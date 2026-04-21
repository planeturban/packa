"""
Worker REST API.

  GET    /status                 — worker state + live ffmpeg progress
  POST   /files                  — submit a file record (enqueues for conversion)
  GET    /files[?status=]        — list file records
  GET    /files/{id}             — get a single file record
  DELETE /files/{id}             — delete a file record (terminates ffmpeg if running)
  PATCH  /files/{id}/status      — update a record's status
  POST   /conversion/stop        — terminate the running ffmpeg process
  POST   /conversion/pause       — suspend the running ffmpeg process (SIGSTOP)
  POST   /conversion/resume      — resume a paused process; clears drain flag
  POST   /conversion/drain       — finish current job then stop polling
  POST   /conversion/sleep       — enter sleep mode (no polling, no new jobs)
  POST   /conversion/wake        — leave sleep mode
  GET    /settings               — current encoder
  POST   /settings               — change encoder (also activates unconfigured worker)
"""

import asyncio
import signal

from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import crud
from shared.config import Config
from shared.db import migrate
from shared.models import Base, FileStatus
from shared.schemas import FileRecordCreate, FileRecordOut, StatusUpdate

from .database import engine, get_db
from .poller import poller_loop
from .state import FfmpegProgress, Job, worker_state
from .store import get_setting, set_setting
from .worker import recover, worker_loop

Base.metadata.create_all(bind=engine)
migrate(engine)

_config: Config = Config()
_advertise_host: str = ""
_worker_config_id: str = ""


def set_config(config: Config) -> None:
    global _config
    _config = config


def set_registration_params(advertise_host: str, worker_config_id: str) -> None:
    global _advertise_host, _worker_config_id
    _advertise_host = advertise_host
    _worker_config_id = worker_config_id


async def _register_and_poll() -> None:
    """Retry registration until master is reachable, then keep registration fresh and run the poller."""
    master_base = f"http://{_config.master_host}:{_config.master_port}"
    url = f"{master_base}/workers"
    payload = {"config_id": _worker_config_id, "host": _advertise_host, "api_port": _config.api_port}

    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                record = r.json()
            worker_state.worker_id = record["id"]
            worker_state.worker_config_id = _worker_config_id
            worker_state.master_url = master_base
            print(f"[worker] registered as worker-{record['id']}")
            break
        except Exception as exc:
            attempt += 1
            wait = min(5 * attempt, 30)
            print(f"[worker] registration failed (attempt {attempt}): {exc} — retrying in {wait}s")
            await asyncio.sleep(wait)

    async def _reregister_loop() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(url, json=payload)
                    r.raise_for_status()
                    record = r.json()
                worker_state.worker_id = record["id"]
            except Exception as exc:
                print(f"[worker] re-registration failed: {exc}")

    if _config.ffmpeg.output_dir:
        await asyncio.gather(
            poller_loop(
                master_url=worker_state.master_url,
                worker_config_id=_worker_config_id,
                path_prefix=_config.path_prefix,
                batch_size=_config.worker.batch_size,
                poll_interval=_config.worker.poll_interval,
                output_dir=_config.ffmpeg.output_dir,
            ),
            _reregister_loop(),
        )
    else:
        await _reregister_loop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    worker_state.presets = _config.ffmpeg.presets
    worker_state.available_encoders = _config.ffmpeg.available_encoders
    worker_state.replace_original = get_setting("replace_original") == "true"
    worker_state.cancel_thresholds = _config.worker.cancel_thresholds

    _default_encoder = worker_state.available_encoders[0] if worker_state.available_encoders else "libx265"
    stored_batch = get_setting("batch_size")
    worker_state.batch_size = max(1, int(stored_batch)) if stored_batch else _config.worker.batch_size

    if get_setting("ready"):
        worker_state.encoder = get_setting("encoder") or _default_encoder
    elif get_setting("first_run"):
        worker_state.encoder = _default_encoder
        worker_state.sleeping = True
        worker_state.unconfigured = True
        print("[worker] no stored configuration — starting in unconfigured state")
    else:
        worker_state.encoder = _default_encoder

    if _config.ffmpeg.output_dir:
        recover(_config.ffmpeg.output_dir)
        tasks.append(asyncio.create_task(worker_loop(
            ffmpeg_bin=_config.ffmpeg.bin,
            output_dir=_config.ffmpeg.output_dir,
            extra_args=_config.ffmpeg.extra_args,
        )))
    tasks.append(asyncio.create_task(_register_and_poll()))
    yield
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Packa Worker API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProgressOut(BaseModel):
    percent: float | None
    speed: float | None
    fps: float | None
    out_time: str | None
    eta_seconds: int | None
    bitrate: str | None
    source_size_bytes: int | None
    current_size_bytes: int | None
    projected_size_bytes: int | None


