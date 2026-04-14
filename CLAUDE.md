# Packa — developer notes

Distributed system where a **master** node accepts file paths via API or directory scan, stores metadata, and distributes work to one or more **slave** nodes via a pull model. Slaves poll master for jobs, run ffmpeg, and report results back. All code is Python 3.11+.

## Repository layout

```
master/             Master node — accepts file paths, manages job queue, distributes to slaves
slave/              Slave node — polls master for jobs, runs ffmpeg, reports back
shared/             Code shared by both nodes (models, schemas, crud, config)
packa.example.toml  Single config file for both master and slave
requirements.txt
```

## Shared package

| File | Purpose |
|------|---------|
| `shared/base.py` | SQLAlchemy `DeclarativeBase` — imported by both `master/database.py` and `slave/database.py` |
| `shared/models.py` | `FileRecord` ORM model and `FileStatus` enum |
| `shared/schemas.py` | Pydantic schemas (`FileRecordCreate`, `FileRecordOut`, `StatusUpdate`) |
| `shared/crud.py` | All DB operations — takes a `Session` parameter, no DB knowledge of its own |
| `shared/config.py` | `Config` + sub-configs; `load_master(path)` and `load_slave(path)` parse TOML |

## Databases

Each node has its own SQLite database with **identical schema**.

- `master.db` — created in the working directory when master starts
- `slave.db` — created in the working directory when slave starts

Master assigns the record ID. Slave stores the record under the same ID, so both databases share IDs for the same file.

## FileStatus enum

```
PENDING → ASSIGNED → PROCESSING → COMPLETE
                               → DISCARDED  (output >= source size, output file deleted)
                               → ERROR
```

- `PENDING` — record created, not yet claimed by any slave
- `ASSIGNED` — claimed by a slave via `/jobs/claim`, not yet processing
- `PROCESSING` — ffmpeg is running on the slave
- `COMPLETE` / `DISCARDED` / `ERROR` — terminal states

## Master

**Entry point:** `python -m master.master`

| File | Purpose |
|------|---------|
| `master/master.py` | CLI (`--bind`, `--api-port`, `--config`), starts uvicorn |
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

## Slave

**Entry point:** `python -m slave.main`

| File | Purpose |
|------|---------|
| `slave/main.py` | CLI (`--bind`, `--api-port`, `--master-host`, `--master-port`, `--advertise-host`, `--config`); registers with master, sets `worker_state.slave_id`, `slave_config_id`, `master_url` |
| `slave/api.py` | FastAPI app; lifespan starts `worker_loop` and `poller_loop` |
| `slave/worker.py` | `worker_loop` — processes one job at a time from `worker_state.queue`; `recover()` called at startup |
| `slave/poller.py` | `poller_loop` — polls master every `poll_interval` seconds when queue is empty; claims jobs and enqueues them |
| `slave/state.py` | `WorkerState` (active, record_id, queue, progress, slave_id, slave_config_id, master_url) and `FfmpegProgress` dataclass |
| `slave/database.py` | Engine + `SessionLocal` + `get_db()` for `slave.db` |

**Worker queue:** jobs are `asyncio.Queue` items. Poller and API both enqueue; worker processes sequentially. At startup `recover()`:
1. Finds `PROCESSING` records → deletes partial output files → resets to `PENDING`
2. Finds all `PENDING` records → enqueues in ID order

**Poller:** runs as an asyncio task alongside `worker_loop`. Polls when `worker_state.queued == 0 and not worker_state.active`. On each claim it creates slave DB records (applying `path_prefix`) and enqueues jobs. If master is unreachable it logs and retries after `poll_interval` seconds.

**ffmpeg invocation:**
```
ffmpeg -i {file_path} -map 0 -c copy [extra_args] -progress pipe:1 -nostats {output_path}
```
All streams copied. `ffprobe` (derived from `ffmpeg.bin` path) fetches duration for progress calculation. stdout is streamed line-by-line for live progress; stderr collected for error logging.

**After conversion:** if `output_size >= source_size` the output file is deleted and status is set to `DISCARDED`. Otherwise `COMPLETE`, then `POST master/files/{id}/sync`.

**Key API endpoints:**
- `GET /status` — idle/processing state, queue depth, live ffmpeg progress
- `GET /files?status=...` — filterable, all fields including `output_size`, `started_at`, `finished_at`
- `POST /files` — called by master only (creates record + enqueues ffmpeg job); also used indirectly by poller

## Config file (TOML)

Both master and slave use the same config file (`packa.toml`). Parsed with `tomllib` (stdlib, Python 3.11+).

- `load_master(path)` reads the `[master]` section
- `load_slave(path)` reads the `[slave]` section; if `slave.paths.prefix` is empty, falls back to `master.paths.prefix`

**Master config fields (`[master]`):**

```toml
[master.paths]
prefix = "/mnt/data/"      # root path: stripped from file paths sent to slaves
                           # and used as the scan root for POST /scan/start

[master.scan]
extensions = [".mkv", ".mp4", ".avi", ".mov"]
```

**Slave config fields (`[slave]`):**

```toml
[slave]
id = "storage-01"          # unique string ID sent to master on registration

[slave.paths]
prefix = "/mnt/files/"     # prepended to relative paths received from master
                           # if omitted, master.paths.prefix is used instead

[slave.ffmpeg]
bin = "ffmpeg"
output_dir = "/mnt/output" # if empty, ffmpeg is not run
extra_args = ""            # appended after -map 0 -c copy, parsed with shlex

[slave.worker]
batch_size = 1             # jobs to claim per poll
poll_interval = 5          # seconds between poll attempts
```

## Running

```bash
pip install -r requirements.txt

# Master
python -m master.master --config packa.toml

# Slave (registers automatically, ffmpeg optional)
python -m slave.main --master-host 192.168.1.5 --config packa.toml
```

## Key design decisions

- **Pull model:** slaves poll master for work via `POST /jobs/claim`. Master never pushes. Slaves continue processing queued jobs if master goes down.
- **Shared ID:** master auto-increments the ID, returns it in `/jobs/claim`. Slave stores the record under that ID. Both databases use the same ID for the same file.
- **slave_id column:** `FileRecord.slave_id` (string) in master's DB records which slave holds the file, using the slave's config `id` field.
- **No file transfer:** only metadata travels over HTTP. Files are accessed by slaves directly via the filesystem (path prefix translation).
- **Single config file:** `packa.toml` has `[master]` and `[slave]` sections. Each node reads only its own section via `load_master()` / `load_slave()`.
- **asyncio throughout:** uvicorn, worker loop, poller loop, ffmpeg subprocess and progress streaming all share one event loop per process.
- **Config before app:** `set_config()` must be called before uvicorn starts. It sets a module-level `_config` in `api.py`. The lifespan reads `_config` to start (or skip) the worker and poller loops.
