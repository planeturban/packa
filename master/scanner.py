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
    file_size: int
    c_time: float
    m_time: float
    checksum: str


def _content_checksum(path: Path, file_size: int, checksum_bytes: int) -> str:
    """SHA-256 of file_size + bytes read from the middle of the file."""
    h = hashlib.sha256()
    h.update(str(file_size).encode())
    if file_size > 0 and checksum_bytes > 0:
        read_size = min(checksum_bytes, file_size)
        offset = max(0, (file_size - read_size) // 2)
        with open(path, "rb") as f:
            f.seek(offset)
            h.update(f.read(read_size))
    return h.hexdigest()


def collect(file_path: str, checksum_bytes: int = 4194304) -> VideoFile:
    """Return metadata for the file at *file_path*."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"No file found at: {path}")

    stat = path.stat()
    file_name = path.name
    resolved = str(path)
    checksum = _content_checksum(path, stat.st_size, checksum_bytes)

    return VideoFile(
        file_name=file_name,
        file_path=resolved,
        file_size=stat.st_size,
        c_time=stat.st_ctime,
        m_time=stat.st_mtime,
        checksum=checksum,
    )
