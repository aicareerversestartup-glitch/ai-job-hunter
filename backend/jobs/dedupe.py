"""Duplicate detection across sources and across discovery runs."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from backend.jobs.normalizer import NormalizedJob, normalize_company, normalize_title
from backend.utils.text import normalize_key, token_set, jaccard

TITLE_SIMILARITY = 0.9
DESCRIPTION_SIMILARITY = 0.8


@dataclass(frozen=True)
class JobKey:
    """The minimum needed to compare a new posting with one already stored."""
    source: str
    source_job_id: str
    fingerprint: str
    company: str
    title: str
    location: str
    description_tokens: frozenset[str]

    @classmethod
    def from_job(cls, job: NormalizedJob) -> "JobKey":
        return cls(job.source, job.source_job_id, job.fingerprint, normalize_company(job.company),
                   normalize_title(job.title), normalize_key(job.location),
                   frozenset(token_set(job.description_text[:4000])))


def is_duplicate(a: JobKey, b: JobKey) -> bool:
    if (a.source, a.source_job_id) == (b.source, b.source_job_id):
        return True
    if a.fingerprint == b.fingerprint:
        return True
    if a.company != b.company or not a.company:
        return False
    title_sim = SequenceMatcher(None, a.title, b.title).ratio()
    if title_sim < TITLE_SIMILARITY:
        return False
    same_place = a.location == b.location or not a.location or not b.location
    desc_sim = jaccard(a.description_tokens, b.description_tokens)
    return same_place or desc_sim >= DESCRIPTION_SIMILARITY


@dataclass
class DedupeResult:
    unique: list[NormalizedJob]
    duplicates: list[tuple[NormalizedJob, JobKey]]  # (new job, the existing key it duplicates)


def dedupe(jobs: list[NormalizedJob], existing: list[JobKey] | None = None) -> DedupeResult:
    """Keep the first occurrence of each job. Postings with a direct ATS source are preferred
    over aggregator copies because their apply link goes straight to the employer."""
    preferred = sorted(jobs, key=lambda j: 0 if j.source in {"greenhouse", "lever", "ashby", "workable"} else 1)
    seen: list[JobKey] = list(existing or [])
    by_fingerprint = {k.fingerprint: k for k in seen}
    by_source_id = {(k.source, k.source_job_id): k for k in seen}
    unique: list[NormalizedJob] = []
    duplicates: list[tuple[NormalizedJob, JobKey]] = []
    for job in preferred:
        key = JobKey.from_job(job)
        match = by_source_id.get((key.source, key.source_job_id)) or by_fingerprint.get(key.fingerprint)
        if match is None:
            match = next((k for k in seen if k.company == key.company and is_duplicate(key, k)), None)
        if match is not None:
            duplicates.append((job, match))
            continue
        seen.append(key)
        by_fingerprint[key.fingerprint] = key
        by_source_id[(key.source, key.source_job_id)] = key
        unique.append(job)
    return DedupeResult(unique=unique, duplicates=duplicates)
