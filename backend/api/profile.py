from __future__ import annotations

from datetime import datetime, timezone

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, select

from backend.api.deps import current_user, get_owned
from backend.config import get_settings
from backend.cv.formats import STYLES, list_formats
from backend.cv.layout_import import learn_layout
from backend.cv.parser import CVParseError
from backend.cv.renderer import cv_to_docx, cv_to_markdown, cv_to_pdf
from backend.cv.schema import CVData
from backend.cv.bullet_coach import suggest
from backend.cv.strength import assess
from backend.db import get_session
from backend.models import MasterCV, Profile, User
from backend.schemas.api import MasterCVOut, MasterCVSummary, ProfileIO
from backend.services import cv_service
from backend.services.common import NotReadyError, audit
from backend.services.discovery import rescore_all

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile", response_model=ProfileIO)
def get_profile(user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = session.exec(select(Profile).where(Profile.user_id == user.id)).first()
    if record is None:
        out = ProfileIO()
        out.profile.full_name, out.profile.email = user.full_name, user.email
        return out
    prefs = dict(record.preferences or {})
    auto = prefs.pop("auto_discovery", True)
    data = dict(record.data or {})
    data["photo_path"] = "uploaded" if data.get("photo_path") else ""  # never expose server paths
    return ProfileIO(profile=data, preferences=prefs, auto_discovery=auto)


@router.put("/profile", response_model=ProfileIO)
def save_profile(body: ProfileIO, user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = session.exec(select(Profile).where(Profile.user_id == user.id)).first() or Profile(user_id=user.id)
    previous = record.data or {}
    data = body.profile.model_dump()
    # Server-managed fields can only change through their own endpoints.
    data["photo_path"] = previous.get("photo_path", "")
    data["custom_layouts"] = previous.get("custom_layouts", [])
    record.data = data
    previous_prefs = record.preferences or {}
    record.preferences = {**body.preferences.model_dump(exclude={"cv_roles"}), "auto_discovery": body.auto_discovery,
                          # managed on the Companies page
                          "target_companies": previous_prefs.get("target_companies", [])}
    record.updated_at = datetime.now(timezone.utc)
    session.add(record)
    audit(session, user.id, "profile.updated")
    session.commit()
    try:
        rescore_all(session, user.id)
    except NotReadyError:
        pass
    body.profile.photo_path = "uploaded" if data["photo_path"] else ""
    body.profile.custom_layouts = data["custom_layouts"]
    return body


def _profile_record(session: Session, user: User) -> Profile:
    record = session.exec(select(Profile).where(Profile.user_id == user.id)).first()
    if record is None:
        record = Profile(user_id=user.id, data={"full_name": user.full_name, "email": user.email}, preferences={})
        session.add(record)
        session.flush()
    return record


PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}


@router.post("/profile/photo")
async def upload_photo(file: UploadFile = File(...), user: User = Depends(current_user),
                       session: Session = Depends(get_session)):
    data = await file.read()
    ext = PHOTO_TYPES.get(file.content_type or "")
    if ext is None or not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a JPG or PNG photo.")
    if len(data) > 3 * 1024 * 1024:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Photo must be under 3 MB.")
    folder = get_settings().uploads_dir / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("photo.*"):
        old.unlink()
    path = folder / f"photo{ext}"
    path.write_bytes(data)
    record = _profile_record(session, user)
    record.data = {**(record.data or {}), "photo_path": str(path)}
    session.add(record)
    session.commit()
    return {"ok": True}


@router.get("/profile/photo")
def get_photo(user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = _profile_record(session, user)
    path = (record.data or {}).get("photo_path")
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo.")
    return FileResponse(path)


@router.delete("/profile/photo")
def delete_photo(user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = _profile_record(session, user)
    path = (record.data or {}).get("photo_path")
    if path and Path(path).exists():
        Path(path).unlink()
    record.data = {**(record.data or {}), "photo_path": ""}
    session.add(record)
    session.commit()
    return {"ok": True}


@router.get("/cv-formats")
def cv_formats(user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = _profile_record(session, user)
    return {"countries": list_formats(),
            "styles": [{"key": k, "label": v["label"]} for k, v in STYLES.items()],
            "custom_layouts": (record.data or {}).get("custom_layouts", [])}


@router.post("/cv-layouts/sample")
async def learn_sample_layout(file: UploadFile = File(...), name: str = Form(""), user: User = Depends(current_user),
                              session: Session = Depends(get_session)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File is larger than 10 MB.")
    try:
        layout = learn_layout(file.filename or "sample.pdf", data, name)
    except CVParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    record = _profile_record(session, user)
    layouts = [*(record.data or {}).get("custom_layouts", []), layout][-20:]
    record.data = {**(record.data or {}), "custom_layouts": layouts}
    session.add(record)
    audit(session, user.id, "cv_layout.learned", sections=layout["section_order"])
    session.commit()
    return layout


@router.delete("/cv-layouts/{layout_id}")
def delete_layout(layout_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = _profile_record(session, user)
    layouts = [l for l in (record.data or {}).get("custom_layouts", []) if l.get("id") != layout_id]
    record.data = {**(record.data or {}), "custom_layouts": layouts}
    session.add(record)
    session.commit()
    return {"ok": True}


def _cv_out(record: MasterCV) -> MasterCVOut:
    return MasterCVOut(id=record.id, version=record.version, original_filename=record.original_filename,
                       status=record.status, is_active=record.is_active, parse_method=record.parse_method,
                       parse_notes=record.parse_notes, data=record.data, parsed_data=record.parsed_data,
                       raw_text=record.raw_text, created_at=record.created_at, verified_at=record.verified_at)


@router.post("/cv/upload", response_model=MasterCVOut)
async def upload_cv(file: UploadFile = File(...), user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    data = await file.read()
    try:
        record = cv_service.upload_master_cv(session, user.id, file.filename or "cv", data)
    except CVParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return _cv_out(record)


@router.get("/cv", response_model=list[MasterCVSummary])
def list_cvs(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(MasterCV).where(MasterCV.user_id == user.id).order_by(MasterCV.version.desc())).all()
    return [MasterCVSummary(id=r.id, version=r.version, original_filename=r.original_filename, status=r.status,
                            is_active=r.is_active, created_at=r.created_at, verified_at=r.verified_at) for r in rows]


@router.get("/cv/active", response_model=MasterCVOut | None)
def active_cv(user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = session.exec(select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)  # noqa: E712
                          .order_by(MasterCV.version.desc())).first()
    return _cv_out(record) if record else None


@router.get("/cv/{cv_id}", response_model=MasterCVOut)
def get_cv(cv_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _cv_out(get_owned(session, MasterCV, cv_id, user))


@router.put("/cv/{cv_id}", response_model=MasterCVOut)
def update_cv(cv_id: int, body: CVData, user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = get_owned(session, MasterCV, cv_id, user)
    if not record.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only the active CV version can be edited.")
    return _cv_out(cv_service.update_master_cv_data(session, user.id, record, body))


@router.post("/cv/{cv_id}/verify", response_model=MasterCVOut)
def verify_cv(cv_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = get_owned(session, MasterCV, cv_id, user)
    try:
        record = cv_service.verify_master_cv(session, user.id, record)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    try:
        rescore_all(session, user.id)
    except NotReadyError:
        pass
    return _cv_out(record)


@router.get("/cv/{cv_id}/strength")
def cv_strength(cv_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = get_owned(session, MasterCV, cv_id, user)
    return assess(CVData.model_validate(record.data)).as_dict()


@router.get("/profile/suggested-roles")
def suggested_roles(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Roles found in your active CV, with why, and whether you switched any off."""
    from backend.jobs.role_suggest import suggest_roles
    from backend.services.common import get_profile as load_profile

    _, prefs = load_profile(session, user.id)
    record = session.exec(select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)  # noqa: E712
                          .order_by(MasterCV.version.desc())).first()
    roles = suggest_roles(CVData.model_validate(record.data)) if record else []
    excluded = {r.lower() for r in prefs.excluded_cv_roles}
    return {"include_cv_roles": prefs.include_cv_roles,
            "roles": [{**r, "excluded": r["title"].lower() in excluded} for r in roles]}


@router.get("/cv/{cv_id}/coach")
def cv_coach(cv_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Bullets without numbers, each with an X-Y-Z template that has blanks for your real figures."""
    record = get_owned(session, MasterCV, cv_id, user)
    cv = CVData.model_validate(record.data)
    out = []
    for i, exp in enumerate(cv.experience):
        for j, bullet in enumerate(exp.bullets):
            tip = suggest(bullet)
            if tip:
                out.append({"role_index": i, "bullet_index": j, "role": f"{exp.title}, {exp.employer}",
                            "bullet": bullet, "suggestion": tip})
    return out


@router.get("/cv/{cv_id}/original")
def download_original(cv_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = get_owned(session, MasterCV, cv_id, user)
    return FileResponse(record.stored_path, filename=record.original_filename)


@router.get("/cv/{cv_id}/render")
def render_cv(cv_id: int, format: str = Query("pdf", pattern="^(pdf|docx|md)$"), user: User = Depends(current_user),
              session: Session = Depends(get_session)):
    record = get_owned(session, MasterCV, cv_id, user)
    cv = CVData.model_validate(record.data)
    name = f"master_cv_v{record.version}.{format}"
    if format == "pdf":
        return Response(cv_to_pdf(cv), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
    if format == "docx":
        return Response(cv_to_docx(cv),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
    return Response(cv_to_markdown(cv), media_type="text/markdown")
