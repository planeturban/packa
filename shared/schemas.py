from datetime import datetime

from pydantic import BaseModel

from .models import FileStatus


class FileRecordCreate(BaseModel):
    id: int | None = None       # Set by master; slave uses master's ID
    slave_id: str | None = None # Which slave holds this file
    file_name: str
    file_path: str
    c_time: float
    m_time: float
    checksum: str


class FileRecordOut(BaseModel):
    id: int
    file_name: str
    file_path: str
    c_time: float
    m_time: float
    checksum: str
    slave_id: str | None
    status: FileStatus
    pid: int | None
    output_size: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: FileStatus
