from datetime import datetime

from sqlalchemy import func
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
        status=record.status,
    )
    if record.id is not None:
        kwargs["id"] = record.id
    if record.slave_id is not None:
        kwargs["slave_id"] = record.slave_id
    if record.file_size is not None:
        kwargs["file_size"] = record.file_size
    if record.duplicate_of_id is not None:
        kwargs["duplicate_of_id"] = record.duplicate_of_id

    db_record = FileRecord(**kwargs)
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


def get_file_record(db: Session, record_id: int) -> FileRecord | None:
    return db.query(FileRecord).filter(FileRecord.id == record_id).first()


def get_record_by_path(db: Session, file_path: str) -> FileRecord | None:
    return db.query(FileRecord).filter(FileRecord.file_path == file_path).first()


def get_record_by_checksum(db: Session, checksum: str) -> FileRecord | None:
    """Return an existing non-duplicate record with the given checksum, if any."""
    return (
        db.query(FileRecord)
        .filter(FileRecord.checksum == checksum, FileRecord.status != FileStatus.DUPLICATE)
        .first()
    )


def get_all_records(db: Session, status: FileStatus | None = None) -> list[FileRecord]:
    q = db.query(FileRecord)
    if status is not None:
        q = q.filter(FileRecord.status == status)
    return q.all()


def delete_file_record(db: Session, record_id: int) -> bool:
    record = get_file_record(db, record_id)
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True


def update_status(db: Session, record_id: int, status: FileStatus) -> FileRecord | None:
    record = get_file_record(db, record_id)
    if record:
        record.status = status
        db.commit()
        db.refresh(record)
    return record


def get_stats(db: Session) -> dict:
    _dur = (func.julianday(FileRecord.finished_at) - func.julianday(FileRecord.started_at)) * 86400
    _f = [
        FileRecord.status == FileStatus.COMPLETE,
        FileRecord.file_size.isnot(None),
        FileRecord.output_size.isnot(None),
        FileRecord.started_at.isnot(None),
        FileRecord.finished_at.isnot(None),
    ]

    jobs, total_in, total_out, avg_dur = db.query(
        func.count(FileRecord.id),
        func.sum(FileRecord.file_size),
        func.sum(FileRecord.output_size),
        func.avg(_dur),
    ).filter(*_f).one()
    jobs, total_in, total_out = jobs or 0, total_in or 0, total_out or 0

    overall = {
        "jobs": jobs,
        "total_input_bytes": total_in,
        "total_output_bytes": total_out,
        "total_saved_bytes": total_in - total_out,
        "avg_duration_seconds": round(avg_dur or 0, 1),
        "avg_compression_ratio": round(total_out / total_in, 3) if total_in else 0.0,
    }

    by_encoder: dict = {}
    for enc, j, in_b, out_b, dur in db.query(
        FileRecord.encoder, func.count(FileRecord.id),
        func.sum(FileRecord.file_size), func.sum(FileRecord.output_size), func.avg(_dur),
    ).filter(*_f).group_by(FileRecord.encoder).all():
        in_b, out_b = in_b or 0, out_b or 0
        by_encoder[enc or "unknown"] = {
            "jobs": j or 0,
            "total_input_bytes": in_b,
            "total_output_bytes": out_b,
            "total_saved_bytes": in_b - out_b,
            "avg_duration_seconds": round(dur or 0, 1),
            "avg_compression_ratio": round(out_b / in_b, 3) if in_b else 0.0,
        }

    by_slave = []
    for sid, j, in_b, out_b, dur in db.query(
        FileRecord.slave_id, func.count(FileRecord.id),
        func.sum(FileRecord.file_size), func.sum(FileRecord.output_size), func.avg(_dur),
    ).filter(*_f).group_by(FileRecord.slave_id).all():
        in_b, out_b = in_b or 0, out_b or 0
        by_slave.append({
            "slave_id": sid or "unknown",
            "jobs": j or 0,
            "total_saved_bytes": in_b - out_b,
            "avg_compression_ratio": round(out_b / in_b, 3) if in_b else 0.0,
            "avg_duration_seconds": round(dur or 0, 1),
        })

    by_day = []
    _day_f = [
        FileRecord.status == FileStatus.COMPLETE,
        FileRecord.file_size.isnot(None),
        FileRecord.output_size.isnot(None),
        FileRecord.finished_at.isnot(None),
    ]
    day_label = func.strftime('%Y-%m-%d', FileRecord.finished_at).label('day')
    for day, j, saved in db.query(
        day_label, func.count(FileRecord.id),
        func.sum(FileRecord.file_size) - func.sum(FileRecord.output_size),
    ).filter(*_day_f).group_by('day').order_by('day').all():
        by_day.append({"date": day, "jobs": j or 0, "saved_bytes": saved or 0})

    return {"overall": overall, "by_encoder": by_encoder, "by_slave": by_slave, "by_day": by_day}


