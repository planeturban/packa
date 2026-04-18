import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FileStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"     # Claimed by a slave, not yet processing
    PROCESSING = "processing"
    COMPLETE = "complete"
    DISCARDED = "discarded"   # Already HEVC — skipped by slave
    CANCELLED = "cancelled"   # Terminated mid-conversion (user or auto size limit)
    ERROR = "error"


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
    slave_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[FileStatus] = mapped_column(
        SAEnum(FileStatus), nullable=False, default=FileStatus.PENDING
    )
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<FileRecord id={self.id} name={self.file_name!r} status={self.status}>"
