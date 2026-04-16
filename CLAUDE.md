# Packa — developer notes

Distributed system where a **master** node accepts file paths via API or directory scan, stores metadata, and distributes work to one or more **slave** nodes via a pull model. Slaves poll master for jobs, run ffmpeg, and report results back. A **web** frontend provides a browser dashboard and login. All code is Python 3.11+.

## Repository layout

```
master/             Master node — accepts file paths, manages job queue, distributes to slaves
slave/              Slave node — polls master for jobs, runs ffmpeg, reports back
web/                Web frontend — BFF dashboard with login; talks mTLS to master/slaves
shared/             Code shared by all nodes (models, schemas, crud, config, tls)
packa.example.toml  Single config file for master, slave and web
requirements.txt
```

## Shared package

| File | Purpose |
|------|---------|
| `shared/base.py` | SQLAlchemy `DeclarativeBase` — imported by both `master/database.py` and `slave/database.py` |
| `shared/models.py` | `FileRecord` ORM model and `FileStatus` enum |
| `shared/schemas.py` | Pydantic schemas (`FileRecordCreate`, `FileRecordOut`, `StatusUpdate`) |
| `shared/crud.py` | All DB operations — takes a `Session` parameter, no DB knowledge of its own |
| `shared/config.py` | `Config` + sub-configs including `TlsConfig`; `load_master()`, `load_slave()` parse TOML + env vars; `_env()` / `_env_int()` helpers |
| `shared/tls.py` | TLS helpers: `scheme()`, `httpx_kwargs()`, `uvicorn_kwargs()`, `uvicorn_server_kwargs()` — all take a `TlsConfig`. Also exports `UVICORN_LOG_CONFIG` dict (adds `HH:MM:SS` timestamps to all uvicorn log lines). |

## Databases

Each node has its own SQLite database with **identical schema**.

- `master.db` — created in the working directory when master starts
- `slave.db` — created in the working directory when slave starts

Master assigns the record ID. Slave stores the record under the same ID, so both databases share IDs for the same file.

The slave also has a `slave_settings` table (key/value) used to persist the auto-generated slave ID.

## FileStatus enum

```
PENDING → ASSIGNED → DISCARDED  (already HEVC, detected by slave before ffmpeg starts)
                  → PROCESSING → COMPLETE
                               → CANCELLED  (user stopped, or output >= source size)
                               → ERROR
```

- `PENDING` — record created, not yet claimed by any slave
- `ASSIGNED` — claimed by a slave via `/jobs/claim`, not yet processing
- `PROCESSING` — ffmpeg is running on the slave
- `DISCARDED` — file was already HEVC; slave detected this via ffprobe and skipped conversion
- `CANCELLED` — conversion stopped mid-run. `cancel_reason` is `"user"` (manual stop) or `"auto"` (output exceeded source size, either detected mid-run or post-completion)
- `COMPLETE` / `ERROR` — terminal states

## Configuration priority

All three processes apply settings in this order (later wins):

```
config file  <  environment variable  <  CLI flag
```

`load_master()`, `load_slave()`, and `load_web()` each accept `str | None` as the config path. When `None`, only defaults and env vars are used. Env vars are applied inside the load functions; CLI overrides are applied afterwards in `main()` by checking `if args.x is not None`.

## Master

**Entry point:** `python -m master.master`

| File | Purpose |
|------|---------|
| `master/master.py` | CLI (`--bind`, `--api-port`, `--config`), starts uvicorn (with TLS if configured) |
| `master/api.py` | FastAPI app; module-level `_config` set via `set_config()` before uvicorn starts |
| `master/registry.py` | In-memory `SlaveRegistry`; slaves identified by numeric `id` (int, auto) and `config_id` (string, from config file) |
| `master/scanner.py` | `collect(file_path) → VideoFile` — reads stat, computes checksum |
| `master/database.py` | Engine + `SessionLocal` + `get_db()` for `master.db` |

**Checksum:** `SHA-256("{file_name}{file_path}{c_time}{m_time}")` — ID is not included.

**Path prefix:** master strips its own `path_prefix` from `file_path` in `/jobs/claim` before returning relative paths to slaves. Slaves prepend their own `path_prefix`.

**Key API endpoints:**
- `POST /slaves` — slave registration (called automatically by slave on startup)
- `POST /transfer {"file_path": "..."}` — collect metadata for a single file, create PENDING record
- `POST /scan/start` — background directory scan; creates PENDING records for new files
- `POST /scan/stop` / `GET /scan/status` — cancel or query running scan
- `POST /jobs/claim {"slave_id": "...", "count": N}` — slave claims N PENDING records; master marks them ASSIGNED and returns relative paths
- `POST /files/{id}/sync {"slave_id": N}` — called by slave after ffmpeg completes; master fetches the record from slave and updates its own DB
- `GET /files?status=...` — query master DB, filterable by status