class WorkerStatus(BaseModel):
    state: str
    record_id: int | None
    queued: int
    progress: ProgressOut | None
    paused: bool
    drain: bool
    sleeping: bool
    disk_full: bool
    unconfigured: bool
    encoder: str
    available_encoders: list[str]
    encoder_labels: dict[str, str]
    current_file: str | None
    current_cmd: str | None
    batch_size: int
    replace_original: bool


class EncoderUpdate(BaseModel):
    encoder: str
    batch_size: int | None = None
    replace_original: bool | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/status", response_model=WorkerStatus)
def get_status():
    p = worker_state.progress
    return WorkerStatus(
        state="processing" if worker_state.active else "idle",
        record_id=worker_state.record_id,
        queued=worker_state.queued,
        paused=worker_state.paused,
        drain=worker_state.drain,
        sleeping=worker_state.sleeping,
        disk_full=worker_state.disk_full,
        unconfigured=worker_state.unconfigured,
        encoder=worker_state.encoder,
        available_encoders=worker_state.available_encoders,
        encoder_labels={k: (f"{v.display_name} ({k})" if v.display_name else k) for k, v in worker_state.presets.items()},
        current_file=worker_state.current_file or None,
        current_cmd=worker_state.current_cmd or None,
        batch_size=worker_state.batch_size,
        replace_original=worker_state.replace_original,
        progress=ProgressOut(
            percent=p.percent,
            speed=p.speed,
            fps=p.fps,
            out_time=p.out_time,
            eta_seconds=p.eta_seconds,
            bitrate=p.bitrate,
            source_size_bytes=p.source_size_bytes,
            current_size_bytes=p.current_size_bytes,
            projected_size_bytes=p.projected_size_bytes,
        ) if p else None,
    )


@app.post("/files", response_model=FileRecordOut, status_code=201)
def submit_file(record: FileRecordCreate, db: Session = Depends(get_db)):
    if _config.path_prefix:
        record = record.model_copy(update={"file_path": _config.path_prefix + record.file_path})
    db_record = crud.create_file_record(db, record)
    if _config.ffmpeg.output_dir:
        worker_state.enqueue(Job(record_id=db_record.id, file_path=db_record.file_path))
        print(f"[api] record {db_record.id} queued (queue size: {worker_state.queued})")
    return db_record


@app.get("/files", response_model=list[FileRecordOut])
def list_files(status: FileStatus | None = None, db: Session = Depends(get_db)):
    return crud.get_all_records(db, status=status)


@app.get("/files/{record_id}", response_model=FileRecordOut)
def get_file(record_id: int, db: Session = Depends(get_db)):
    record = crud.get_file_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.delete("/files/{record_id}", status_code=204)
def delete_file(record_id: int, db: Session = Depends(get_db)):
    if (worker_state.active
            and worker_state.record_id == record_id
            and worker_state.proc is not None):
        if worker_state.paused:
            worker_state.proc.send_signal(signal.SIGCONT)
        worker_state.cancel_reason = "user"
        worker_state.proc.terminate()
        worker_state.drain = False
    else:
        worker_state.cancel_queued(record_id)
    if not crud.delete_file_record(db, record_id):
        raise HTTPException(status_code=404, detail="Record not found")


