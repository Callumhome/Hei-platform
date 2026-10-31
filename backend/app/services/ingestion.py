from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ElectricityReading, SyncJob


def create_sync_job(db: Session, *, household_id: str, provider: str, job_type: str, max_attempts: int = 5) -> SyncJob:
    provider = provider.strip().lower()
    if not provider or len(provider) > 60:
        raise ValueError("provider must be a valid lowercase identifier")
    if not 1 <= max_attempts <= 20:
        raise ValueError("max_attempts must be between 1 and 20")
    job = SyncJob(id=str(uuid4()), household_id=household_id, provider=provider,
                  job_type=job_type, status="queued", max_attempts=max_attempts)
    db.add(job)
    db.flush()
    return job


def mark_sync_started(db: Session, job: SyncJob) -> None:
    if job.status not in {"queued", "retry"}:
        raise ValueError("Only queued or retry jobs can be started")
    job.status = "running"
    job.attempts += 1
    job.started_at = datetime.now(timezone.utc)
    job.finished_at = None
    job.next_attempt_at = None
    job.error_code = None
    job.error_message = None
    db.flush()


def mark_sync_succeeded(db: Session, job: SyncJob, *, cursor: str | None = None) -> None:
    if job.status != "running":
        raise ValueError("Only running jobs can succeed")
    job.status = "succeeded"
    job.cursor = cursor
    job.finished_at = datetime.now(timezone.utc)
    job.next_attempt_at = None
    db.flush()


def mark_sync_failed(db: Session, job: SyncJob, *, error_code: str, error_message: str, retryable: bool = True) -> None:
    if job.status != "running":
        raise ValueError("Only running jobs can fail")
    job.error_code = error_code[:80]
    job.error_message = error_message[:500]
    job.finished_at = datetime.now(timezone.utc)
    if retryable and job.attempts < job.max_attempts:
        job.status = "retry"
        job.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=min(3600, 30 * (2 ** (job.attempts - 1))))
    else:
        job.status = "failed"
        job.next_attempt_at = None
    db.flush()


def ingest_reading_page(db: Session, *, meter_id: str, provider: str, readings: tuple) -> tuple[int, int]:
    """Persist normalized intervals once; return (inserted, duplicate_count)."""
    inserted = duplicates = 0
    seen_intervals: set[tuple[datetime, datetime]] = set()
    for reading in readings:
        reading.validate()
        interval_key = (reading.interval_start, reading.interval_end)
        if interval_key in seen_intervals:
            duplicates += 1
            continue
        seen_intervals.add(interval_key)
        existing = db.scalar(select(ElectricityReading).where(
            ElectricityReading.meter_id == meter_id,
            ElectricityReading.interval_start == reading.interval_start,
            ElectricityReading.interval_end == reading.interval_end,
        ))
        if existing:
            duplicates += 1
            continue
        db.add(ElectricityReading(
            meter_id=meter_id, interval_start=reading.interval_start,
            interval_end=reading.interval_end, consumption_kwh=reading.import_kwh,
            export_kwh=reading.export_kwh, source_record_ref=reading.source_record_ref,
            source_provider=provider.strip().lower(), quality=reading.quality,
        ))
        inserted += 1
    db.flush()
    return inserted, duplicates
