# Packa — developer notes

Distributed system where a **master** node accepts file paths via API or directory scan, stores metadata, and distributes work to one or more **worker** nodes via a pull model. Workers poll master for jobs, run ffmpeg, and report results back. A **web** frontend provides a browser dashboard and login. All code is Python 3.11+.

## Repository layout

```
master/             Master node — accepts file paths, manages job queue, distributes to workers
worker/              Worker node — polls master for jobs, runs ffmpeg, reports back
web/                Web frontend — BFF dashboard with login; talks mTLS to master/workers
shared/             Code shared by all nodes (models, schemas, crud, config, tls)
packa.example.toml  Single config file for master, worker and web
requirements.txt
```

## Shared package

| File | Purpose |
|------|---------|
| `shared/base.py` | SQLAlchemy `DeclarativeBase` — imported by both `master/database.py` and `worker/database.py` |
| `shared/models.py` | `FileRecord` ORM model and `FileStatus` enum |
| `shared/schemas.py` | Pydantic schemas (`FileRecordCreate`, `FileRecordOut`, `StatusUpdate`) |
| `shared/crud.py` | All DB operations — takes a `Session` parameter, no DB knowledge of its own |
| `shared/config.py` | `Config` + sub-configs including `TlsConfig`; `load_master()`, `load_worker()` parse TOML + env vars; `_env()` / `_env_int()` helpers |
| `shared/tls.py` | TLS helpers: `scheme()`, `httpx_kwargs()`, `uvicorn_kwargs()`, `uvicorn_server_kwargs()` — all take a `TlsConfig`. Also exports `UVICORN_LOG_CONFIG` dict (adds `HH:MM:SS` timestamps to all uvicorn log lines). |
| `shared/db.py` | `make_engine()`, `make_session_factory()`, `migrate()`, `make_get_db()` — shared DB helpers used by master, worker, and web. Engines use `NullPool` (no connection pooling) to avoid exhaustion under concurrent async polling. `migrate()` applies `ALTER TABLE` for columns added after initial schema creation (idempotent). |

## Databases

Each node has its own SQLite database with **identical schema**.

- `master.db` — created in the working directory when master starts
- `worker.db` — created in the working directory when worker starts

Master assigns the record ID. Worker stores the record under the same ID, so both databases share IDs for the same file.

The worker also has a `worker_settings` table (key/value) used to persist the auto-generated worker ID.

## FileStatus enum

```
SCANNING → PENDING → ASSIGNED → DISCARDED  (already HEVC, detected by master probe loop)
         → DUPLICATE
                             → PROCESSING → COMPLETE
                                          → CANCELLED  (user stopped, or output >= source size)
                                          → ERROR
```

- `SCANNING` — record created by scan or `/transfer`; awaiting ffprobe analysis by the master probe loop
- `PENDING` — probed; codec, resolution, bitrate and duration known; not yet claimed by any worker
- `ASSIGNED` — claimed by a worker via `/jobs/claim`, not yet processing
- `PROCESSING` — ffmpeg is running on the worker
- `DISCARDED` — file was already HEVC; detected by master probe loop, never sent to a worker
- `CANCELLED` — conversion stopped mid-run. `cancel_reason` is `"user"` (manual stop) or `"auto"` (output exceeded source size, either detected mid-run or post-completion)
- `COMPLETE` / `ERROR` — terminal states

## Configuration priority

Worker and web apply settings in this order (later wins):

```
config file  <  environment variable  <  CLI flag
```

Master uses a five-layer model managed by `master/config_store.py`:

```
default  <  file  <  environment  <  database  <  CLI
```

The database layer (`master_settings` table, `config.*` keys) is editable at runtime via the dashboard's Master tab. CLI flags always win but are never persisted. On first start `config_store.initialize_from_layers()` seeds the database with the effective file+env+default values; subsequent starts read all four layers, merge them with any CLI overrides, and apply the result via `apply_to_config()`. The running `_config` is refreshed whenever a config endpoint writes to the database.

