"""
Async HTTP client for fetching dashboard data from master and slaves.
"""

import asyncio

import httpx

from shared.config import TlsConfig
from shared.tls import httpx_kwargs, scheme

_STATUSES = ["pending", "assigned", "processing", "complete", "discarded", "cancelled", "error"]


async def fetch_dashboard(master_url: str, tls: TlsConfig) -> dict:
    """
    Fetch all data needed for the dashboard in one call.
    Never raises — returns error fields on failure.
    """
    kw = httpx_kwargs(tls)
    slave_scheme = scheme(tls)

    async with httpx.AsyncClient(timeout=5.0, **kw) as client:
        try:
            slaves_r, scan_r, files_r, settings_r = await asyncio.gather(
                client.get(f"{master_url}/slaves"),
                client.get(f"{master_url}/scan/status"),
                client.get(f"{master_url}/files"),
                client.get(f"{master_url}/scan/settings"),
            )
            slaves_list: list = slaves_r.json()
            scan: dict = scan_r.json()
            files: list = files_r.json()
            scan_settings: dict = settings_r.json()
            master_error = None
        except Exception as exc:
            return {
                "master_error": str(exc),
                "scan": None,
                "scan_settings": {"interval": 60, "enabled": False},
                "file_counts": {s: 0 for s in _STATUSES},
                "slaves": [],
            }

        file_counts = {s: 0 for s in _STATUSES}
        for f in files:
            s = f.get("status", "")
            if s in file_counts:
                file_counts[s] += 1

        status_results = await asyncio.gather(
            *[
                client.get(f"{slave_scheme}://{s['host']}:{s['api_port']}/status")
                for s in slaves_list
            ],
            return_exceptions=True,
        )

    slaves = []
    for info, result in zip(slaves_list, status_results):
        if isinstance(result, Exception):
            st = None
        else:
            try:
                st = result.json()
            except Exception:
                st = None

        slaves.append({
            "id": info["id"],
            "config_id": info["config_id"],
            "host": info["host"],
            "api_port": info["api_port"],
            "state": (st or {}).get("state", "unreachable"),
            "record_id": (st or {}).get("record_id"),
            "queued": (st or {}).get("queued", 0),
            "progress": (st or {}).get("progress"),
            "paused": (st or {}).get("paused", False),
            "drain": (st or {}).get("drain", False),
            "sleeping": (st or {}).get("sleeping", False),
            "encoder": (st or {}).get("encoder", "libx265"),
        })

    return {
        "master_error": master_error,
        "scan": scan,
        "scan_settings": scan_settings,
        "file_counts": file_counts,
        "files": files,
        "slaves": slaves,
    }