**Scan state** is held in a module-level `_ScanState` instance in `master/api.py`. The background task runs as an `asyncio.Task`, yields with `await asyncio.sleep(0)` between files, and is cancellable via `/scan/stop`.

**Master env vars:**

| Variable | Config equivalent |
|----------|------------------|
| `PACKA_MASTER_BIND` | `[master].bind` |
| `PACKA_MASTER_API_PORT` | `[master].api_port` |
| `PACKA_MASTER_PREFIX` | `[master.paths].prefix` |
| `PACKA_MASTER_EXTENSIONS` | `[master.scan].extensions` (comma-separated) |
| `PACKA_MASTER_TLS_CERT` | `[master.tls].cert` |
| `PACKA_MASTER_TLS_KEY` | `[master.tls].key` |
| `PACKA_TLS_CA` | `[tls].ca` (shared) |

## Slave

**Entry point:** `python -m slave.main`

| File | Purpose |
|------|---------|
| `slave/main.py` | CLI (`--bind`, `--api-port`, `--master-host`, `--master-port`, `--advertise-host`, `--config`); resolves slave ID, registers with master, sets `worker_state` fields |
| `slave/api.py` | FastAPI app; lifespan sets `worker_state.tls`, starts `worker_loop` and `poller_loop` |
| `slave/worker.py` | `worker_loop` — processes one job at a time from `worker_state.queue`; `recover()` called at startup |
| `slave/poller.py` | `poller_loop` — polls master every `poll_interval` seconds when queue is empty; claims jobs and enqueues them |
| `slave/state.py` | `WorkerState` (active, record_id, queue, progress, proc, slave_id, slave_config_id, master_url, tls) and `FfmpegProgress` dataclass |
| `slave/identity.py` | `get_or_create_slave_id()` / `get_stored_slave_id()` — persists slave ID in `slave_settings` table |
| `slave/database.py` | Engine + `SessionLocal` + `get_db()` for `slave.db` |

**Slave ID resolution** (in `slave/main.py`):
1. Use `slave.id` from config / `PACKA_SLAVE_ID` env / `--id` (whichever wins per priority order)
2. Otherwise look up persisted ID from `slave_settings` table in `slave.db`
3. Otherwise generate a UUID4, store it, and use it

If config has an ID and the DB has a different one, a warning is logged.

**Worker queue:** jobs are `asyncio.Queue` items. Poller and API both enqueue; worker processes sequentially. At startup `recover()`:
1. Finds `PROCESSING` records → deletes partial output files → resets to `PENDING`
2. Finds all `PENDING` records → enqueues in ID order

**Poller:** runs as an asyncio task alongside `worker_loop`. Polls when `worker_state.queued == 0 and not worker_state.active`. On each claim it creates slave DB records (applying `path_prefix`) and enqueues jobs. If master is unreachable it logs and retries after `poll_interval` seconds.

**ffmpeg invocation:**
```
ffmpeg -i {file_path} -map 0 -c copy [extra_args] -progress pipe:1 -nostats {output_path}
```
Before starting ffmpeg, `ffprobe` checks the video codec. If the file is already HEVC the record is set to `DISCARDED` immediately and ffmpeg is never run. Otherwise all streams are copied. stdout is streamed line-by-line for live progress; stderr collected for error logging.

**Output size monitoring:** `_monitor_output_size()` checks the output file every 5 seconds while ffmpeg runs. If it grows `>= source_size`, ffmpeg is terminated and the record is set to `CANCELLED` (`cancel_reason="auto"`).

**After conversion:** if `output_size >= source_size` the output file is deleted and status is set to `CANCELLED` (`cancel_reason="auto"`). Otherwise `COMPLETE` and result is pushed to master via `PATCH /files/{id}/result`.

**Sleep / drain modes:** `worker_state.sleeping` blocks the worker loop and the poller. `worker_state.drain` causes the worker to set `sleeping=True` after the current job finishes (Finish current). Both flags are exposed in `GET /status`.

