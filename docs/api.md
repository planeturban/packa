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
| `GET` | `/stats` | Aggregated conversion statistics (overall + per-worker + per-day) |
| `GET` | `/stats/worker/{id}` | Per-encoder statistics for a specific worker |
| `GET` | `/master/stats` | Probe rate, scan rate, probe queue depth, average conversion time |
| `GET` | `/master/config` | Layered master config: `fields`, effective `values`, per-key `sources`, and each layer (`file`, `env`, `db`, `cli`) |
| `PATCH` | `/master/config/{key}` | Write a database override `{"value": ...}`; returns `{ok, requires_restart}` |
| `DELETE` | `/master/config/{key}` | Clear the database override for `{key}`; value reverts via the priority chain |
| `POST` | `/master/config/{key}/restore` | Copy a layer's value into the database `{"source": "file"\|"env"\|"default"}` |
| `POST` | `/bootstrap` | Exchange a bootstrap token for a signed client cert bundle `{cert_pem, key_pem, ca_pem}` |
| `GET` | `/tls/status` | CA fingerprint and `enabled` flag |
| `GET` | `/tls/token` | Current token info `{token, expires_at}` |
| `POST` | `/tls/token` | Generate a new bootstrap token |

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
| `GET` | `/config` | Layered worker config: `fields`, effective `values`, per-key `sources`, and each layer (`file`, `env`, `db`, `cli`) |
| `PATCH` | `/config/{key}` | Write a database override `{"value": ...}`; returns `{ok, requires_restart}` |
| `DELETE` | `/config/{key}` | Clear the database override for `{key}`; value reverts via the priority chain |
| `POST` | `/config/{key}/restore` | Copy a layer's value into the database `{"source": "file"\|"env"\|"default"}` |
| `POST` | `/tls/bootstrap` | Fetch cert bundle from master using a bootstrap token and self-restart |
| `POST` | `/restart` | Restart worker process in-place (`os.execv`) |

---

## Web BFF (default port 8080)

The web process proxies most calls to master and workers. TLS-related BFF endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/data/tls/status` | Proxy to `GET /tls/status` on master |
| `GET` | `/data/tls/token` | Proxy to `GET /tls/token` on master |
| `POST` | `/data/tls/token` | Proxy to `POST /tls/token` on master |
| `POST` | `/data/worker/tls/onboard` | Generate token, send to worker, trigger worker restart |
| `POST` | `/restart` | Restart web process in-place (`os.execv`) |
| `GET` | `/setup/bootstrap` | Standalone bootstrap token form (shown when web has no TLS certs) |
| `POST` | `/setup/bootstrap` | Submit token, bootstrap TLS, restart |
