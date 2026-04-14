"""
Master REST API.

  POST   /slaves               — slave registration
  GET    /slaves               — list registered slaves
  DELETE /slaves/{id}          — deregister a slave
  POST   /transfer             — send file metadata to the next slave
  POST   /files/{id}/sync      — slave notifies master that conversion is done;
                                 master fetches the record from slave and updates its DB
  GET    /files                — list all records in master DB
  GET    /files/{id}           — get a single record from master DB
"""

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import crud
from shared.base import Base
from shared.config import Config
from shared.models import FileStatus
from shared.schemas import FileRecordCreate, FileRecordOut

from .database import engine, get_db
from .registry import registry
from .scanner import collect
from .sender import send_metadata

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Packa Master API")

_config: Config = Config()


def set_config(config: Config) -> None:
    global _config
    _config = config


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SlaveRegister(BaseModel):
    config_id: str
    host: str
    api_port: int
    file_port: int


class SlaveOut(BaseModel):
    id: int
    config_id: str
    host: str
    api_port: int
    file_port: int


class TransferRequest(BaseModel):
    file_path: str


class TransferOut(BaseModel):
    record_id: int
    slave_id: int
    slave_host: str
    file_name: str
    file_path: str
    checksum: str


# ---------------------------------------------------------------------------
# Slave registration routes
# ---------------------------------------------------------------------------

@app.post("/slaves", response_model=SlaveOut, status_code=201)
def register_slave(body: SlaveRegister):
    slave = registry.register(body.config_id, body.host, body.api_port, body.file_port)
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

@app.post("/transfer", response_model=TransferOut, status_code=201)
async def transfer_file(body: TransferRequest, db: Session = Depends(get_db)):
    slave = registry.next_slave()
    if slave is None:
        raise HTTPException(status_code=503, detail="No slaves registered")

    try:
        video = collect(body.file_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Create record in master DB using the full local path.
    master_record = crud.create_file_record(db, FileRecordCreate(
        slave_id=slave.config_id,
        file_name=video.file_name,
        file_path=video.file_path,
        c_time=video.c_time,
        m_time=video.m_time,
        checksum=video.checksum,
    ))

    # Send to slave with master prefix stripped from file_path.
    await send_metadata(master_record.id, video, slave, path_prefix=_config.path_prefix)

    print(f"[master] '{video.file_name}' → {slave}  record={master_record.id}")
    return TransferOut(
        record_id=master_record.id,
        slave_id=slave.id,
        slave_host=slave.host,
        file_name=video.file_name,
        file_path=video.file_path,
        checksum=video.checksum,
    )


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

    url = f"http://{slave.host}:{slave.api_port}/files/{record_id}"
    async with httpx.AsyncClient(timeout=10) as client:
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
def list_files(db: Session = Depends(get_db)):
    return crud.get_all_records(db)


@app.get("/files/{record_id}", response_model=FileRecordOut)
def get_file(record_id: int, db: Session = Depends(get_db)):
    record = crud.get_file_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record