`load_worker()` and `load_web()` each accept `str | None` as the config path. When `None`, only defaults and env vars are used. Env vars are applied inside the load functions; CLI overrides are applied afterwards in `main()` by checking `if args.x is not None`. Master doesn't use `load_master()` — `master/master.py` reads layers directly via `config_store.read_file_values()`, `read_env_values()`, `read_db_values()`, then calls `compute_effective()` and `apply_to_config()`.

## Master

**Entry point:** `python -m master.master`

| File | Purpose |
|------|---------|
| `master/master.py` | CLI (`--bind`, `--api-port`, `--config`), reads config layers, seeds DB on first run, starts uvicorn |
| `master/api.py` | FastAPI app; module-level `_config`, `_config_path`, `_cli_values` set via `set_config()` / `set_config_layers()` before uvicorn starts. Exposes `/master/config` CRUD endpoints that mutate the DB layer and call `_reapply_config()` |
| `master/config_store.py` | Field registry (`MASTER_FIELDS`), layer readers (`read_file_values`, `read_env_values`, `read_db_values`, `default_values`), `compute_effective()` and `apply_to_config()`, DB ops (`set_db_value`, `delete_db_value`, `initialize_from_layers`) |
| `master/settings.py` | `MasterSetting` key/value table — stores `config.*` entries plus scan-scheduler settings |
| `master/registry.py` | In-memory `WorkerRegistry`; workers identified by numeric `id` (int, auto) and `config_id` (string, from config file) |
| `master/scanner.py` | `collect(file_path) → VideoFile` — reads stat, computes checksum |
| `master/database.py` | Engine + `SessionLocal` + `get_db()` for `master.db` |

**Checksum:** `SHA-256("{file_name}{file_path}{c_time}{m_time}")` — ID is not included.

**Path prefix:** master strips its own `path_prefix` from `file_path` in `/jobs/claim` before returning relative paths to workers. Workers prepend their own `path_prefix`.

**Key API endpoints:**
- `POST /workers` — worker registration (called automatically by worker on startup)
- `POST /transfer {"file_path": "..."}` — collect metadata for a single file, create PENDING record
- `POST /scan/start` — background directory scan; creates PENDING records for new files
- `POST /scan/stop` / `GET /scan/status` — cancel or query running scan
- `POST /jobs/claim {"worker_id": "...", "count": N}` — worker claims N PENDING records; master marks them ASSIGNED and returns relative paths
- `POST /files/{id}/sync {"worker_id": N}` — called by worker after ffmpeg completes; master fetches the record from worker and updates its own DB
- `GET /files?status=...` — query master DB, filterable by status
- `GET /master/config` — full layered view `{fields, values, sources, file, env, db, cli, config_file}`
- `PATCH /master/config/{key}` — body `{value}`, writes DB override, reapplies live config
- `DELETE /master/config/{key}` — clears DB override; effective value falls back through env → file → default
- `POST /master/config/{key}/restore` — body `{source: "file"|"env"|"default"}`, copies that layer into DB
- `GET /master/stats` — probe rate (last 60 s), scan rate, probe queue depth, average conversion time
- `POST /bootstrap` — exchange a bootstrap token for a signed client cert bundle `{cert_pem, key_pem, ca_pem}`
- `GET /tls/status` — CA fingerprint and enabled flag
- `GET /tls/token` — current token info `{token, expires_at}`
- `POST /tls/token` — generate a new bootstrap token

**Scan state** is held in a module-level `_ScanState` instance in `master/api.py`. The background task runs as an `asyncio.Task`, yields with `await asyncio.sleep(0)` between files, and is cancellable via `/scan/stop`.

**Master env vars:**

