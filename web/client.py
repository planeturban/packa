"""
Async HTTP client for fetching dashboard data from master and workers.
"""

import asyncio

import httpx

_STATUSES = ["pending", "assigned", "processing", "complete", "discarded", "cancelled", "error", "duplicate"]


async def fetch_dashboard(master_url: str) -> dict:
    """
    Fetch all data needed for the dashboard in one call.
    Never raises — returns error fields on failure.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            workers_r, scan_r, files_r, settings_r, stats_r = await asyncio.gather(
                client.get(f"{master_url}/workers"),
                client.get(f"{master_url}/scan/status"),
                client.get(f"{master_url}/files"),
                client.get(f"{master_url}/scan/settings"),
                client.get(f"{master_url}/stats"),
            )
            workers_list: list = workers_r.json()
            scan: dict = scan_r.json()
            files: list = files_r.json()
            scan_settings: dict = settings_r.json()
            master_stats: dict = stats_r.json()
            master_error = None
        except Exception as exc:
            return {
                "master_error": str(exc),
                "scan": None,
                "scan_settings": {"interval": 60, "enabled": False},
                "file_counts": {s: 0 for s in _STATUSES},
                "files": [],
                "workers": [],
                "stats": {"total": 0, "converted": 0, "pending": 0, "processing": 0,
                          "error": 0, "duplicate": 0, "saved_bytes": 0},
                "master_stats": {},
            }

        file_counts = {s: 0 for s in _STATUSES}
        for f in files:
            s = f.get("status", "")
            if s in file_counts:
                file_counts[s] += 1

        overall = (master_stats.get("overall") or {})
        stats = {
            "total": sum(file_counts.values()),
            "converted": file_counts.get("complete", 0),
            "pending": file_counts.get("pending", 0),
            "processing": file_counts.get("processing", 0),
            "cancelled": file_counts.get("cancelled", 0),
            "error": file_counts.get("error", 0),
            "duplicate": file_counts.get("duplicate", 0),
            "discarded": file_counts.get("discarded", 0),
            "saved_bytes": overall.get("total_saved_bytes", 0),
        }

        status_results = await asyncio.gather(
            *[
                client.get(f"http://{s['host']}:{s['api_port']}/status")
                for s in workers_list
            ],
            return_exceptions=True,
        )

    workers = []
    for info, result in zip(workers_list, status_results):
        st = None
        if not isinstance(result, Exception):
            try:
                st = result.json()
            except Exception:
                pass

        config_id = info["config_id"]
        converted = sum(
            1 for f in files
            if f.get("worker_id") == config_id and f.get("status") == "complete"
        )
        errors = sum(
            1 for f in files
            if f.get("worker_id") == config_id and f.get("status") == "error"
        )

        workers.append({
            "id": info["id"],
            "config_id": config_id,
            "hostname": config_id,
            "url": f"http://{info['host']}:{info['api_port']}",
            "host": info["host"],
            "api_port": info["api_port"],
            "state": (st or {}).get("state", "unreachable"),
            "record_id": (st or {}).get("record_id"),
            "queued": (st or {}).get("queued", 0),
            "progress": (st or {}).get("progress"),
            "paused": (st or {}).get("paused", False),
            "drain": (st or {}).get("drain", False),
            "sleeping": (st or {}).get("sleeping", False),
            "current_file": (st or {}).get("current_file"),
            "current_cmd": (st or {}).get("current_cmd"),
            "unconfigured": (st or {}).get("unconfigured", False),
            "encoder": (st or {}).get("encoder", "libx265"),
            "available_encoders": (st or {}).get("available_encoders", ["libx265"]),
            "encoder_labels": (st or {}).get("encoder_labels", {}),
            "batch_size": (st or {}).get("batch_size", 1),
            "replace_original": (st or {}).get("replace_original", False),
            "converted": converted,
            "errors": errors,
        })

    return {
        "master_error": master_error,
        "scan": scan,
        "scan_settings": scan_settings,
        "file_counts": file_counts,
        "files": files,
        "workers": workers,
        "stats": stats,
        "master_stats": master_stats,
    }
