"""
Background poller — worker pulls jobs from master.

Runs as an asyncio task alongside worker_loop. When the job queue is empty
the poller contacts master's POST /jobs/claim endpoint to fetch up to
batch_size records. Each claimed record is inserted into the worker DB and
enqueued for the worker.
"""

import asyncio
from pathlib import Path

import httpx
from sqlalchemy.exc import IntegrityError

from shared import crud
from shared.models import FileStatus
from shared.schemas import FileRecordCreate

from .database import SessionLocal
from .state import Job, worker_state


async def poller_loop(
    master_url: str,
    worker_config_id: str,
) -> None:
    print(f"[poller] started (batch_size={worker_state.batch_size}, poll_interval={worker_state.poll_interval}s)")
    while True:
        await asyncio.sleep(worker_state.poll_interval)
        if worker_state.unconfigured or worker_state.sleeping or worker_state.queued > 0 or worker_state.active or worker_state.drain:
            continue
        await _claim_and_enqueue(
            master_url, worker_config_id,
            worker_state.path_prefix, worker_state.batch_size, worker_state.output_dir,
        )


async def _claim_and_enqueue(
    master_url: str,
    worker_config_id: str,
    path_prefix: str,
    batch_size: int,
    output_dir: str,
) -> None:
    url = f"{master_url}/jobs/claim"
    try:
        async with httpx.AsyncClient(timeout=10, **worker_state.tls.httpx_kwargs()) as client:
            response = await client.post(url, json={"worker_id": worker_config_id, "count": batch_size})
            response.raise_for_status()
            jobs = response.json()
    except Exception as exc:
        print(f"[poller] failed to reach master: {exc}")
        return

    if not jobs:
        return

    db = SessionLocal()
    try:
        for job_data in jobs:
            raw_relative = job_data["file_path"]
            full_path = path_prefix + raw_relative if path_prefix else raw_relative
            if path_prefix:
                try:
                    resolved = Path(full_path).resolve()
                    resolved.relative_to(Path(path_prefix).resolve())
                    full_path = str(resolved)
                except (ValueError, OSError):
                    print(f"[poller] rejecting job {job_data.get('id')} — path escapes prefix: {raw_relative!r}")
                    continue
            record = None
            try:
                record = crud.create_file_record(db, FileRecordCreate(
                    id=job_data["id"],
                    worker_id=worker_config_id,
                    file_name=job_data["file_name"],
                    file_path=full_path,
                    file_size=job_data.get("file_size"),
                    c_time=job_data["c_time"],
                    m_time=job_data["m_time"],
                    checksum=job_data["checksum"],
                ))
            except IntegrityError:
                db.rollback()
                record = crud.get_file_record(db, job_data["id"])
                if record:
                    record.status = FileStatus.PENDING
                    record.pid = None
                    record.started_at = None
                    record.finished_at = None
                    record.cancel_reason = None
                    db.commit()
                    print(f"[poller] re-claimed existing record {record.id} '{record.file_name}' — reset to pending")
            if record and output_dir:
                worker_state.enqueue(Job(record_id=record.id, file_path=record.file_path,
                                         duration=job_data.get("duration"),
                                         force_encode=bool(job_data.get("force_encode", False))))
                print(f"[poller] claimed record {record.id} '{record.file_name}'")
    finally:
        db.close()