**Key API endpoints:**
- `GET /status` — idle/processing/sleeping state, queue depth, drain flag, live ffmpeg progress
- `GET /files?status=...` — filterable, all fields including `output_size`, `started_at`, `finished_at`
- `POST /conversion/stop` — terminates the running ffmpeg process; sets status to `CANCELLED` with `cancel_reason="user"`
- `POST /conversion/sleep` — enter sleep mode (no polling, no new jobs)
- `POST /conversion/wake` — leave sleep mode

**Slave env vars:**

| Variable | Config equivalent |
|----------|------------------|
| `PACKA_SLAVE_BIND` | `[slave].bind` |
| `PACKA_SLAVE_API_PORT` | `[slave].api_port` |
| `PACKA_SLAVE_ID` | `[slave].id` |
| `PACKA_SLAVE_PREFIX` | `[slave.paths].prefix` |
| `PACKA_SLAVE_MASTER_HOST` | `[slave].master_host` |
| `PACKA_SLAVE_MASTER_PORT` | `[slave].master_port` |
| `PACKA_SLAVE_ADVERTISE_HOST` | `[slave].advertise_host` |
| `PACKA_SLAVE_FFMPEG_BIN` | `[slave.ffmpeg].bin` |
| `PACKA_SLAVE_FFMPEG_OUTPUT_DIR` | `[slave.ffmpeg].output_dir` |
| `PACKA_SLAVE_FFMPEG_EXTRA_ARGS` | `[slave.ffmpeg].extra_args` |
| `PACKA_SLAVE_BATCH_SIZE` | `[slave.worker].batch_size` |
| `PACKA_SLAVE_POLL_INTERVAL` | `[slave.worker].poll_interval` |
| `PACKA_SLAVE_TLS_CERT` | `[slave.tls].cert` |
| `PACKA_SLAVE_TLS_KEY` | `[slave.tls].key` |
| `PACKA_TLS_CA` | `[tls].ca` (shared) |

## Web frontend

**Entry point:** `python -m web.main`

Browser talks HTTP(S) to the web process. Web process talks mTLS to master and slaves (BFF pattern).

| File | Purpose |
|------|---------|
| `web/main.py` | CLI (`--bind`, `--port`, `--master-host`, `--master-port`, `--config`), starts uvicorn |
| `web/app.py` | FastAPI app; session-based auth, Jinja2 dashboard, login/logout routes |
| `web/client.py` | `fetch_dashboard()` — fans out to master + all slaves in parallel with one `AsyncClient` |
| `web/config.py` | `WebConfig` dataclass + `load_web()` — reads `[web]` section + env vars |
| `web/templates/` | `base.html`, `login.html`, `dashboard.html` |

**Dashboard** auto-refreshes every 3 seconds with smooth DOM updates. Shows:
- Master file counts by status (clickable, opens filtered file list modal)
- Scan state and controls, periodic scan toggle
- Per-slave cards: idle/converting/sleeping/draining badge, queue depth, ffmpeg progress with speed/FPS/ETA/size; controls for Pause, Finish current (drain), Stop, Sleep/Wake
- Full file table with search, status filter, bulk actions (delete / set to pending) and pagination
- Dark mode with manual Light / System / Dark picker (preference stored in `localStorage`); inline `<script>` in `<head>` applies theme before first render to avoid flash

**Auth:** `SessionMiddleware` (starlette) with `secret_key` from config. Session stores `{"user": username}` after successful login. `secret_key` must be set — `set_config()` raises `ValueError` if empty.

**Web env vars:**

| Variable | Config equivalent |
|----------|------------------|
| `PACKA_WEB_BIND` | `[web].bind` |
| `PACKA_WEB_PORT` | `[web].port` |
| `PACKA_WEB_USERNAME` | `[web].username` |
| `PACKA_WEB_PASSWORD` | `[web].password` |
| `PACKA_WEB_SECRET_KEY` | `[web].secret_key` |
| `PACKA_WEB_MASTER_HOST` | `[web].master_host` |
| `PACKA_WEB_MASTER_PORT` | `[web].master_port` |
| `PACKA_WEB_TLS_CERT` | `[web.tls].cert` |
| `PACKA_WEB_TLS_KEY` | `[web.tls].key` |
| `PACKA_TLS_CA` | `[tls].ca` (shared) |

## mTLS

mTLS is optional and controlled entirely by config. All HTTP calls (registration, job claim, sync) use `https://` and client certificates when `tls.enabled` is true.