@app.patch("/files/{record_id}/status", response_model=FileRecordOut)
def update_status(record_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    record = crud.update_status(db, record_id, body.status)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.post("/jobs/push", status_code=202)
def push_jobs(jobs: list[FileRecordCreate], db: Session = Depends(get_db)):
    queued = 0
    for job in jobs:
        full_path = (_config.path_prefix + job.file_path) if _config.path_prefix else job.file_path
        record = None
        try:
            record = crud.create_file_record(db, job.model_copy(update={"file_path": full_path, "worker_id": _worker_config_id}))
        except IntegrityError:
            db.rollback()
            record = crud.get_file_record(db, job.id)
            if record:
                record.status = FileStatus.PENDING
                record.pid = None
                record.started_at = None
                record.finished_at = None
                record.cancel_reason = None
                db.commit()
        if record and _config.ffmpeg.output_dir:
            worker_state.enqueue(Job(record_id=record.id, file_path=record.file_path))
            queued += 1
    print(f"[api] pushed {queued} job(s) to queue")
    return {"queued": queued}


@app.post("/conversion/stop")
def stop_conversion():
    if not worker_state.active or worker_state.proc is None:
        raise HTTPException(status_code=409, detail="No conversion running")
    if worker_state.paused:
        worker_state.proc.send_signal(signal.SIGCONT)
    worker_state.cancel_reason = "user"
    worker_state.proc.terminate()
    worker_state.drain = False


@app.post("/conversion/pause")
def pause_conversion():
    if not worker_state.active or worker_state.proc is None:
        raise HTTPException(status_code=409, detail="No conversion running")
    if worker_state.paused:
        raise HTTPException(status_code=409, detail="Already paused")
    worker_state.proc.send_signal(signal.SIGSTOP)
    worker_state.paused = True


@app.post("/conversion/resume")
def resume_conversion():
    if worker_state.paused:
        if worker_state.proc is not None:
            worker_state.proc.send_signal(signal.SIGCONT)
        worker_state.paused = False
    worker_state.drain = False


@app.post("/conversion/drain")
def drain_conversion():
    worker_state.drain = True


@app.post("/conversion/sleep")
def sleep_conversion():
    worker_state.sleeping = True
    worker_state.drain = False


@app.post("/conversion/wake")
def wake_conversion():
    worker_state.sleeping = False
    worker_state.drain = False
    worker_state.disk_full = False


# ---------------------------------------------------------------------------
# Encoder settings
# ---------------------------------------------------------------------------

@app.get("/settings")
def get_settings():
    return {"encoder": worker_state.encoder, "batch_size": worker_state.batch_size, "replace_original": worker_state.replace_original}


@app.post("/settings")
def update_settings(body: EncoderUpdate):
    if body.encoder not in worker_state.presets:
        raise HTTPException(
            status_code=400,
            detail=f"encoder must be one of: {', '.join(sorted(worker_state.presets))}",
        )
    worker_state.encoder = body.encoder
    set_setting("encoder", body.encoder)
    set_setting("ready", "true")
    set_setting("first_run", "false")
    if body.batch_size is not None:
        worker_state.batch_size = max(1, body.batch_size)
        set_setting("batch_size", str(worker_state.batch_size))
    if body.replace_original is not None:
        worker_state.replace_original = body.replace_original
        set_setting("replace_original", "true" if body.replace_original else "false")
    if worker_state.unconfigured:
        worker_state.unconfigured = False
        print(f"[worker] activated with encoder={body.encoder!r} — sleeping until woken")
    else:
        print(f"[worker] encoder changed to {body.encoder!r}")
    return {"encoder": worker_state.encoder, "batch_size": worker_state.batch_size}
