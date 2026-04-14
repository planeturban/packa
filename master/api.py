"""
Master REST API.

  POST   /slaves               — slave registration
  GET    /slaves               — list registered slaves
  DELETE /slaves/{id}          — deregister a slave
  POST   /transfer             — accept a file path and create a PENDING record
  POST   /jobs/claim           — slave claims N pending jobs (pull model)
  POST   /files/{id}/sync      — slave notifies master that conversion is done;
                                 master fetches the record from slave and updates its DB
  GET    /files[?status=]      — list records in master DB, filterable by status
  GET    /files/{id}           — get a single record from master DB
  POST   /scan/start           — start background directory scan
  POST   /scan/stop            — cancel running scan
  GET    /scan/status          — show scan progress
"""

import asyncio

import httpx
from fastapi import Depends, FastAPI, HTTPException
from shared.tls import httpx_kwargs, scheme
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import crud
from shared.base import Base
from shared.config import Config
from shared.models import FileRecord, FileStatus
from shared.schemas import FileRecordCreate, FileRecordOut

from .database import SessionLocal, engine, get_db
from .registry import registry
from .scanner import collect

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Packa Master API")

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
        self.found: int = 0    # new records created
        self.skipped: int = 0  # already existed in DB
        self.errors: int = 0   # collect() failures
        self._task: asyncio.Task | None = None

    def cancel(self) -> bool:
        if self._task and not self._task.done():
            self._task.cancel()
            return True
        return False


_scan = _ScanState()


async def _scan_task(scan_dir: str, extensions: set[str]) -> None:
    from pathlib import Path
    _scan.running = True
    _scan.found = 0
    _scan.skipped = 0
    _scan.errors = 0
    print(f"[scan] starting in '{scan_dir}' (extensions: {sorted(extensions)})")
    db = SessionLocal()
    try:
        for path in Path(scan_dir).rglob("*"):
            await asyncio.sleep(0)  # yield to event loop between files
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            if crud.get_record_by_path(db, str(path)):
                _scan.skipped += 1
                continue
            try:
                video = collect(str(path))
                crud.create_file_record(db, FileRecordCreate(
                    file_name=video.file_name,
                    file_path=video.file_path,
                    c_time=video.c_time,
                    m_time=video.m_time,
                    checksum=video.checksum,
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

class SlaveRegister(BaseModel):
    config_id: str
    host: str
    api_port: int


class SlaveOut(BaseModel):
    id: int
    config_id: str
    host: str
    api_port: int


class TransferRequest(BaseModel):
    file_path: str


class ClaimRequest(BaseModel):
    slave_id: str  # slave's config_id string
    count: int = 1


class ClaimOut(BaseModel):
    id: int
    file_name: str
    file_path: str   # relative path (master prefix stripped)
    c_time: float
    m_time: float
    checksum: str


# ---------------------------------------------------------------------------
# Slave registration routes
# ---------------------------------------------------------------------------

@app.post("/slaves", response_model=SlaveOut, status_code=201)
def register_slave(body: SlaveRegister):
    slave = registry.register(body.config_id, body.host, body.api_port)
    print(f"[master] registered: {slave}")
    return slave


@app.get("/slaves", response_model=list[SlaveOut])
def list_slaves():
    return registry.all()


@app.delete("/slaves/{slave_id}", status_code=204)
def remove_slave(slave_id: int):
    if not registry.remove(slave_id):
        raise HTTPException(status_code=404, detail="Slave not found")


# ---------------------------------------------------------------------------
# Transfer route
# ---------------------------------------------------------------------------

@app.post("/transfer", response_model=FileRecordOut, status_code=201)
def transfer_file(body: TransferRequest, db: Session = Depends(get_db)):
    try:
        video = collect(body.file_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    record = crud.create_file_record(db, FileRecordCreate(
        file_name=video.file_name,
        file_path=video.file_path,
        c_time=video.c_time,
        m_time=video.m_time,
        checksum=video.checksum,
    ))
    print(f"[master] queued '{video.file_name}'  record={record.id}")
    return record


# ---------------------------------------------------------------------------
# Job claim route — slaves pull work from master
# ---------------------------------------------------------------------------

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
        record.slave_id = body.slave_id
        relative_path = record.file_path
        if _config.path_prefix and relative_path.startswith(_config.path_prefix):
            relative_path = relative_path[len(_config.path_prefix):]
        result.append(ClaimOut(
            id=record.id,
            file_name=record.file_name,
            file_path=relative_path,
            c_time=record.c_time,
            m_time=record.m_time,
            checksum=record.checksum,
        ))
    db.commit()
    print(f"[master] slave '{body.slave_id}' claimed {len(result)} job(s)")
    return result


# ---------------------------------------------------------------------------
# Sync route — called by slave after conversion
# ---------------------------------------------------------------------------

class SyncRequest(BaseModel):
    slave_id: int


@app.post("/files/{record_id}/sync", response_model=FileRecordOut)
async def sync_file(record_id: int, body: SyncRequest, db: Session = Depends(get_db)):
    slave = registry.get(body.slave_id)
    if slave is None:
        raise HTTPException(status_code=404, detail="Slave not found")

    url = f"{scheme(_config.tls)}://{slave.host}:{slave.api_port}/files/{record_id}"
    async with httpx.AsyncClient(timeout=10, **httpx_kwargs(_config.tls)) as client:
        response = await client.get(url)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Record not found on slave")
        response.raise_for_status()
        slave_data = response.json()

    record = crud.update_conversion_result(
        db,
        record_id=record_id,
        status=FileStatus(slave_data["status"]),
        pid=slave_data.get("pid"),
        output_size=slave_data.get("output_size"),
        started_at=slave_data.get("started_at"),
        finished_at=slave_data.get("finished_at"),
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found in master DB")

    print(f"[master] synced record {record_id} from slave-{body.slave_id}: {record.status.value}")
    return record


# ---------------------------------------------------------------------------
# Master DB read routes
# ---------------------------------------------------------------------------

@app.get("/files", response_model=list[FileRecordOut])
def list_files(status: FileStatus | None = None, db: Session = Depends(get_db)):
    return crud.get_all_records(db, status=status)


@app.get("/files/{record_id}", response_model=FileRecordOut)
def get_file(record_id: int, db: Session = Depends(get_db)):
    record = crud.get_file_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


# ---------------------------------------------------------------------------
# Scan routes
# ---------------------------------------------------------------------------

class ScanStatus(BaseModel):
    running: bool
    found: int
    skipped: int
    errors: int


@app.post("/scan/start", response_model=ScanStatus, status_code=202)
async def scan_start():
    if _scan.running:
        raise HTTPException(status_code=409, detail="Scan already running")
    if not _config.path_prefix:
        raise HTTPException(status_code=400, detail="master.paths.prefix not configured")
    extensions = {e if e.startswith(".") else f".{e}" for e in _config.scan.extensions}
    _scan._task = asyncio.create_task(_scan_task(_config.path_prefix, extensions))
    return ScanStatus(running=True, found=0, skipped=0, errors=0)


@app.post("/scan/stop", response_model=ScanStatus)
def scan_stop():
    if not _scan.cancel():
        raise HTTPException(status_code=409, detail="No scan running")
    return ScanStatus(running=_scan.running, found=_scan.found, skipped=_scan.skipped, errors=_scan.errors)


@app.get("/scan/status", response_model=ScanStatus)
def scan_status():
    return ScanStatus(running=_scan.running, found=_scan.found, skipped=_scan.skipped, errors=_scan.errors)