| Variable | Config equivalent |
|----------|------------------|
| `PACKA_MASTER_BIND` | `[master].bind` |
| `PACKA_MASTER_API_PORT` | `[master].api_port` |
| `PACKA_MASTER_PREFIX` | `[master.paths].prefix` |
| `PACKA_MASTER_EXTENSIONS` | `[master.scan].extensions` (comma-separated) |
| `PACKA_MASTER_MIN_SIZE` | `[master.scan].min_size` (MB) |
| `PACKA_MASTER_MAX_SIZE` | `[master.scan].max_size` (MB) |
| `PACKA_MASTER_CHECKSUM_BYTES` | `[master.scan].checksum_bytes` |
| `PACKA_MASTER_PROBE_BATCH_SIZE` | `[master.scan].probe_batch_size` |
| `PACKA_MASTER_PROBE_INTERVAL` | `[master.scan].probe_interval` |
| `PACKA_MASTER_SCAN_PERIODIC_ENABLED` | `[master.scan.periodic].enabled` |
| `PACKA_MASTER_SCAN_INTERVAL` | `[master.scan.periodic].interval` (seconds) |
| `PACKA_MASTER_TLS_CERT` | `[master.tls].cert` |
| `PACKA_MASTER_TLS_KEY` | `[master.tls].key` |
| `PACKA_MASTER_TLS_DISABLED` | `[master.tls].disabled` |
| `PACKA_TLS_CA` | `[tls].ca` (shared) |

## Worker

**Entry point:** `python -m worker.main`

| File | Purpose |
|------|---------|
| `worker/main.py` | CLI (`--bind`, `--api-port`, `--master-host`, `--master-port`, `--advertise-host`, `--config`); resolves worker ID, registers with master, sets `worker_state` fields |
| `worker/api.py` | FastAPI app; lifespan sets `worker_state.tls`, starts `worker_loop` and `poller_loop` |
| `worker/worker.py` | `worker_loop` — processes one job at a time from `worker_state.queue`; `recover()` called at startup |
| `worker/poller.py` | `poller_loop` — polls master every `poll_interval` seconds when queue is empty; claims jobs and enqueues them |
| `worker/state.py` | `WorkerState` (active, record_id, queue, progress, proc, worker_id, worker_config_id, master_url, tls) and `FfmpegProgress` dataclass |
| `worker/identity.py` | `get_or_create_worker_id()` / `get_stored_worker_id()` — persists worker ID in `worker_settings` table |
| `worker/database.py` | Engine + `SessionLocal` + `get_db()` for `worker.db` |

**Worker ID resolution** (in `worker/main.py`):
1. Use `worker.id` from config / `PACKA_WORKER_ID` env / `--id` (whichever wins per priority order)
2. Otherwise look up persisted ID from `worker_settings` table in `worker.db`
3. Otherwise generate a UUID4, store it, and use it

If config has an ID and the DB has a different one, a warning is logged.

**Worker queue:** jobs are `asyncio.Queue` items. Poller and API both enqueue; worker processes sequentially. At startup `recover()`:
1. Finds `PROCESSING` records → deletes partial output files → resets to `PENDING`
2. Finds all `PENDING` records → enqueues in ID order

**Poller:** runs as an asyncio task alongside `worker_loop`. Polls when `worker_state.queued == 0 and not worker_state.active`. On each claim it creates worker DB records (applying `path_prefix`) and enqueues jobs. If master is unreachable it logs and retries after `poll_interval` seconds.

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
- `POST /tls/bootstrap` — fetch cert bundle from master using a bootstrap token and self-restart
- `POST /restart` — restart worker process in-place via `os.execv`

**Worker env vars:**

