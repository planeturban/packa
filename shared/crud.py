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
    if record.worker_id is not None:
        kwargs["worker_id"] = record.worker_id
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
    if not checksum:
        return None
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


def get_status_counts(db: Session) -> dict:
    """Return per-status counts and per-worker complete/error counts in two queries."""
    rows = db.query(FileRecord.status, func.count()).group_by(FileRecord.status).all()
    by_status = {s.value: 0 for s in FileStatus}
    for status, count in rows:
        by_status[status.value] = count

    worker_rows = (
        db.query(FileRecord.worker_id, FileRecord.status, func.count())
        .filter(FileRecord.status.in_([FileStatus.COMPLETE, FileStatus.ERROR]))
        .filter(FileRecord.worker_id.isnot(None))
        .group_by(FileRecord.worker_id, FileRecord.status)
        .all()
    )
    worker_stats: dict[str, dict] = {}
    for worker_id, status, count in worker_rows:
        w = worker_stats.setdefault(worker_id, {"complete": 0, "error": 0})
        w[status.value] = count

    return {"by_status": by_status, "worker_stats": worker_stats}


_SORT_COLUMNS = {
    "file_name": FileRecord.file_name,
    "file_path": FileRecord.file_path,
    "file_size": FileRecord.file_size,
    "output_size": FileRecord.output_size,
    "created_at": FileRecord.created_at,
    "finished_at": FileRecord.finished_at,
    "status": FileRecord.status,
    "worker_id": FileRecord.worker_id,
    "cancel_reason": FileRecord.cancel_reason,
    "discard_reason": FileRecord.discard_reason,
}


def get_records_page(
    db: Session,
    status: FileStatus | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    page: int = 0,
    page_size: int = 100,
) -> tuple[list[FileRecord], int]:
    """Return one page of records and the total matching count."""
    q = db.query(FileRecord)
    if status is not None:
        q = q.filter(FileRecord.status == status)
    if search:
        q = q.filter(FileRecord.file_name.ilike(f"%{search}%"))
    col = _SORT_COLUMNS.get(sort_by, FileRecord.created_at)
    q = q.order_by(col.desc() if sort_dir == "desc" else col.asc())
    total = q.count()
    items = q.offset(page * page_size).limit(page_size).all()
    return items, total


def get_record_ids(
    db: Session,
    status: FileStatus | None = None,
    search: str | None = None,
) -> list[int]:
    """Return all matching record IDs (no pagination)."""
    q = db.query(FileRecord.id)
    if status is not None:
        q = q.filter(FileRecord.status == status)
    if search:
        q = q.filter(FileRecord.file_name.ilike(f"%{search}%"))
    return [row[0] for row in q.all()]


def delete_file_record(db: Session, record_id: int) -> bool:
    record = get_file_record(db, record_id)
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True