`shared/tls.py` provides four helpers:
- `scheme(tls)` — returns `"https"` or `"http"`
- `httpx_kwargs(tls)` — returns `{"verify": ca, "cert": (cert, key)}` or `{}`
- `uvicorn_kwargs(tls)` — uvicorn SSL kwargs with `ssl_cert_reqs=ssl.CERT_REQUIRED` (master/slave servers)
- `uvicorn_server_kwargs(tls)` — same but without `ssl_cert_reqs` (web server, browsers don't send client certs)

**Behaviour matrix:**

| Master TLS | Slave TLS | Result |
|------------|-----------|--------|
| enabled | enabled | mTLS on all connections |
| disabled | disabled | plain HTTP |
| enabled | disabled | master rejects slave (no client cert) |
| disabled | enabled | slave connects without TLS |

`worker_state.tls` is set in `slave/api.py` lifespan (from `_config.tls`) so `worker.py` and `poller.py` can use it without importing `_config`.

## Config file (TOML)

All nodes share one config file (`packa.toml`). Parsed with `tomllib` (stdlib, Python 3.11+).

- `load_master(path|None)` reads `[master]` + `[tls]` / `[master.tls]`
- `load_slave(path|None)` reads `[slave]` + `[tls]` / `[slave.tls]`; falls back to `master.paths.prefix` if slave prefix is empty
- `load_web(path|None)` reads `[web]` + `[tls]` / `[web.tls]`

TLS: `[tls]` holds the shared CA. Node-specific `[*.tls]` sections hold cert and key and override the shared values.

**Master config fields:**

```toml
[master]
bind     = "localhost"
api_port = 9000

[master.paths]
prefix = "/mnt/data/"

[master.scan]
extensions = [".mkv", ".mp4", ".avi", ".mov"]

[master.tls]               # optional
cert = "/etc/packa/master.crt"
key  = "/etc/packa/master.key"
```

**Slave config fields:**

```toml
[slave]
bind           = "localhost"
api_port       = 8000
master_host    = "localhost"
master_port    = 9000
# advertise_host = ""      # auto-detected if omitted
id             = "storage-01"   # omit to use persisted UUID from slave.db

[slave.paths]
prefix = "/mnt/files/"    # omit to fall back to master.paths.prefix

[slave.ffmpeg]
bin        = "ffmpeg"
output_dir = "/mnt/output"
extra_args = ""

[slave.worker]
batch_size    = 1
poll_interval = 5

[slave.tls]                # optional
cert = "/etc/packa/slave.crt"
key  = "/etc/packa/slave.key"
```

**Web config fields:**

```toml
[web]
bind        = "localhost"
port        = 8080
username    = "admin"
password    = "secret"
secret_key  = "long-random-string"
master_host = "localhost"
master_port = 9000

[web.tls]                  # optional
cert = "/etc/packa/web.crt"
key  = "/etc/packa/web.key"
```

**Shared TLS:**

```toml
[tls]
ca = "/etc/packa/ca.crt"
```

## Running

```bash
pip install -r requirements.txt

# Master
python -m master.master --config packa.toml

# Slave (registers automatically, ffmpeg optional)
python -m slave.main --config packa.toml

# Web dashboard
python -m web.main --config packa.toml
```

## Key design decisions

- **Pull model:** slaves poll master for work via `POST /jobs/claim`. Master never pushes. Slaves continue processing queued jobs if master goes down.
- **Shared ID:** master auto-increments the ID, returns it in `/jobs/claim`. Slave stores the record under that ID. Both databases use the same ID for the same file.
- **slave_id column:** `FileRecord.slave_id` (string) in master's DB records which slave holds the file, using the slave's config `id` field.
- **Persistent slave ID:** if `slave.id` is omitted from config and env, the ID is looked up in `slave_settings` in `slave.db`. If absent, a UUID4 is generated and stored so the same ID survives restarts.
- **No file transfer:** only metadata travels over HTTP. Files are accessed by slaves directly via the filesystem (path prefix translation).
- **Single config file:** `packa.toml` has `[master]`, `[slave]`, `[web]`, and optional `[tls]` sections. Each process reads only its own section.
- **Config priority:** config file < env var < CLI flag. Load functions apply env vars internally; CLI overrides happen in `main()` with `default=None` args.
- **mTLS optional:** enabled when all three TLS fields (cert, key, ca) are set for a node. `shared/tls.py` helpers used by uvicorn setup and every httpx call.
- **Web as BFF:** browser talks to web process, web process talks mTLS to master/slaves. Web holds its own client certificate.
- **asyncio throughout:** uvicorn, worker loop, poller loop, ffmpeg subprocess and progress streaming all share one event loop per process.
- **Config before app:** `set_config()` must be called before uvicorn starts. It sets a module-level `_config` in each `api.py`. The lifespan reads `_config` to start background tasks.