| Variable | Config equivalent |
|----------|------------------|
| `PACKA_WORKER_BIND` | `[worker].bind` |
| `PACKA_WORKER_API_PORT` | `[worker].api_port` |
| `PACKA_WORKER_ID` | `[worker].id` |
| `PACKA_WORKER_PREFIX` | `[worker.paths].prefix` |
| `PACKA_WORKER_MASTER_HOST` | `[worker].master_host` |
| `PACKA_WORKER_MASTER_PORT` | `[worker].master_port` |
| `PACKA_WORKER_ADVERTISE_HOST` | `[worker].advertise_host` |
| `PACKA_WORKER_FFMPEG_BIN` | `[worker.ffmpeg].bin` |
| `PACKA_WORKER_FFMPEG_OUTPUT_DIR` | `[worker.ffmpeg].output_dir` |
| `PACKA_WORKER_FFMPEG_EXTRA_ARGS` | `[worker.ffmpeg].extra_args` |
| `PACKA_WORKER_BATCH_SIZE` | `[worker.worker].batch_size` |
| `PACKA_WORKER_POLL_INTERVAL` | `[worker.worker].poll_interval` |
| `PACKA_WORKER_BOOTSTRAP_TOKEN` | `[worker].bootstrap_token` |
| `PACKA_WORKER_TLS_CERT` | `[worker.tls].cert` |
| `PACKA_WORKER_TLS_KEY` | `[worker.tls].key` |
| `PACKA_TLS_CA` | `[tls].ca` (shared) |

## Web frontend

**Entry point:** `python -m web.main`

Browser talks HTTP(S) to the web process. Web process talks mTLS to master and workers (BFF pattern).

| File | Purpose |
|------|---------|
| `web/main.py` | CLI (`--bind`, `--port`, `--master-host`, `--master-port`, `--config`), starts uvicorn |
| `web/app.py` | FastAPI app; session-based auth, Jinja2 dashboard, login/logout, BFF action endpoints |
| `web/client.py` | `fetch_dashboard()` — fans out to master + all workers in parallel with one `AsyncClient` |
| `web/config.py` | `WebConfig` dataclass + `load_web()` — reads `[web]` section + env vars |
| `web/templates/` | `base.html`, `login.html`, `dashboard.html` |
| `web/static/` | `style.css` (all CSS with oklch design tokens), `dashboard.js` (all dashboard JS) |
| `web/static/fonts/` | IBM Plex Sans (variable) and IBM Plex Mono (400, 500) woff2 files — served locally |

**Dashboard** is a single-page app rendered entirely in `dashboard.js`. It auto-refreshes every 3 seconds and has six tabs:

- **Overview** — 8 clickable status chips (counts per status). Clicking any chip opens a modal listing matching files with checkboxes and bulk actions (Set → Pending / Cancelled, Delete, Queue to worker).
- **Files** — filterable by status chip, searchable by filename or worker name. Bulk actions (same as modal) live in the table header row so the list never jumps. Prefix stripped from displayed paths; full path in `title`.
- **Statistics** — aggregated and per-worker stats: jobs, input/output bytes, space saved, compression ratio, avg duration.
- **Workers** — per-worker cards with live ffmpeg progress (%, FPS, speed, bitrate, current→projected size), encoder selector, batch size, pause/drain/stop/sleep controls and settings panel. When master has TLS active, worker cards that are not yet onboarded show an **Onboard TLS** button and have all other controls disabled.
- **Master** — four stat cards (avg conversion, probe rate, scan speed, probe queue), probe-progress bar, scanner controls, and editable master configuration form. Each row has per-value Save / Restore from file / Restore from env / Default / Revert buttons; edits are PATCHed to the database layer and applied live (`requires_restart` fields pop a restart-required toast). The underlying source (`default`/`file`/`env`/`db`/`cli`) is tracked server-side and decides whether the Revert button appears, but it's not rendered as a badge.
- **Settings** — poll interval selector.

**Polling guard:** `isEditing()` returns true when any input/select/textarea has focus, any worker settings panel is open, or any modal files are selected. When true, `renderActiveTab()` and `updateFromData()` are skipped so in-progress edits are never wiped by a poll.

**Status modal:** opened from overview chips or from JS. `ST.modalSelected` tracks selection; after any action `fetchAll()` is awaited and `renderStatusModal()` re-renders in place. Bulk-action controls live in the `<thead>` row (fixed height `36px`) so the file list never jumps.

**Themes:** `data-theme` attribute on `<html>`. Inline `<script>` in `<head>` applies the stored preference before first render (no flash). IBM Plex fonts served from `/static/fonts/` — no Google Fonts request.

