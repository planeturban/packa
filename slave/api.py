import asyncio
import signal
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import crud
from shared.base import Base
from shared.config import Config
from shared.models import FileStatus
from shared.schemas import FileRecordCreate, FileRecordOut, StatusUpdate
from shared.tls import httpx_kwargs, scheme

from .database import _migrate, engine, get_db
from .poller import poller_loop
from .settings import get_setting, set_setting
from .state import FfmpegProgress, Job, worker_state
from .worker import recover, worker_loop

Base.metadata.create_all(bind=engine)
_migrate()

_config: Config = Config()
_advertise_host: str = ""
_slave_config_id: str = ""


def set_config(config: Config) -> None:
    global _config
    _config = config


def set_registration_params(advertise_host: str, slave_config_id: str) -> None:
    global _advertise_host, _slave_config_id
    _advertise_host = advertise_host
    _slave_config_id = slave_config_id


async def _register_and_poll() -> None:
    """Retry registration until master is reachable, then run the poller."""
    url = f"{scheme(_config.tls)}://{_config.master_host}:{_config.master_port}/slaves"
    payload = {"config_id": _slave_config_id, "host": _advertise_host, "api_port": _config.api_port}
    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=10, **httpx_kwargs(_config.tls)) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                record = r.json()
            worker_state.slave_id = record["id"]
            worker_state.slave_config_id = _slave_config_id
            worker_state.master_url = f"{scheme(_config.tls)}://{_config.master_host}:{_config.master_port}"
            print(f"[slave] registered as slave-{record['id']}")
            break
        except Exception as exc:
            attempt += 1
            wait = min(5 * attempt, 30)
            print(f"[slave] registration failed (attempt {attempt}): {exc} — retrying in {wait}s")
            await asyncio.sleep(wait)

    if _config.ffmpeg.output_dir:
        await poller_loop(
            master_url=worker_state.master_url,
            slave_config_id=_slave_config_id,
            path_prefix=_config.path_prefix,
            batch_size=_config.worker.batch_size,
            poll_interval=_config.worker.poll_interval,
            output_dir=_config.ffmpeg.output_dir,
            tls=_config.tls,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    worker_state.tls = _config.tls
    worker_state.vaapi_device = _config.ffmpeg.vaapi_device
    worker_state.presets = _config.ffmpeg.presets
    # If the slave has never been activated via the web UI, start unconfigured (sleeping).
    # main.py writes "first_run=true" on the very first startup (no slave_id in DB yet).
    # Once the user selects an encoder, "ready=true" is written and this branch is skipped.
    # Slaves that existed before this feature (no "first_run" key) start normally.
    if get_setting("ready"):
        worker_state.encoder = get_setting("encoder") or _config.ffmpeg.encoder
    elif get_setting("first_run"):
        worker_state.encoder = _config.ffmpeg.encoder
        worker_state.sleeping = True
        worker_state.unconfigured = True
        print("[slave] no stored configuration — starting in unconfigured state")
    else:
        worker_state.encoder = _config.ffmpeg.encoder
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


app = FastAPI(title="Packa Slave API", lifespan=lifespan)


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
    current_size_bytes: int | None
    projected_size_bytes: int | None


class SlaveStatus(BaseModel):
    state: str                    # "idle" or "processing"
    record_id: int | None
    queued: int
    progress: ProgressOut | None  # only present while processing
    paused: bool
    drain: bool
    sleeping: bool
    unconfigured: bool
    encoder: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/status", response_model=SlaveStatus)
def get_status():
    p = worker_state.progress
    return SlaveStatus(
        state="processing" if worker_state.active else "idle",
        record_id=worker_state.record_id,
        queued=worker_state.queued,
        paused=worker_state.paused,
        drain=worker_state.drain,
        sleeping=worker_state.sleeping,
        unconfigured=worker_state.unconfigured,
        encoder=worker_state.encoder,
        progress=ProgressOut(
            percent=p.percent,
            speed=p.speed,
            fps=p.fps,
            out_time=p.out_time,
            eta_seconds=p.eta_seconds,
            bitrate=p.bitrate,
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
def list_files(
    status: FileStatus | None = None,
    db: Session = Depends(get_db),
):
    return crud.get_all_records(db, status=status)


@app.get("/files/{record_id}", response_model=FileRecordOut)
def get_file(record_id: int, db: Session = Depends(get_db)):
    record = crud.get_file_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.delete("/files/{record_id}", status_code=204)
def delete_file(record_id: int, db: Session = Depends(get_db)):
    if not crud.delete_file_record(db, record_id):
        raise HTTPException(status_code=404, detail="Record not found")


@app.patch("/files/{record_id}/status", response_model=FileRecordOut)
def update_status(record_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    record = crud.update_status(db, record_id, body.status)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


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


# ---------------------------------------------------------------------------
# Encoder settings
# ---------------------------------------------------------------------------

_VALID_ENCODERS = {"libx265", "nvenc", "vaapi", "videotoolbox"}


class EncoderUpdate(BaseModel):
    encoder: str


@app.get("/settings")
def get_settings():
    return {"encoder": worker_state.encoder, "vaapi_device": worker_state.vaapi_device}


@app.post("/settings")
def update_settings(body: EncoderUpdate):
    if body.encoder not in _VALID_ENCODERS:
        raise HTTPException(
            status_code=400,
            detail=f"encoder must be one of: {', '.join(sorted(_VALID_ENCODERS))}",
        )
    worker_state.encoder = body.encoder
    set_setting("encoder", body.encoder)
    set_setting("ready", "true")
    set_setting("first_run", "false")
    if worker_state.unconfigured:
        worker_state.unconfigured = False
        worker_state.sleeping = False
        print(f"[slave] activated with encoder={body.encoder!r}")
    else:
        print(f"[slave] encoder changed to {body.encoder!r}")
    return {"encoder": worker_state.encoder, "vaapi_device": worker_state.vaapi_device}
