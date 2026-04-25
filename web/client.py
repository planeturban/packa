"""
Async HTTP client for fetching dashboard data from master and workers.
"""

import asyncio

import httpx

_STATUSES = ["scanning", "pending", "assigned", "processing", "complete", "discarded", "cancelled", "error", "duplicate"]


async def fetch_dashboard(master_url: str, httpx_kwargs: dict | None = None) -> dict:
    """
    Fetch all data needed for the dashboard in one call.
    Never raises — returns error fields on failure.
    """
    kw = httpx_kwargs or {}
    async with httpx.AsyncClient(timeout=5.0, **kw) as client:
        try:
            workers_r, scan_r, counts_r, stats_r, meta_r, cfg_r, tls_status_r, tls_token_r = await asyncio.gather(
                client.get(f"{master_url}/workers"),
                client.get(f"{master_url}/scan/status"),
                client.get(f"{master_url}/files/counts"),
                client.get(f"{master_url}/stats"),
                client.get(f"{master_url}/master/stats"),
                client.get(f"{master_url}/master/config"),
                client.get(f"{master_url}/tls/status"),
                client.get(f"{master_url}/tls/token"),
            )
            workers_list: list = workers_r.json()
            scan: dict = scan_r.json()
            counts_data: dict = counts_r.json()
            master_stats: dict = stats_r.json()
            master_meta: dict = meta_r.json()
            master_config: dict = cfg_r.json()
            tls_status: dict = tls_status_r.json() if tls_status_r.is_success else {}
            tls_token: dict = tls_token_r.json() if tls_token_r.is_success else {}
            master_error = None
        except Exception as exc:
            return {
                "master_error": str(exc),
                "scan": None,
                "file_counts": {s: 0 for s in _STATUSES},
                "workers": [],
                "stats": {"total": 0, "converted": 0, "pending": 0, "processing": 0,
                          "error": 0, "duplicate": 0, "saved_bytes": 0},
                "master_stats": {},
                "master_meta": {},
                "master_config": {},
                "tls_status": {},
                "tls_token": {},
            }

        file_counts = counts_data.get("by_status", {s: 0 for s in _STATUSES})
        worker_stats = counts_data.get("worker_stats", {})

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

        status_results, config_results, worker_stat_results = await asyncio.gather(
            asyncio.gather(
                *[client.get(f"{s.get('scheme','http')}://{s['host']}:{s['api_port']}/status") for s in workers_list],
                return_exceptions=True,
            ),
            asyncio.gather(
                *[client.get(f"{s.get('scheme','http')}://{s['host']}:{s['api_port']}/config") for s in workers_list],
                return_exceptions=True,
            ),
            asyncio.gather(
                *[client.get(f"{master_url}/stats/worker/{s['config_id']}") for s in workers_list],
                return_exceptions=True,
            ),
        )

    workers = []
    for info, result, cfg_result, stat_result in zip(workers_list, status_results, config_results, worker_stat_results):
        st = None
        if not isinstance(result, Exception):
            try:
                st = result.json()
            except Exception:
                pass
        worker_cfg = {}
        if not isinstance(cfg_result, Exception):
            try:
                worker_cfg = cfg_result.json()
            except Exception:
                pass
        worker_avg_s = None
        if not isinstance(stat_result, Exception):
            try:
                wd = stat_result.json()
                v = (wd.get("overall") or wd).get("avg_duration_seconds")
                worker_avg_s = v if v else None
            except Exception:
                pass

        config_id = info["config_id"]
        ws = worker_stats.get(config_id, {})
        converted = ws.get("complete", 0)
        errors = ws.get("error", 0)

        workers.append({
            "id": info["id"],
            "config_id": config_id,
            "hostname": config_id,
            "url": f"{info.get('scheme','http')}://{info['host']}:{info['api_port']}",
            "host": info["host"],
            "api_port": info["api_port"],
            "state": (st or {}).get("state", "unreachable"),
            "record_id": (st or {}).get("record_id"),
            "queued": (st or {}).get("queued", 0),
            "progress": (st or {}).get("progress"),
            "paused": (st or {}).get("paused", False),
            "drain": (st or {}).get("drain", False),
            "sleeping": (st or {}).get("sleeping", False),
            "disk_full": (st or {}).get("disk_full", False),
            "current_file": (st or {}).get("current_file"),
            "current_cmd": (st or {}).get("current_cmd"),
            "unconfigured": (st or {}).get("unconfigured", False),
            "encoder": (st or {}).get("encoder", "libx265"),
            "available_encoders": (st or {}).get("available_encoders", ["libx265"]),
            "encoder_labels": (st or {}).get("encoder_labels", {}),
            "batch_size": (st or {}).get("batch_size", 1),
            "replace_original": (st or {}).get("replace_original", False),
            "tls_enabled": (st or {}).get("tls_enabled", False),
            "version": (st or {}).get("version", "?"),
            "consecutive_errors": (st or {}).get("consecutive_errors", 0),
            "sleep_reason": (st or {}).get("sleep_reason"),
            "converted": converted,
            "errors": errors,
            "worker_config": worker_cfg,
            "avg_duration_s": worker_avg_s,
        })

    return {
        "master_error": master_error,
        "scan": scan,
        "file_counts": file_counts,
        "workers": workers,
        "stats": stats,
        "master_stats": master_stats,
        "master_meta": master_meta,
        "master_config": master_config,
        "tls_status": tls_status,
        "tls_token": tls_token,
    }
