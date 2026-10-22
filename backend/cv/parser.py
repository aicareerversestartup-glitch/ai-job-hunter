"""Extract raw text from an uploaded CV (PDF, DOCX, TXT/MD) with an OCR fallback for scans."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.utils.text import clean_whitespace

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MIN_TEXT_CHARS_BEFORE_OCR = 200


class CVParseError(ValueError):
    pass


@dataclass
class ExtractedText:
    text: str
    method: str  # "pdf-text" | "pdf-ocr" | "docx" | "plain"
    pages: int = 1
    warnings: list[str] | None = None


def extract_text(filename: str, data: bytes) -> ExtractedText:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise CVParseError(f"Unsupported file type {ext!r}. Upload PDF, DOCX, TXT or MD.")
    if not data:
        raise CVParseError("The uploaded file is empty.")
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    return ExtractedText(text=clean_whitespace(data.decode("utf-8", errors="replace")), method="plain")


def _extract_pdf(data: bytes) -> ExtractedText:
    from pypdf import PdfReader  # imported lazily so the module loads without it

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pypdf raises several error types
        raise CVParseError(f"Could not read PDF: {exc}") from exc
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise CVParseError("The PDF is password protected.") from exc
    pages = [page.extract_text() or "" for page in reader.pages]
    text = clean_whitespace("\n\n".join(pages))
    if len(text) >= MIN_TEXT_CHARS_BEFORE_OCR:
        return ExtractedText(text=text, method="pdf-text", pages=len(pages))

    ocr_text = _ocr_pdf(data)
    if ocr_text and len(ocr_text) > len(text):
        return ExtractedText(text=ocr_text, method="pdf-ocr", pages=len(pages),
                             warnings=["Text was recovered with OCR. Check the parsed CV carefully."])
    warnings = ["Very little text found. If this is a scanned CV, install Tesseract to enable OCR."]
    return ExtractedText(text=text, method="pdf-text", pages=len(pages), warnings=warnings)


def _ocr_pdf(data: bytes) -> str:
    """OCR fallback. Needs the optional extras: pytesseract + pypdfium2 and the tesseract binary."""
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError:
        log.info("OCR libraries not installed; skipping OCR fallback")
        return ""
    try:
        pdf = pdfium.PdfDocument(data)
        chunks = []
        for index in range(len(pdf)):
            image = pdf[index].render(scale=2.5).to_pil()
            chunks.append(pytesseract.image_to_string(image))
        return clean_whitespace("\n\n".join(chunks))
    except Exception as exc:  # tesseract binary missing, corrupt page, ...
        log.warning("OCR failed: %s", exc)
        return ""


def _extract_docx(data: bytes) -> ExtractedText:
    import docx  # python-docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise CVParseError(f"Could not read DOCX: {exc}") from exc
    lines: list[str] = []
    for block in _iter_docx_blocks(document):
        lines.append(block)
    return ExtractedText(text=clean_whitespace("\n".join(lines)), method="docx")


def _iter_docx_blocks(document):
    """Yield paragraph and table-cell text in document order (tables are common in CVs)."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = para.text.strip()
            if text:
                style = (para.style.name or "").lower() if para.style is not None else ""
                prefix = "- " if "list" in style and not text.startswith(("-", "•")) else ""
                yield prefix + text
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                seen = set()
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    if cell_text and cell_text not in seen:
                        seen.add(cell_text)
                        yield cell_text
