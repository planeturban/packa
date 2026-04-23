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
  GET    /master/config        — running master configuration (layered: default<file<env<db<cli)
  PATCH  /master/config/{key}  — write an override to the database
  DELETE /master/config/{key}  — clear the database override, revert via priority
  POST   /master/config/{key}/restore — copy file/env/default value into the database
  GET    /master/stats         — probe rate, scan rate, scanning queue depth
"""

import asyncio
import time as _time
from collections import deque
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

from . import config_store
from .database import SessionLocal, engine, get_db
from .registry import registry
from .scanner import collect
from .tls_manager import (
    consume_token, generate_token, get_ca_fingerprint,
    get_token_info, issue_client_cert, renew_client_cert,
)

Base.metadata.create_all(bind=engine)
migrate(engine)

_last_periodic_start: datetime | None = None


# ---------------------------------------------------------------------------
# Startup / background tasks
# ---------------------------------------------------------------------------

def _recover() -> None:
    """Reset stuck PROCESSING records to PENDING and SCANNING records to SCANNING (re-probe) on startup."""
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

        unprobed = (
            db.query(FileRecord)
            .filter(FileRecord.status == FileStatus.SCANNING)
            .count()
        )
        if unprobed:
            print(f"[master] {unprobed} SCANNING record(s) pending probe")
    finally:
        db.close()


_hevc_cursor: int = 0  # last record id checked; resets each full cycle
_probe_window: deque[tuple[float, int]] = deque()  # (monotonic_time, count)


def _record_probes(n: int) -> None:
    now = _time.monotonic()
    _probe_window.append((now, n))
    cutoff = now - 60.0
    while _probe_window and _probe_window[0][0] < cutoff:
        _probe_window.popleft()


def _probe_rate_per_min() -> float | None:
    if not _probe_window:
        return None
    now = _time.monotonic()
    recent = [(t, c) for t, c in _probe_window if t >= now - 60.0]
    if not recent:
        return None
    total = sum(c for _, c in recent)
    elapsed = now - recent[0][0]
    if elapsed < 1.0:
        return None
    return round(total / elapsed * 60, 1)


async def _probe_codec(file_path: str) -> tuple[str, int | None, int | None, int | None, float | None]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height:format=bit_rate,duration",
            "-of", "default=noprint_wrappers=1",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        info = {}
        for line in stdout.decode().splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip()
        codec = info.get("codec_name", "").lower()
        width = int(info["width"]) if info.get("width", "").isdigit() else None
        height = int(info["height"]) if info.get("height", "").isdigit() else None
        bitrate = int(info["bit_rate"]) if info.get("bit_rate", "").isdigit() else None
        dur_s = info.get("duration", "")
        duration = float(dur_s) if dur_s.replace(".", "", 1).isdigit() else None
        return codec, width, height, bitrate, duration
    except Exception:
        return "", None, None, None, None


async def _hevc_check_loop() -> None:
    """Cursor-based loop: probe all SCANNING records, 20 at a time concurrently."""
    global _hevc_cursor
    await asyncio.sleep(15)
    while True:
        db = SessionLocal()
        try:
            records = (
                db.query(FileRecord)
                .filter(
                    FileRecord.status == FileStatus.SCANNING,
                    FileRecord.id > _hevc_cursor,
                )
                .order_by(FileRecord.id)
                .limit(_config.scan.probe_batch_size)
                .all()
            )
            if not records:
                _hevc_cursor = 0
                await asyncio.sleep(_config.scan.probe_interval)
                continue
            probes = await asyncio.gather(*[_probe_codec(r.file_path) for r in records])
            for record, (codec, width, height, bitrate, duration) in zip(records, probes):
                record.width = width
                record.height = height
                record.bitrate = bitrate
                record.duration = duration
                if codec == "hevc":
                    record.status = FileStatus.DISCARDED
                    record.finished_at = datetime.now(timezone.utc)
                    print(f"[master] record {record.id} discarded — already HEVC ({record.file_name!r})")
                else:
                    record.status = FileStatus.PENDING
            db.commit()
            _hevc_cursor = records[-1].id
            _record_probes(len(records))
        finally:
            db.close()
        await asyncio.sleep(0)


async def _periodic_scan_loop() -> None:
    global _last_periodic_start
    while True:
        await asyncio.sleep(5)
        if not _config.path_prefix or not _config.scan.periodic_enabled or _scan.running:
            continue
        interval = max(10, _config.scan.periodic_interval)
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
_config_path: str | None = None
_cli_values: dict = {}


def set_config(config: Config) -> None:
    global _config
    _config = config


def set_config_layers(config_path: str | None, cli_values: dict) -> None:
    global _config_path, _cli_values
    _config_path = config_path
    _cli_values = dict(cli_values)


# ---------------------------------------------------------------------------
# Scan state
# ---------------------------------------------------------------------------

class _ScanState:
    def __init__(self) -> None:
        self.running: bool = False
        self.found: int = 0
        self.skipped: int = 0
        self.errors: int = 0
        self.started_at: float | None = None  # monotonic
        self._task: asyncio.Task | None = None

    def cancel(self) -> bool:
        if self._task and not self._task.done():
            self._task.cancel()
            return True
        return False

    def scan_rate(self) -> float | None:
        if not self.running or self.started_at is None:
            return None
        elapsed = _time.monotonic() - self.started_at
        if elapsed < 1.0:
            return None
        processed = self.found + self.skipped
        return round(processed / elapsed, 1)


_scan = _ScanState()


async def _scan_task(scan_dir: str, extensions: set[str], min_size: int, max_size: int) -> None:
    from pathlib import Path
    _scan.running = True
    _scan.found = _scan.skipped = _scan.errors = 0
    _scan.started_at = _time.monotonic()
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
                status = FileStatus.DUPLICATE if existing else FileStatus.SCANNING
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
    config_id: str = ""
    host: str
    api_port: int
    scheme: str = "http"


class WorkerOut(BaseModel):
    id: int
    config_id: str
    host: str
    api_port: int
    scheme: str = "http"


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
    duration: float | None


class FileResultUpdate(BaseModel):
    status: FileStatus
    pid: int | None = None
    output_size: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_reason: str | None = None
    cancel_detail: str | None = None
    encoder: str | None = None
    avg_fps: float | None = None
    avg_speed: float | None = None
    width: int | None = None
    height: int | None = None
    bitrate: int | None = None
    duration: float | None = None


class ScanStatus(BaseModel):
    running: bool
    found: int
    skipped: int
    errors: int
    path: str


# ---------------------------------------------------------------------------
# Worker routes
# ---------------------------------------------------------------------------

@app.post("/workers", response_model=WorkerOut, status_code=201)
def register_worker(body: WorkerRegister):
    worker = registry.register(body.config_id, body.host, body.api_port, body.scheme)
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
    status = FileStatus.DUPLICATE if existing else FileStatus.SCANNING
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
            duration=record.duration,
        ))
    db.commit()
    print(f"[master] assigned {len(result)} job(s) to worker '{body.worker_id}'")
    return result


@app.post("/jobs/claim", response_model=list[ClaimOut])
def claim_jobs(body: ClaimRequest, db: Session = Depends(get_db)):
    records = (
        db.query(FileRecord)
        .filter(FileRecord.status == FileStatus.PENDING, FileRecord.duration.isnot(None))
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
            duration=record.duration,
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
        cancel_detail=body.cancel_detail,
        encoder=body.encoder,
        avg_fps=body.avg_fps,
        avg_speed=body.avg_speed,
        width=body.width,
        height=body.height,
        bitrate=body.bitrate,
        duration=body.duration,
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


@app.get("/master/config")
def get_master_config(db: Session = Depends(get_db)):
    file_values = config_store.read_file_values(_config_path)
    env_values = config_store.read_env_values()
    db_values = config_store.read_db_values(db)
    effective, sources = config_store.compute_effective(
        file_values, env_values, db_values, _cli_values,
    )
    return {
        "fields": config_store.fields_for_api(),
        "values": effective,
        "sources": sources,
        "file": file_values,
        "env": env_values,
        "db": db_values,
        "cli": _cli_values,
        "config_file": _config_path,
    }


class ConfigValueUpdate(BaseModel):
    value: object


class ConfigRestore(BaseModel):
    source: str  # "file" | "env" | "default"


def _reapply_config(db: Session) -> None:
    """Recompute effective config from all layers and update the live _config."""
    file_values = config_store.read_file_values(_config_path)
    env_values = config_store.read_env_values()
    db_values = config_store.read_db_values(db)
    effective, _ = config_store.compute_effective(
        file_values, env_values, db_values, _cli_values,
    )
    config_store.apply_to_config(effective, _config)


@app.patch("/master/config/{key}")
def update_master_config(key: str, body: ConfigValueUpdate, db: Session = Depends(get_db)):
    fld = config_store.field(key)
    if fld is None:
        raise HTTPException(status_code=404, detail=f"Unknown key {key!r}")
    try:
        config_store.set_db_value(db, key, body.value)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid value for {key!r}: {exc}")
    _reapply_config(db)
    print(f"[master] config {key!r} set via DB (requires_restart={fld.requires_restart})")
    return {"ok": True, "requires_restart": fld.requires_restart}


@app.delete("/master/config/{key}")
def clear_master_config(key: str, db: Session = Depends(get_db)):
    fld = config_store.field(key)
    if fld is None:
        raise HTTPException(status_code=404, detail=f"Unknown key {key!r}")
    removed = config_store.delete_db_value(db, key)
    _reapply_config(db)
    print(f"[master] config {key!r} DB override {'cleared' if removed else 'was already unset'}")
    return {"ok": True, "cleared": removed, "requires_restart": fld.requires_restart}


@app.post("/master/config/{key}/restore")
def restore_master_config(key: str, body: ConfigRestore, db: Session = Depends(get_db)):
    fld = config_store.field(key)
    if fld is None:
        raise HTTPException(status_code=404, detail=f"Unknown key {key!r}")
    source = body.source
    if source == "file":
        vals = config_store.read_file_values(_config_path)
    elif source == "env":
        vals = config_store.read_env_values()
    elif source == "default":
        vals = config_store.default_values()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown source {source!r}")
    if key not in vals:
        raise HTTPException(status_code=404, detail=f"No value for {key!r} in {source}")
    config_store.set_db_value(db, key, vals[key])
    _reapply_config(db)
    print(f"[master] config {key!r} restored from {source}")
    return {"ok": True, "value": vals[key], "requires_restart": fld.requires_restart}


@app.post("/restart")
def restart_master():
    import os, signal, threading
    threading.Thread(target=lambda: (
        __import__('time').sleep(0.2),
        os.kill(os.getpid(), signal.SIGTERM)
    ), daemon=True).start()
    return {"ok": True}


@app.get("/master/stats")
def get_master_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func as _func
    scanning_queue = (
        db.query(_func.count(FileRecord.id))
        .filter(FileRecord.status == FileStatus.SCANNING)
        .scalar() or 0
    )
    overall = crud.get_stats(db).get("overall", {})
    return {
        "scanning_queue": scanning_queue,
        "probe_rate_per_min": _probe_rate_per_min(),
        "scan_rate_per_s": _scan.scan_rate(),
        "avg_conversion_s": overall.get("avg_duration_seconds"),
        "avg_fps": overall.get("avg_fps"),
    }


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
            from shared.tls import scheme as _scheme
            url = f"{_scheme(_config.tls)}://{worker.host}:{worker.api_port}/files/{record_id}"
            try:
                async with httpx.AsyncClient(timeout=5, **_config.tls.httpx_kwargs()) as client:
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
# TLS bootstrap and token management
# ---------------------------------------------------------------------------

class BootstrapRequest(BaseModel):
    token: str
    cn: str = "node"


class CertBundle(BaseModel):
    cert_pem: str
    key_pem: str
    ca_pem: str


@app.post("/bootstrap", response_model=CertBundle)
def bootstrap_node(body: BootstrapRequest, db: Session = Depends(get_db)):
    """Exchange a valid bootstrap token for a client cert bundle (TLS must be enabled)."""
    if _config.tls.disabled:
        raise HTTPException(status_code=400, detail="TLS is disabled on this master")
    if not consume_token(db, body.token):
        raise HTTPException(status_code=401, detail="Invalid or expired bootstrap token")
    cn = body.cn or "node"
    cert_pem, key_pem, ca_pem = issue_client_cert(db, cn)
    print(f"[tls] issued cert for {cn!r}")
    return CertBundle(cert_pem=cert_pem, key_pem=key_pem, ca_pem=ca_pem)


@app.get("/tls/token")
def get_tls_token(db: Session = Depends(get_db)):
    """Return current bootstrap token info, or empty dict if none/expired."""
    return get_token_info(db) or {}


@app.post("/tls/token")
def create_tls_token(db: Session = Depends(get_db)):
    """Generate a new bootstrap token (10-minute TTL, multi-use within window)."""
    token = generate_token(db)
    info = get_token_info(db)
    print(f"[tls] new bootstrap token: {token}")
    return info


@app.get("/tls/status")
def get_tls_status(db: Session = Depends(get_db)):
    """Return TLS state and CA fingerprint."""
    fp = get_ca_fingerprint(db)
    return {
        "enabled": not _config.tls.disabled,
        "ca_fingerprint": fp,
    }