def delete_file_records_bulk(db: Session, ids: list[int]) -> list[FileRecord]:
    """Delete multiple records in one query. Returns the records as they were before deletion."""
    if not ids:
        return []
    records = db.query(FileRecord).filter(FileRecord.id.in_(ids)).all()
    for r in records:
        db.delete(r)
    db.commit()
    return records


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

    jobs, total_in, total_out, avg_dur, avg_fps, avg_speed = db.query(
        func.count(FileRecord.id),
        func.sum(FileRecord.file_size),
        func.sum(FileRecord.output_size),
        func.avg(_dur),
        func.avg(FileRecord.avg_fps),
        func.avg(FileRecord.avg_speed),
    ).filter(*_f).one()
    jobs, total_in, total_out = jobs or 0, total_in or 0, total_out or 0
    _avg_dur = avg_dur or 0
    _mb_per_s = ((total_in / jobs) / 1_048_576 / _avg_dur) if (jobs and _avg_dur) else None

    # Library-wide totals — include COMPLETE + DISCARDED (both have been ffprobed)
    _lf = [FileRecord.status.in_([FileStatus.COMPLETE, FileStatus.DISCARDED])]
    lib_total_duration, lib_avg_bitrate = db.query(
        func.sum(FileRecord.duration),
        func.avg(FileRecord.bitrate),
    ).filter(*_lf).one()

    overall = {
        "jobs": jobs,
        "total_input_bytes": total_in,
        "total_output_bytes": total_out,
        "total_saved_bytes": total_in - total_out,
        "avg_duration_seconds": round(_avg_dur, 1),
        "avg_compression_ratio": round(total_out / total_in, 3) if total_in else 0.0,
        "avg_fps": round(avg_fps, 1) if avg_fps is not None else None,
        "avg_speed": round(avg_speed, 2) if avg_speed is not None else None,
        "avg_mb_per_s": round(_mb_per_s, 2) if _mb_per_s is not None else None,
        "total_duration_seconds": round(lib_total_duration, 0) if lib_total_duration else None,
        "avg_bitrate_bps": round(lib_avg_bitrate, 0) if lib_avg_bitrate else None,
    }

    by_encoder: dict = {}
    for enc, j, in_b, out_b, dur, avg_fps, avg_speed, avg_src_br in db.query(
        FileRecord.encoder, func.count(FileRecord.id),
        func.sum(FileRecord.file_size), func.sum(FileRecord.output_size), func.avg(_dur),
        func.avg(FileRecord.avg_fps), func.avg(FileRecord.avg_speed),
        func.avg(FileRecord.bitrate),
    ).filter(*_f).group_by(FileRecord.encoder).all():
        in_b, out_b = in_b or 0, out_b or 0
        avg_dur = dur or 0
        mb_per_s = ((in_b / j) / 1_048_576 / avg_dur) if (j and avg_dur) else None
        by_encoder[enc or "unknown"] = {
            "jobs": j or 0,
            "total_input_bytes": in_b,
            "total_output_bytes": out_b,
            "total_saved_bytes": in_b - out_b,
            "avg_duration_seconds": round(avg_dur, 1),
            "avg_compression_ratio": round(out_b / in_b, 3) if in_b else 0.0,
            "avg_fps": round(avg_fps, 1) if avg_fps is not None else None,
            "avg_speed": round(avg_speed, 2) if avg_speed is not None else None,
            "avg_mb_per_s": round(mb_per_s, 2) if mb_per_s is not None else None,
            "avg_src_bitrate_bps": round(avg_src_br, 0) if avg_src_br is not None else None,
        }

    by_worker = []
    for sid, j, in_b, out_b, dur in db.query(
        FileRecord.worker_id, func.count(FileRecord.id),
        func.sum(FileRecord.file_size), func.sum(FileRecord.output_size), func.avg(_dur),
    ).filter(*_f).group_by(FileRecord.worker_id).all():
        in_b, out_b = in_b or 0, out_b or 0
        w_dur = dur or 0
        w_mb_per_s = ((in_b / j) / 1_048_576 / w_dur) if (j and w_dur) else None
        by_worker.append({
            "worker_id": sid or "unknown",
            "jobs": j or 0,
            "total_input_bytes": in_b,
            "total_output_bytes": out_b,
            "total_saved_bytes": in_b - out_b,
            "avg_compression_ratio": round(out_b / in_b, 3) if in_b else 0.0,
            "avg_duration_seconds": round(w_dur, 1),
            "avg_mb_per_s": round(w_mb_per_s, 2) if w_mb_per_s is not None else None,
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

    def _res_tier(h: int) -> str:
        if h >= 2160: return "4K"
        if h >= 1080: return "1080p"
        if h >= 720:  return "720p"
        return "SD"

    def _br_tier(bps: int) -> str:
        if bps < 5_000_000:  return "<5 Mbps"
        if bps < 15_000_000: return "5–15 Mbps"
        if bps < 40_000_000: return "15–40 Mbps"
        return "40+ Mbps"

    _tier_defaults: dict = {"count": 0, "total_duration_seconds": 0.0,
                            "total_saved_bytes": 0, "bitrate_samples": []}

    by_resolution: dict[str, dict] = {}
    for h, br, dur, fsz, osz, st in db.query(
        FileRecord.height, FileRecord.bitrate, FileRecord.duration,
        FileRecord.file_size, FileRecord.output_size, FileRecord.status,
    ).filter(FileRecord.height.isnot(None)).all():
        tier = _res_tier(h)
        t = by_resolution.setdefault(tier, {"count": 0, "total_duration_seconds": 0.0,
                                             "total_saved_bytes": 0, "bitrate_samples": []})
        t["count"] += 1
        if dur: t["total_duration_seconds"] += dur
        if br:  t["bitrate_samples"].append(br)
        if st == FileStatus.COMPLETE and fsz and osz:
            t["total_saved_bytes"] += max(0, fsz - osz)
    for t in by_resolution.values():
        samples = t.pop("bitrate_samples")
        t["avg_bitrate_bps"] = round(sum(samples) / len(samples), 0) if samples else None
        t["total_duration_seconds"] = round(t["total_duration_seconds"], 0)

    by_bitrate_tier: dict[str, dict] = {}
    for br, fsz, osz, st in db.query(
        FileRecord.bitrate, FileRecord.file_size, FileRecord.output_size, FileRecord.status,
    ).filter(FileRecord.bitrate.isnot(None)).all():
        tier = _br_tier(br)
        t = by_bitrate_tier.setdefault(tier, {"count": 0, "total_saved_bytes": 0})
        t["count"] += 1
        if st == FileStatus.COMPLETE and fsz and osz:
            t["total_saved_bytes"] += max(0, fsz - osz)

    return {"overall": overall, "by_encoder": by_encoder, "by_worker": by_worker,
            "by_day": by_day, "by_resolution": by_resolution, "by_bitrate_tier": by_bitrate_tier}


def get_worker_stats(db: Session, worker_id: str) -> dict:
    _dur = (func.julianday(FileRecord.finished_at) - func.julianday(FileRecord.started_at)) * 86400
    _f = [
        FileRecord.status == FileStatus.COMPLETE,
        FileRecord.worker_id == worker_id,
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
        FileRecord.worker_id == worker_id,
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

    return {"worker_id": worker_id, "overall": overall, "by_encoder": by_encoder, "by_day": by_day}


def update_conversion_result(
    db: Session,
    record_id: int,
    status: FileStatus,
    pid: int | None,
    output_size: int | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    cancel_reason: str | None = None,
    cancel_detail: str | None = None,
    encoder: str | None = None,
    avg_fps: float | None = None,
    avg_speed: float | None = None,
    width: int | None = None,
    height: int | None = None,
    bitrate: int | None = None,
    duration: float | None = None,
    ffmpeg_cmd: str | None = None,
) -> FileRecord | None:
    record = get_file_record(db, record_id)
    if record:
        record.status = status
        record.pid = pid
        record.output_size = output_size
        record.started_at = started_at
        record.finished_at = finished_at
        record.cancel_reason = cancel_reason
        record.cancel_detail = cancel_detail
        if encoder is not None:
            record.encoder = encoder
        if avg_fps is not None:
            record.avg_fps = avg_fps
        if avg_speed is not None:
            record.avg_speed = avg_speed
        if width is not None:
            record.width = width
        if height is not None:
            record.height = height
        if bitrate is not None:
            record.bitrate = bitrate
        if duration is not None:
            record.duration = duration
        if ffmpeg_cmd is not None:
            record.ffmpeg_cmd = ffmpeg_cmd
        db.commit()
        db.refresh(record)
    return record
