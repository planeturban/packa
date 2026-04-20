# API Reference

## Master (default port 9000)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/workers` | Register a worker |
| `GET` | `/workers` | List registered workers |
| `DELETE` | `/workers/{id}` | Deregister a worker |
| `POST` | `/transfer` | Add a single file `{"file_path": "..."}` |
| `POST` | `/jobs/claim` | Worker claims pending jobs `{"worker_id": "...", "count": 1}` |
| `POST` | `/jobs/assign` | Directly assign specific file IDs to a worker `{"worker_id": "...", "ids": [...]}` |
| `PATCH` | `/files/{id}/result` | Worker reports conversion result |
| `PATCH` | `/files/{id}/status` | Update record status |
| `GET` | `/files` | List records, filterable by `?status=` |
| `GET` | `/files/{id}` | Get a single record |
| `GET` | `/files/duplicate-pairs` | List duplicate records alongside their original paths |
| `DELETE` | `/files/{id}` | Delete a record |
| `POST` | `/scan/start` | Start a background directory scan |
| `POST` | `/scan/stop` | Cancel a running scan |
| `GET` | `/scan/status` | Scan progress and current path |
| `GET` | `/scan/settings` | Get periodic scan settings |
| `POST` | `/scan/settings` | Update periodic scan settings |
| `GET` | `/stats` | Aggregated conversion statistics (overall + per-worker + per-day) |
| `GET` | `/stats/worker/{id}` | Per-encoder statistics for a specific worker |

---

## Worker (default port 8000)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Worker state, queue depth, live ffmpeg progress, encoder, batch size |
| `GET` | `/files` | List records, filterable by `?status=` |
| `GET` | `/files/{id}` | Get a single record |
| `DELETE` | `/files/{id}` | Delete a record (stops ffmpeg if currently processing this file) |
| `PATCH` | `/files/{id}/status` | Update record status |
| `POST` | `/jobs/push` | Accept a list of pre-assigned jobs (called by master after `/jobs/assign`) |
| `POST` | `/conversion/stop` | Terminate ffmpeg (`cancel_reason = "user"`) |
| `POST` | `/conversion/pause` | Suspend ffmpeg (SIGSTOP) |
| `POST` | `/conversion/resume` | Resume paused ffmpeg (SIGCONT) |
| `POST` | `/conversion/drain` | Finish current job then enter sleep mode |
| `POST` | `/conversion/sleep` | Enter sleep mode (no polling, no new jobs) |
| `POST` | `/conversion/wake` | Leave sleep mode |
| `GET` | `/settings` | Get current encoder, batch size, and replace_original flag |
| `POST` | `/settings` | Update encoder, batch size, and/or replace_original flag |
