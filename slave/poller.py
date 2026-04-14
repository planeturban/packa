"""
Background poller — slave pulls jobs from master.

Runs as an asyncio task alongside worker_loop. When the job queue is empty
the poller contacts master's POST /jobs/claim endpoint to fetch up to
batch_size records. Each claimed record is inserted into the slave DB and
enqueued for the worker.

If master is unreachable the poller logs the error and retries after
poll_interval seconds — the worker keeps processing whatever is already
queued.
"""

import asyncio

import httpx

from shared import crud
from shared.config import TlsConfig
from shared.schemas import FileRecordCreate
from shared.tls import httpx_kwargs

from .database import SessionLocal
from .state import Job, worker_state


async def poller_loop(
    master_url: str,
    slave_config_id: str,
    path_prefix: str,
    batch_size: int,
    poll_interval: int,
    output_dir: str,
    tls: TlsConfig,
) -> None:
    print(f"[poller] started (batch_size={batch_size}, poll_interval={poll_interval}s)")
    while True:
        await asyncio.sleep(poll_interval)
        if worker_state.queued > 0 or worker_state.active:
            continue
        await _claim_and_enqueue(master_url, slave_config_id, path_prefix, batch_size, output_dir, tls)


async def _claim_and_enqueue(
    master_url: str,
    slave_config_id: str,
    path_prefix: str,
    batch_size: int,
    output_dir: str,
    tls: TlsConfig,
) -> None:
    url = f"{master_url}/jobs/claim"
    try:
        async with httpx.AsyncClient(timeout=10, **httpx_kwargs(tls)) as client:
            response = await client.post(url, json={"slave_id": slave_config_id, "count": batch_size})
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
            full_path = path_prefix + job_data["file_path"] if path_prefix else job_data["file_path"]
            record = crud.create_file_record(db, FileRecordCreate(
                id=job_data["id"],
                slave_id=slave_config_id,
                file_name=job_data["file_name"],
                file_path=full_path,
                c_time=job_data["c_time"],
                m_time=job_data["m_time"],
                checksum=job_data["checksum"],
            ))
            if output_dir:
                worker_state.enqueue(Job(record_id=record.id, file_path=record.file_path))
                print(f"[poller] claimed record {record.id} '{record.file_name}'")
    finally:
        db.close()
