# API Reference

## Master (default port 9000)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/slaves` | Register a slave |
| `GET` | `/slaves` | List registered slaves |
| `DELETE` | `/slaves/{id}` | Deregister a slave |
| `POST` | `/transfer` | Add a single file `{"file_path": "..."}` |
| `POST` | `/jobs/claim` | Claim pending jobs `{"slave_id": "...", "count": 1}` |
| `PATCH` | `/files/{id}/result` | Slave reports conversion result |
| `PATCH` | `/files/{id}/status` | Update record status |
| `GET` | `/files` | List records, filterable by `?status=` |
| `GET` | `/files/{id}` | Get a single record |
| `DELETE` | `/files/{id}` | Delete a record |
| `POST` | `/scan/start` | Start a background directory scan |
| `POST` | `/scan/stop` | Cancel a running scan |
| `GET` | `/scan/status` | Scan progress |
| `GET` | `/scan/settings` | Get periodic scan settings |
| `POST` | `/scan/settings` | Update periodic scan settings |
| `GET` | `/stats` | Aggregated conversion statistics |
| `GET` | `/stats/slave/{id}` | Per-encoder statistics for a specific slave |

---

## Slave (default port 8000)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Worker state, queue depth, live ffmpeg progress |
| `GET` | `/files` | List records, filterable by `?status=` |
| `GET` | `/files/{id}` | Get a single record |
| `DELETE` | `/files/{id}` | Delete a record (stops ffmpeg if running) |
| `PATCH` | `/files/{id}/status` | Update record status |
| `POST` | `/conversion/stop` | Terminate ffmpeg (`cancel_reason = "user"`) |
| `POST` | `/conversion/pause` | Suspend ffmpeg (SIGSTOP) |
| `POST` | `/conversion/resume` | Resume paused ffmpeg |
| `POST` | `/conversion/drain` | Finish current job then enter sleep mode |
| `POST` | `/conversion/sleep` | Enter sleep mode (no polling, no new jobs) |
| `POST` | `/conversion/wake` | Leave sleep mode |
| `GET` | `/settings` | Get current encoder and batch size |
| `POST` | `/settings` | Update encoder and/or batch size |
