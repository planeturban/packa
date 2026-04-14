"""
Sends metadata (HTTP) to a slave.
The master's path prefix is stripped before sending so the slave receives
only the relative path, which it then prepends with its own prefix.
"""

import httpx

from .registry import SlaveInfo
from .scanner import VideoFile


async def send_metadata(record_id: int, video: VideoFile, slave: SlaveInfo, path_prefix: str = "") -> dict:
    relative_path = video.file_path
    if path_prefix and relative_path.startswith(path_prefix):
        relative_path = relative_path[len(path_prefix):]

    url = f"http://{slave.host}:{slave.api_port}/files"
    payload = {
        "id": record_id,
        "file_name": video.file_name,
        "file_path": relative_path,
        "c_time": video.c_time,
        "m_time": video.m_time,
        "checksum": video.checksum,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