**BFF action endpoints in `web/app.py`:**
- `POST /data/scan/start|stop`
- `POST /data/files/pending|cancel|delete|assign`
- `POST /data/worker/action` (stop/pause/resume/drain/sleep/wake — validated against allowlist)
- `POST /data/worker/encoder`, `GET/POST /data/worker` (settings)
- `POST /data/transfer`, `POST /data/workers/register`, `DELETE /data/workers/{worker_id}`
- `GET /data/dashboard`, `GET /data/files`, `GET /data/files/duplicate-pairs`
- `GET /data/stats`, `GET /data/stats/worker`
- `PATCH /data/master/config/{key}`, `DELETE /data/master/config/{key}`, `POST /data/master/config/{key}/restore` — thin proxies to the master's `/master/config` CRUD endpoints
- `GET /data/tls/token`, `POST /data/tls/token`, `GET /data/tls/status` — thin proxies to master TLS endpoints
- `POST /data/worker/tls/onboard` — generate a new token, send it to the worker, trigger worker restart
- `POST /restart` — restart the web process in-place via `os.execv`
- `GET /setup/bootstrap`, `POST /setup/bootstrap` — standalone bootstrap token form (shown when web has no TLS certs)

**Auth:** `SessionMiddleware` (starlette) with `secret_key` from config. Session stores `{"user": username}` after successful login. Auth is **optional** — if `username` or `password` is empty/missing, all routes are accessible without login. `secret_key` is **auto-generated and persisted in `web.db`** so sessions survive restarts.

**TLS bootstrap:** when the web process starts without TLS certs, the login page shows a "Bootstrap token" input above the login form. The user pastes the token printed by master, clicks "Bootstrap TLS", and the web process restarts with TLS enabled. The first connection to master uses TOFU (`verify=False`) to fetch the CA cert.

**Web env vars:**

| Variable | Config equivalent |
|----------|------------------|
| `PACKA_WEB_BIND` | `[web].bind` |
| `PACKA_WEB_PORT` | `[web].port` |
| `PACKA_WEB_USERNAME` | `[web].username` |
| `PACKA_WEB_PASSWORD` | `[web].password` |
| `PACKA_WEB_SECRET_KEY` | `[web].secret_key` |
| `PACKA_WEB_BOOTSTRAP_TOKEN` | `[web].bootstrap_token` |
| `PACKA_WEB_MASTER_HOST` | `[web].master_host` |
| `PACKA_WEB_MASTER_PORT` | `[web].master_port` |
| `PACKA_WEB_TLS_CERT` | `[web.tls].cert` |
| `PACKA_WEB_TLS_KEY` | `[web.tls].key` |
| `PACKA_TLS_CA` | `[tls].ca` (shared) |

## mTLS

mTLS is opt-in and recommended for untrusted networks. Master auto-generates a CA and server cert on first start (stored in `master.db`). It prints a **bootstrap token** (valid 10 minutes, multi-use) to the log. Workers and the web process exchange this token for a signed client cert, which is stored in `worker.db` / `web.db` and loaded on subsequent starts.

The first connection to master uses TOFU (Trust On First Use) — `verify=False` to fetch the CA cert bundle. After bootstrap all connections verify against the CA.

Opt out entirely with `[master.tls] disabled = true`. BYO certs are supported by setting `cert`/`key` in the relevant `[*.tls]` section.

