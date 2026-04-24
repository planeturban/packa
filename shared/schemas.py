from datetime import datetime

from pydantic import BaseModel

from .models import FileStatus


class FileRecordCreate(BaseModel):
    id: int | None = None       # Set by master; worker uses master's ID
    worker_id: str | None = None # Which worker holds this file
    file_name: str
    file_path: str
    file_size: int | None = None
    c_time: float
    m_time: float
    checksum: str = ""
    status: FileStatus = FileStatus.PENDING
    duplicate_of_id: int | None = None
    width: int | None = None
    height: int | None = None
    bitrate: int | None = None
    duration: float | None = None


class FileRecordOut(BaseModel):
    id: int
    file_name: str
    file_path: str
    c_time: float
    m_time: float
    checksum: str
    worker_id: str | None
    status: FileStatus
    file_size: int | None
    cancel_reason: str | None
    cancel_detail: str | None = None
    discard_reason: str | None = None
    force_encode: bool = False
    pid: int | None
    output_size: int | None
    encoder: str | None
    avg_fps: float | None
    avg_speed: float | None
    duplicate_of_id: int | None
    width: int | None
    height: int | None
    bitrate: int | None
    duration: float | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: FileStatus
    force_encode: bool = False
