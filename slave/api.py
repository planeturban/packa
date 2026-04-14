import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import crud
from shared.base import Base
from shared.config import Config
from shared.models import FileStatus
from shared.schemas import FileRecordCreate, FileRecordOut, StatusUpdate

from .database import engine, get_db
from .poller import poller_loop
from .state import FfmpegProgress, Job, worker_state
from .worker import recover, worker_loop

Base.metadata.create_all(bind=engine)

_config: Config = Config()


def set_config(config: Config) -> None:
    global _config
    _config = config


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    if _config.ffmpeg.output_dir:
        recover(_config.ffmpeg.output_dir)
        tasks.append(asyncio.create_task(worker_loop(
            ffmpeg_bin=_config.ffmpeg.bin,
            output_dir=_config.ffmpeg.output_dir,
            extra_args=_config.ffmpeg.extra_args,
        )))
        if worker_state.master_url and worker_state.slave_config_id:
            tasks.append(asyncio.create_task(poller_loop(
                master_url=worker_state.master_url,
                slave_config_id=worker_state.slave_config_id,
                path_prefix=_config.path_prefix,
                batch_size=_config.worker.batch_size,
                poll_interval=_config.worker.poll_interval,
                output_dir=_config.ffmpeg.output_dir,
            )))
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


@app.patch("/files/{record_id}/status", response_model=FileRecordOut)
def update_status(record_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    record = crud.update_status(db, record_id, body.status)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record
