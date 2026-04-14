# Packa — developer notes

Distributed system where a **master** node receives file paths via API, collects metadata and distributes it to one or more **slave** nodes. Slaves optionally run ffmpeg on received files. All code is Python 3.11+.

## Repository layout

```
master/         Master node — receives file paths, sends metadata to slaves
slave/          Slave node — receives metadata, optionally runs ffmpeg
shared/         Code shared by both nodes (models, schemas, crud, config)
master.example.toml
slave.example.toml
requirements.txt
```

## Shared package

| File | Purpose |
|------|---------|
| `shared/base.py` | SQLAlchemy `DeclarativeBase` — imported by both `master/database.py` and `slave/database.py` |
| `shared/models.py` | `FileRecord` ORM model and `FileStatus` enum |
| `shared/schemas.py` | Pydantic schemas (`FileRecordCreate`, `FileRecordOut`, `StatusUpdate`) |
| `shared/crud.py` | All DB operations — takes a `Session` parameter, no DB knowledge of its own |
| `shared/config.py` | `Config` + `FfmpegConfig` dataclasses; `load(path)` parses TOML |

## Databases

Each node has its own SQLite database with **identical schema**.

- `master.db` — created in the working directory when master starts
- `slave.db` — created in the working directory when slave starts

Master assigns the record ID. Slave stores the record under the same ID, so both databases share IDs for the same file.

## FileStatus enum

```
PENDING → PROCESSING → COMPLETE
                     → DISCARDED  (output >= source size, output file deleted)
                     → ERROR
```

## Master

**Entry point:** `python -m master.master`

| File | Purpose |
|------|---------|
| `master/master.py` | CLI (`--bind`, `--api-port`, `--config`), starts uvicorn |
| `master/api.py` | FastAPI app; module-level `_config` set via `set_config()` before uvicorn starts |
| `master/registry.py` | In-memory `SlaveRegistry`; round-robin via `next_slave()`; slaves identified by numeric `id` (int, auto) and `config_id` (string, from slave config file) |
| `master/scanner.py` | `collect(file_path) → VideoFile` — reads stat, computes checksum |
| `master/sender.py` | `send_metadata()` — strips master path prefix before POSTing to slave |
| `master/database.py` | Engine + session for `master.db` |

**Checksum:** `SHA-256("{file_name}{file_path}{c_time}{m_time}")` — ID is not included.

**Path prefix:** master strips its own `path_prefix` from `file_path` before sending. The relative path travels over the wire. Slave prepends its own `path_prefix`.

**Key API endpoints:**
- `POST /slaves` — slave registration (called automatically by slave on startup)
- `POST /transfer {"file_path": "..."}` — trigger metadata collection and distribution
- `POST /files/{id}/sync {"slave_id": N}` — called by slave after ffmpeg completes; master fetches the record from slave and updates its own DB
- `GET /files?status=...` — query master DB

## Slave

**Entry point:** `python -m slave.main`

| File | Purpose |
|------|---------|
| `slave/main.py` | CLI (`--bind`, `--api-port`, `--master-host`, `--master-port`, `--advertise-host`, `--config`); registers with master, sets module-level `_config` in `api.py` via `set_config()` |
| `slave/api.py` | FastAPI app; lifespan starts `worker_loop`; `submit_file` enqueues jobs |
| `slave/worker.py` | `worker_loop` — processes one job at a time from `worker_state.queue`; `recover()` called at startup |
| `slave/state.py` | `WorkerState` (active, record_id, queue, progress, slave_id, master_url) and `FfmpegProgress` dataclass |
| `slave/database.py` | Engine + session for `slave.db` |

**Worker queue:** jobs are `asyncio.Queue` items. API enqueues, worker processes sequentially. At startup `recover()`:
1. Finds `PROCESSING` records → deletes partial output files → resets to `PENDING`
2. Finds all `PENDING` records → enqueues in ID order

**ffmpeg invocation:**
```
ffmpeg -i {file_path} -map 0 -c copy [extra_args] -progress pipe:1 -nostats {output_path}
```
All streams copied. `ffprobe` (derived from `ffmpeg.bin` path) fetches duration for progress calculation. stdout is streamed line-by-line for live progress; stderr collected for error logging.

**After conversion:** if `output_size >= source_size` the output file is deleted and status is set to `DISCARDED`. Otherwise `COMPLETE`, then `POST master/files/{id}/sync`.

**Key API endpoints:**
- `GET /status` — idle/processing state, queue depth, live ffmpeg progress
- `GET /files?status=...` — filterable, all fields including `output_size`, `started_at`, `finished_at`
- `POST /files` — called by master only (creates record + enqueues ffmpeg job)

## Config files (TOML)

See `master.example.toml` and `slave.example.toml`. Parsed with `tomllib` (stdlib, Python 3.11+).

**Slave config fields:**

```toml
id = "storage-01"          # unique string ID sent to master on registration

[paths]
prefix = "/mnt/files/"     # prepended to relative paths received from master

[ffmpeg]
bin = "ffmpeg"
output_dir = "/mnt/output" # if empty, ffmpeg is not run
extra_args = ""            # appended after -map 0 -c copy, parsed with shlex
```

**Master config fields:**

```toml
[paths]
prefix = "/mnt/data/"      # stripped from file_path before sending to slave
```

## Running

```bash
pip install -r requirements.txt

# Master
python -m master.master --config master.toml

# Slave (registers automatically, ffmpeg optional)
python -m slave.main --master-host 192.168.1.5 --config slave.toml
```

## Key design decisions

- **Shared ID:** master auto-increments the ID, sends it in the metadata payload (`FileRecordCreate.id`). Slave stores the record under that ID. Both databases use the same ID for the same file.
- **slave_id column:** `FileRecord.slave_id` (string) in master's DB records which slave holds the file, using the slave's config `id` field.
- **No file transfer:** only metadata travels over HTTP. Files are accessed by slaves directly via the filesystem (path prefix translation).
- **asyncio throughout:** uvicorn, worker loop, ffmpeg subprocess and progress streaming all share one event loop per process.
- **Config before app:** `set_config()` must be called before uvicorn starts. It sets a module-level `_config` in `api.py`. The lifespan reads `_config` to start (or skip) the worker loop.
