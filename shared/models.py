import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FileStatus(str, enum.Enum):
    SCANNING = "scanning"     # Discovered but not yet probed by master
    PENDING = "pending"
    ASSIGNED = "assigned"     # Claimed by a worker, not yet processing
    PROCESSING = "processing"
    COMPLETE = "complete"
    DISCARDED = "discarded"   # Already HEVC — skipped by worker
    CANCELLED = "cancelled"   # Terminated mid-conversion (user or auto size limit)
    ERROR = "error"
    DUPLICATE = "duplicate"   # Same content already exists under a different path


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FileRecord(Base):
    __tablename__ = "file_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    c_time: Mapped[float] = mapped_column(Float, nullable=False)
    m_time: Mapped[float] = mapped_column(Float, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[FileStatus] = mapped_column(
        SAEnum(FileStatus), nullable=False, default=FileStatus.PENDING
    )
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cancel_detail: Mapped[str | None] = mapped_column(String(128), nullable=True)
    discard_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    force_encode: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoder: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ffmpeg_cmd: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    ffmpeg_stderr: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    avg_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    master_synced: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<FileRecord id={self.id} name={self.file_name!r} status={self.status}>"
