"""
Master REST API.

  POST   /workers               — worker registration
  GET    /workers               — list registered workers
  DELETE /workers/{id}          — deregister a worker
  POST   /transfer             — accept a file path, create a PENDING record
  POST   /jobs/claim           — worker claims N pending jobs (pull model)
  PATCH  /files/{id}/result    — worker pushes final conversion result
  PATCH  /files/{id}/status    — update a record's status
  GET    /files[?status=]      — list records, filterable by status
  GET    /files/{id}           — get a single record
  DELETE /files/{id}           — delete a record (cascades to worker)
  POST   /scan/start           — start background directory scan
  POST   /scan/stop            — cancel running scan
  GET    /scan/status          — scan progress
  GET    /scan/settings        — periodic scan settings
  POST   /scan/settings        — update periodic scan settings
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import crud
from shared.config import Config
from shared.db import migrate
from shared.models import Base, FileRecord, FileStatus
from shared.schemas import FileRecordCreate, FileRecordOut, StatusUpdate

from .database import SessionLocal, engine, get_db
from .registry import registry
from .scanner import collect
from .settings import get_setting, set_setting

Base.metadata.create_all(bind=engine)
migrate(engine)

_last_periodic_start: datetime | None = None


# ---------------------------------------------------------------------------
# Startup / background tasks
# ---------------------------------------------------------------------------

def _recover() -> None:
    """Reset any PROCESSING records to PENDING on startup."""
    db = SessionLocal()
    try:
        stuck = (
            db.query(FileRecord)
            .filter(FileRecord.status == FileStatus.PROCESSING)
            .all()
        )
        for record in stuck:
            record.status = FileStatus.PENDING
            record.pid = None
        if stuck:
            db.commit()
            print(f"[master] reset {len(stuck)} stuck PROCESSING record(s) to PENDING")
    finally:
        db.close()


_hevc_cursor: int = 0  # last record id checked; resets each full cycle


async def _probe_codec(file_path: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip().lower()
    except Exception:
        return ""


async def _hevc_check_loop() -> None:
    """Cursor-based loop: probe all PENDING records for HEVC, 20 at a time concurrently."""
    global _hevc_cursor
    await asyncio.sleep(15)
    while True:
        db = SessionLocal()
        try:
            records = (
                db.query(FileRecord)
                .filter(
                    FileRecord.status == FileStatus.PENDING,
                    FileRecord.id > _hevc_cursor,
                )
                .order_by(FileRecord.id)
                .limit(20)
                .all()
            )
            if not records:
                _hevc_cursor = 0
                await asyncio.sleep(60)
                continue
            codecs = await asyncio.gather(*[_probe_codec(r.file_path) for r in records])
            for record, codec in zip(records, codecs):
                if codec == "hevc":
                    record.status = FileStatus.DISCARDED
                    print(f"[master] record {record.id} discarded — already HEVC ({record.file_name!r})")
            db.commit()
            _hevc_cursor = records[-1].id
        finally:
            db.close()
        await asyncio.sleep(0)


async def _periodic_scan_loop() -> None:
    global _last_periodic_start
    while True:
        await asyncio.sleep(5)
        if not _config.path_prefix:
            continue
        db = SessionLocal()
        try:
            enabled = get_setting(db, "scan_periodic_enabled") == "true"
            interval = int(get_setting(db, "scan_interval_seconds") or "60")
        finally:
            db.close()
        if not enabled or _scan.running:
            continue
        now = datetime.now(timezone.utc)
        if _last_periodic_start is None or (now - _last_periodic_start).total_seconds() >= interval:
            _last_periodic_start = now
            extensions = {e if e.startswith(".") else f".{e}" for e in _config.scan.extensions}
            _scan._task = asyncio.create_task(_scan_task(
                _config.path_prefix, extensions,
                _config.scan.min_size, _config.scan.max_size,
            ))
            print(f"[master] periodic scan started (interval={interval}s)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _recover()
    tasks = [
        asyncio.create_task(_periodic_scan_loop()),
        asyncio.create_task(_hevc_check_loop()),
    ]
    yield
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Packa Master API", lifespan=lifespan)

_config: Config = Config()


def set_config(config: Config) -> None:
    global _config
    _config = config


# ---------------------------------------------------------------------------
# Scan state
# ---------------------------------------------------------------------------

class _ScanState:
    def __init__(self) -> None:
        self.running: bool = False
        self.found: int = 0
        self.skipped: int = 0
        self.errors: int = 0
        self._task: asyncio.Task | None = None

    def cancel(self) -> bool:
        if self._task and not self._task.done():
            self._task.cancel()
            return True
        return False


_scan = _ScanState()


async def _scan_task(scan_dir: str, extensions: set[str], min_size: int, max_size: int) -> None:
    from pathlib import Path
    _scan.running = True
    _scan.found = _scan.skipped = _scan.errors = 0
    print(f"[scan] starting in '{scan_dir}' (extensions: {sorted(extensions)})")
    db = SessionLocal()
    try:
        for path in Path(scan_dir).rglob("*"):
            await asyncio.sleep(0)
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            size = path.stat().st_size
            if (min_size > 0 and size < min_size) or (max_size > 0 and size > max_size):
                _scan.skipped += 1
                continue
            if crud.get_record_by_path(db, str(path)):
                _scan.skipped += 1
                continue
            try:
                video = collect(str(path), _config.scan.checksum_bytes)
                existing = crud.get_record_by_checksum(db, video.checksum)
                status = FileStatus.DUPLICATE if existing else FileStatus.PENDING
                duplicate_of_id = existing.id if existing else None
                crud.create_file_record(db, FileRecordCreate(
                    file_name=video.file_name,
                    file_path=video.file_path,
                    file_size=video.file_size,
                    c_time=video.c_time,
                    m_time=video.m_time,
                    checksum=video.checksum,
                    status=status,
                    duplicate_of_id=duplicate_of_id,
                ))
                _scan.found += 1
            except Exception as exc:
                print(f"[scan] error on '{path}': {exc}")
                _scan.errors += 1
    except asyncio.CancelledError:
        print(f"[scan] cancelled — found={_scan.found} skipped={_scan.skipped} errors={_scan.errors}")
        return
    finally:
        db.close()
        _scan.running = False
    print(f"[scan] done — found={_scan.found} skipped={_scan.skipped} errors={_scan.errors}")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WorkerRegister(BaseModel):
    config_id: str
    host: str
    api_port: int


class WorkerOut(BaseModel):
    id: int
    config_id: str
    host: str
    api_port: int


class TransferRequest(BaseModel):
    file_path: str


class ClaimRequest(BaseModel):
    worker_id: str
    count: int = 1


class ClaimOut(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_size: int | None
    c_time: float
    m_time: float
    checksum: str


class FileResultUpdate(BaseModel):
    status: FileStatus
    pid: int | None = None
    output_size: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_reason: str | None = None
    encoder: str | None = None
    avg_fps: float | None = None
    avg_speed: float | None = None


class ScanStatus(BaseModel):
    running: bool
    found: int
    skipped: int
    errors: int
    path: str


class ScanSettings(BaseModel):
    interval: int
    enabled: bool


# ---------------------------------------------------------------------------
# Worker routes
# ---------------------------------------------------------------------------

@app.post("/workers", response_model=WorkerOut, status_code=201)
def register_worker(body: WorkerRegister):
    worker = registry.register(body.config_id, body.host, body.api_port)
    print(f"[master] registered: {worker}")
    return worker


@app.get("/workers", response_model=list[WorkerOut])
def list_workers():
    return registry.all()


@app.delete("/workers/{config_id}", status_code=204)
def remove_worker(config_id: str):
    if not registry.remove_by_config_id(config_id):
        raise HTTPException(status_code=404, detail="Worker not found")


# ---------------------------------------------------------------------------
# Transfer route
# ---------------------------------------------------------------------------

@app.post("/transfer", response_model=FileRecordOut, status_code=201)
def transfer_file(body: TransferRequest, db: Session = Depends(get_db)):
    try:
        video = collect(body.file_path, _config.scan.checksum_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    existing = crud.get_record_by_checksum(db, video.checksum)
    status = FileStatus.DUPLICATE if existing else FileStatus.PENDING
    duplicate_of_id = existing.id if existing else None
    record = crud.create_file_record(db, FileRecordCreate(
        file_name=video.file_name,
        file_path=video.file_path,
        file_size=video.file_size,
        c_time=video.c_time,
        m_time=video.m_time,
        checksum=video.checksum,
        status=status,
        duplicate_of_id=duplicate_of_id,
    ))
    if existing:
        print(f"[master] duplicate '{video.file_name}' — same content as record {existing.id}")
    else:
        print(f"[master] queued '{video.file_name}'  record={record.id}")
    return record


# ---------------------------------------------------------------------------
# Job claim route
# ---------------------------------------------------------------------------

class AssignRequest(BaseModel):
    ids: list[int]
    worker_id: str


@app.post("/jobs/assign", response_model=list[ClaimOut])
def assign_jobs(body: AssignRequest, db: Session = Depends(get_db)):
    records = (
        db.query(FileRecord)
        .filter(FileRecord.id.in_(body.ids), FileRecord.status == FileStatus.PENDING)
        .all()
    )
    result = []
    for record in records:
        record.status = FileStatus.ASSIGNED
        record.worker_id = body.worker_id
        relative_path = record.file_path
        if _config.path_prefix and relative_path.startswith(_config.path_prefix):
            relative_path = relative_path[len(_config.path_prefix):]
        result.append(ClaimOut(
            id=record.id,
            file_name=record.file_name,
            file_path=relative_path,
            file_size=record.file_size,
            c_time=record.c_time,
            m_time=record.m_time,
            checksum=record.checksum,
        ))
    db.commit()
    print(f"[master] assigned {len(result)} job(s) to worker '{body.worker_id}'")
    return result


@app.post("/jobs/claim", response_model=list[ClaimOut])
def claim_jobs(body: ClaimRequest, db: Session = Depends(get_db)):
    records = (
        db.query(FileRecord)
        .filter(FileRecord.status == FileStatus.PENDING)
        .order_by(FileRecord.id)
        .limit(body.count)
        .all()
    )
    result = []
    for record in records:
        record.status = FileStatus.ASSIGNED
        record.worker_id = body.worker_id
        relative_path = record.file_path
        if _config.path_prefix and relative_path.startswith(_config.path_prefix):
            relative_path = relative_path[len(_config.path_prefix):]
        result.append(ClaimOut(
            id=record.id,
            file_name=record.file_name,
            file_path=relative_path,
            file_size=record.file_size,
            c_time=record.c_time,
            m_time=record.m_time,
            checksum=record.checksum,
        ))
    db.commit()
    print(f"[master] worker '{body.worker_id}' claimed {len(result)} job(s)")
    return result


# ---------------------------------------------------------------------------
# Result / files routes
# ---------------------------------------------------------------------------

@app.patch("/files/{record_id}/result", response_model=FileRecordOut)
def update_file_result(record_id: int, body: FileResultUpdate, db: Session = Depends(get_db)):
    record = crud.update_conversion_result(
        db, record_id,
        status=body.status,
        pid=body.pid,
        output_size=body.output_size,
        started_at=body.started_at,
        finished_at=body.finished_at,
        cancel_reason=body.cancel_reason,
        encoder=body.encoder,
        avg_fps=body.avg_fps,
        avg_speed=body.avg_speed,
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    print(f"[master] record {record_id} → {body.status.value}")
    return record


@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    return crud.get_stats(db)


@app.get("/stats/worker/{worker_id}")
def get_worker_stats(worker_id: str, db: Session = Depends(get_db)):
    return crud.get_worker_stats(db, worker_id)


@app.get("/files/duplicate-pairs")
def list_duplicate_pairs(db: Session = Depends(get_db)):
    dupes = (
        db.query(FileRecord)
        .filter(FileRecord.status == FileStatus.DUPLICATE)
        .all()
    )
    prefix = _config.path_prefix
    result = []
    for d in dupes:
        orig = crud.get_file_record(db, d.duplicate_of_id) if d.duplicate_of_id else None
        dup_path = d.file_path[len(prefix):] if prefix and d.file_path.startswith(prefix) else d.file_path
        orig_path = None
        if orig:
            orig_path = orig.file_path[len(prefix):] if prefix and orig.file_path.startswith(prefix) else orig.file_path
        result.append({
            "id": d.id,
            "file_path": dup_path,
            "duplicate_of_id": d.duplicate_of_id,
            "original_file_path": orig_path,
        })
    return result


@app.get("/files", response_model=list[FileRecordOut])
def list_files(status: FileStatus | None = None, db: Session = Depends(get_db)):
    return crud.get_all_records(db, status=status)


@app.get("/files/{record_id}", response_model=FileRecordOut)
def get_file(record_id: int, db: Session = Depends(get_db)):
    record = crud.get_file_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.patch("/files/{record_id}/status", response_model=FileRecordOut)
def update_file_status(record_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    record = crud.update_status(db, record_id, body.status)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.delete("/files/{record_id}", status_code=204)
async def delete_file(record_id: int, db: Session = Depends(get_db)):
    record = crud.get_file_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.worker_id:
        worker = registry.get_by_config_id(record.worker_id)
        if worker:
            url = f"http://{worker.host}:{worker.api_port}/files/{record_id}"
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.delete(url)
            except Exception:
                pass
    crud.delete_file_record(db, record_id)


# ---------------------------------------------------------------------------
# Scan routes
# ---------------------------------------------------------------------------

@app.post("/scan/start", response_model=ScanStatus, status_code=202)
async def scan_start():
    if _scan.running:
        raise HTTPException(status_code=409, detail="Scan already running")
    if not _config.path_prefix:
        raise HTTPException(status_code=400, detail="master.paths.prefix not configured")
    extensions = {e if e.startswith(".") else f".{e}" for e in _config.scan.extensions}
    _scan._task = asyncio.create_task(_scan_task(
        _config.path_prefix, extensions,
        _config.scan.min_size, _config.scan.max_size,
    ))
    return ScanStatus(running=True, found=0, skipped=0, errors=0, path=_config.path_prefix)


@app.post("/scan/stop", response_model=ScanStatus)
def scan_stop():
    if not _scan.cancel():
        raise HTTPException(status_code=409, detail="No scan running")
    return ScanStatus(running=_scan.running, found=_scan.found, skipped=_scan.skipped,
                      errors=_scan.errors, path=_config.path_prefix)


@app.get("/scan/status", response_model=ScanStatus)
def scan_status():
    return ScanStatus(running=_scan.running, found=_scan.found, skipped=_scan.skipped,
                      errors=_scan.errors, path=_config.path_prefix)


# ---------------------------------------------------------------------------
# Periodic scan settings
# ---------------------------------------------------------------------------

@app.get("/scan/settings", response_model=ScanSettings)
def get_scan_settings(db: Session = Depends(get_db)):
    return ScanSettings(
        interval=int(get_setting(db, "scan_interval_seconds") or "60"),
        enabled=get_setting(db, "scan_periodic_enabled") == "true",
    )


@app.post("/scan/settings", response_model=ScanSettings)
def update_scan_settings(body: ScanSettings, db: Session = Depends(get_db)):
    interval = max(10, body.interval)
    set_setting(db, "scan_interval_seconds", str(interval))
    set_setting(db, "scan_periodic_enabled", "true" if body.enabled else "false")
    return ScanSettings(interval=interval, enabled=body.enabled)