def get_slave_stats(db: Session, slave_id: str) -> dict:
    _dur = (func.julianday(FileRecord.finished_at) - func.julianday(FileRecord.started_at)) * 86400
    _f = [
        FileRecord.status == FileStatus.COMPLETE,
        FileRecord.slave_id == slave_id,
        FileRecord.file_size.isnot(None),
        FileRecord.output_size.isnot(None),
        FileRecord.started_at.isnot(None),
        FileRecord.finished_at.isnot(None),
    ]

    jobs, total_in, total_out, avg_dur = db.query(
        func.count(FileRecord.id),
        func.sum(FileRecord.file_size),
        func.sum(FileRecord.output_size),
        func.avg(_dur),
    ).filter(*_f).one()
    jobs, total_in, total_out = jobs or 0, total_in or 0, total_out or 0

    overall = {
        "jobs": jobs,
        "total_input_bytes": total_in,
        "total_output_bytes": total_out,
        "total_saved_bytes": total_in - total_out,
        "avg_duration_seconds": round(avg_dur or 0, 1),
        "avg_compression_ratio": round(total_out / total_in, 3) if total_in else 0.0,
    }

    _ratio = FileRecord.output_size * 1.0 / FileRecord.file_size

    by_encoder: dict = {}
    for row in db.query(
        FileRecord.encoder,
        func.count(FileRecord.id),
        func.sum(FileRecord.file_size) - func.sum(FileRecord.output_size),
        func.min(_dur), func.max(_dur),
        func.min(FileRecord.avg_fps), func.max(FileRecord.avg_fps),
        func.min(FileRecord.avg_speed), func.max(FileRecord.avg_speed),
        func.min(_ratio), func.max(_ratio),
    ).filter(*_f).group_by(FileRecord.encoder).all():
        enc, j, saved, min_dur, max_dur, min_fps, max_fps, min_spd, max_spd, min_ratio, max_ratio = row
        by_encoder[enc or "unknown"] = {
            "jobs": j or 0,
            "total_saved_bytes": saved or 0,
            "min_duration_seconds": round(min_dur or 0, 1),
            "max_duration_seconds": round(max_dur or 0, 1),
            "min_fps": round(min_fps, 1) if min_fps is not None else None,
            "max_fps": round(max_fps, 1) if max_fps is not None else None,
            "min_speed": round(min_spd, 2) if min_spd is not None else None,
            "max_speed": round(max_spd, 2) if max_spd is not None else None,
            "min_size_ratio": round(min_ratio, 3) if min_ratio is not None else None,
            "max_size_ratio": round(max_ratio, 3) if max_ratio is not None else None,
        }

    _day_f = [
        FileRecord.status == FileStatus.COMPLETE,
        FileRecord.slave_id == slave_id,
        FileRecord.file_size.isnot(None),
        FileRecord.output_size.isnot(None),
        FileRecord.finished_at.isnot(None),
    ]
    day_label = func.strftime('%Y-%m-%d', FileRecord.finished_at).label('day')
    by_day = [
        {"date": day, "jobs": j or 0, "saved_bytes": saved or 0}
        for day, j, saved in db.query(
            day_label, func.count(FileRecord.id),
            func.sum(FileRecord.file_size) - func.sum(FileRecord.output_size),
        ).filter(*_day_f).group_by('day').order_by('day').all()
    ]

    return {"slave_id": slave_id, "overall": overall, "by_encoder": by_encoder, "by_day": by_day}


def update_conversion_result(
    db: Session,
    record_id: int,
    status: FileStatus,
    pid: int | None,
    output_size: int | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    cancel_reason: str | None = None,
    encoder: str | None = None,
    avg_fps: float | None = None,
    avg_speed: float | None = None,
) -> FileRecord | None:
    record = get_file_record(db, record_id)
    if record:
        record.status = status
        record.pid = pid
        record.output_size = output_size
        record.started_at = started_at
        record.finished_at = finished_at
        record.cancel_reason = cancel_reason
        if encoder is not None:
            record.encoder = encoder
        if avg_fps is not None:
            record.avg_fps = avg_fps
        if avg_speed is not None:
            record.avg_speed = avg_speed
        db.commit()
        db.refresh(record)
    return record
