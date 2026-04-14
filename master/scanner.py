"""
Collects metadata for a single file.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoFile:
    file_name: str
    file_path: str
    c_time: float
    m_time: float
    checksum: str


def _checksum(file_name: str, file_path: str, c_time: float, m_time: float) -> str:
    """SHA-256 of the concatenated metadata fields."""
    combined = f"{file_name}{file_path}{c_time}{m_time}"
    return hashlib.sha256(combined.encode()).hexdigest()


def collect(file_path: str) -> VideoFile:
    """Return metadata for the file at *file_path*."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"No file found at: {path}")

    stat = path.stat()
    file_name = path.name
    resolved = str(path)
    c_time = stat.st_ctime
    m_time = stat.st_mtime
    checksum = _checksum(file_name, resolved, c_time, m_time)

    return VideoFile(
        file_name=file_name,
        file_path=resolved,
        c_time=c_time,
        m_time=m_time,
        checksum=checksum,
    )
