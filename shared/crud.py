from datetime import datetime

from sqlalchemy.orm import Session

from .models import FileRecord, FileStatus
from .schemas import FileRecordCreate


def create_file_record(db: Session, record: FileRecordCreate) -> FileRecord:
    kwargs = dict(
        file_name=record.file_name,
        file_path=record.file_path,
        c_time=record.c_time,
        m_time=record.m_time,
        checksum=record.checksum,
    )
    if record.id is not None:
        kwargs["id"] = record.id
    if record.slave_id is not None:
        kwargs["slave_id"] = record.slave_id

    db_record = FileRecord(**kwargs)
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


def get_file_record(db: Session, record_id: int) -> FileRecord | None:
    return db.query(FileRecord).filter(FileRecord.id == record_id).first()


def get_record_by_path(db: Session, file_path: str) -> FileRecord | None:
    return db.query(FileRecord).filter(FileRecord.file_path == file_path).first()


def get_all_records(db: Session, status: FileStatus | None = None) -> list[FileRecord]:
    q = db.query(FileRecord)
    if status is not None:
        q = q.filter(FileRecord.status == status)
    return q.all()


def update_status(db: Session, record_id: int, status: FileStatus) -> FileRecord | None:
    record = get_file_record(db, record_id)
    if record:
        record.status = status
        db.commit()
        db.refresh(record)
    return record


def update_conversion_result(
    db: Session,
    record_id: int,
    status: FileStatus,
    pid: int | None,
    output_size: int | None,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> FileRecord | None:
    record = get_file_record(db, record_id)
    if record:
        record.status = status
        record.pid = pid
        record.output_size = output_size
        record.started_at = started_at
        record.finished_at = finished_at
        db.commit()
        db.refresh(record)
    return record