`shared/tls.py` provides four helpers:
- `scheme(tls)` — returns `"https"` or `"http"`
- `httpx_kwargs(tls)` — returns `{"verify": ca, "cert": (cert, key)}` or `{}`
- `uvicorn_kwargs(tls)` — uvicorn SSL kwargs with `ssl_cert_reqs=ssl.CERT_REQUIRED` (master/worker servers)
- `uvicorn_server_kwargs(tls)` — same but without `ssl_cert_reqs` (web server, browsers don't send client certs)

**Behaviour matrix:**

| Master TLS | Worker TLS | Result |
|------------|-----------|--------|
| enabled | enabled | mTLS on all connections |
| disabled | disabled | plain HTTP |
| enabled | disabled | master rejects worker (no client cert) |
| disabled | enabled | worker connects without TLS |

`worker_state.tls` is set in `worker/api.py` lifespan (from `_config.tls`) so `worker.py` and `poller.py` can use it without importing `_config`.

## Config file (TOML)

All nodes share one config file (`packa.toml`). Parsed with `tomllib` (stdlib, Python 3.11+).

- `load_master(path|None)` reads `[master]` + `[tls]` / `[master.tls]`
- `load_worker(path|None)` reads `[worker]` + `[tls]` / `[worker.tls]`; falls back to `master.paths.prefix` if worker prefix is empty
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

[master.tls]               # auto-generated on first start; opt out with:
# disabled = true
# cert = "/etc/packa/master.crt"   # BYO cert
# key  = "/etc/packa/master.key"
```

**Worker config fields:**

```toml
[worker]
bind             = "localhost"
api_port         = 8000
master_host      = "localhost"
master_port      = 9000
# advertise_host = ""      # auto-detected if omitted
id               = "storage-01"   # omit to use persisted UUID from worker.db
# bootstrap_token = ""     # copy from master log on first run; stored after bootstrap

[worker.paths]
prefix = "/mnt/files/"    # omit to fall back to master.paths.prefix

[worker.ffmpeg]
bin        = "ffmpeg"
output_dir = "/mnt/output"
extra_args = ""

[worker.worker]
batch_size    = 1
poll_interval = 5

[worker.tls]                # BYO cert (overrides bootstrapped certs)
# cert = "/etc/packa/worker.crt"
# key  = "/etc/packa/worker.key"
```

**Web config fields:**

```toml
[web]
bind             = "localhost"
port             = 8080
username         = "admin"    # optional — omit username or password to disable auth entirely
password         = "secret"
# bootstrap_token = ""       # copy from master log on first run
master_host      = "localhost"
master_port      = 9000

[web.tls]                    # BYO cert (overrides bootstrapped certs)
# cert = "/etc/packa/web.crt"
# key  = "/etc/packa/web.key"
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

# Worker (registers automatically, ffmpeg optional)
python -m worker.main --config packa.toml

# Web dashboard
python -m web.main --config packa.toml
```

## Key design decisions

- **Pull model:** workers poll master for work via `POST /jobs/claim`. Master never pushes. Workers continue processing queued jobs if master goes down.
- **Shared ID:** master auto-increments the ID, returns it in `/jobs/claim`. Worker stores the record under that ID. Both databases use the same ID for the same file.
- **worker_id column:** `FileRecord.worker_id` (string) in master's DB records which worker holds the file, using the worker's config `id` field.
- **Persistent worker ID:** if `worker.id` is omitted from config and env, the ID is looked up in `worker_settings` in `worker.db`. If absent, a UUID4 is generated and stored so the same ID survives restarts.
- **No file transfer:** only metadata travels over HTTP. Files are accessed by workers directly via the filesystem (path prefix translation).
- **Single config file:** `packa.toml` has `[master]`, `[worker]`, `[web]`, and optional `[tls]` sections. Each process reads only its own section.
- **Config priority:** config file < env var < CLI flag. Load functions apply env vars internally; CLI overrides happen in `main()` with `default=None` args.
- **mTLS optional:** enabled when all three TLS fields (cert, key, ca) are set for a node. `shared/tls.py` helpers used by uvicorn setup and every httpx call.
- **Web as BFF:** browser talks to web process, web process talks mTLS to master/workers. Web holds its own client certificate.
- **asyncio throughout:** uvicorn, worker loop, poller loop, ffmpeg subprocess and progress streaming all share one event loop per process.
- **Config before app:** `set_config()` must be called before uvicorn starts. It sets a module-level `_config` in each `api.py`. The lifespan reads `_config` to start background tasks.
