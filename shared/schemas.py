from datetime import datetime

from pydantic import BaseModel

from .models import FileStatus


class FileRecordCreate(BaseModel):
    id: int | None = None       # Set by master; slave uses master's ID
    slave_id: str | None = None # Which slave holds this file
    file_name: str
    file_path: str
    file_size: int | None = None
    c_time: float
    m_time: float
    checksum: str
    status: FileStatus = FileStatus.PENDING
    duplicate_of_id: int | None = None


class FileRecordOut(BaseModel):
    id: int
    file_name: str
    file_path: str
    c_time: float
    m_time: float
    checksum: str
    slave_id: str | None
    status: FileStatus
    file_size: int | None
    cancel_reason: str | None
    pid: int | None
    output_size: int | None
    encoder: str | None
    avg_fps: float | None
    avg_speed: float | None
    duplicate_of_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: FileStatus
