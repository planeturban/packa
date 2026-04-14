# Packa

Distributed system for converting video files. The master receives file paths via API or directory scan, stores metadata, and distributes work to one or more slaves. Slaves pull jobs from master, run ffmpeg, and report results back.

No files are transferred over the network — slaves access files directly via the filesystem. Only metadata travels over HTTP.

## Architecture

```
master/          — accepts file paths, stores metadata, distributes jobs to slaves
slave/           — polls master for jobs, runs ffmpeg, reports back
shared/          — common models, schemas, CRUD and config (used by both)
```

### Ports

| Service    | Protocol | Default |
|------------|----------|---------|
| Master API | HTTP     | 9000    |
| Slave API  | HTTP     | 8000    |

### Databases

Each node has its own SQLite database with an identical schema. The master assigns the record ID — the slave stores the record under the same ID.

| Node   | File      |
|--------|-----------|
| Master | master.db |
| Slave  | slave.db  |

### Path prefix translation

Files are not transferred — instead, a path is translated between nodes:

```
Master file:  /mnt/data/shows/ep1.mkv
              strip master prefix "/mnt/data/"
              ──────────────────────────────►  shows/ep1.mkv  (sent over API)
              prepend slave prefix "/mnt/files/"
Slave file:   /mnt/files/shows/ep1.mkv
```

### Pull model

Slaves poll master for work. When a slave's queue is empty, it calls `POST /jobs/claim` to fetch one or more pending jobs. The master marks those records as `assigned` and returns relative file paths. The slave creates local DB records, applies its path prefix, and enqueues the jobs for ffmpeg.

If master goes down, the slave continues processing whatever is already in its queue.

---

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.11+. ffmpeg and ffprobe must be installed on slave nodes.

---

## Configuration

Both master and slave share one config file:

```bash
cp packa.example.toml packa.toml
```

### Master section

```toml
[master.paths]
prefix = "/mnt/data/"   # root path: stripped from file paths sent to slaves,
                        # and used as the scan root for POST /scan/start

[master.scan]
extensions = [".mkv", ".mp4", ".avi", ".mov"]
```

### Slave section

```toml
[slave]
id = "storage-01"       # unique string ID, used by master to track which slave holds which file

[slave.paths]
prefix = "/mnt/files/"  # prepended to relative paths received from master
                        # if omitted, master.paths.prefix is used instead

[slave.ffmpeg]
bin = "ffmpeg"
output_dir = "/mnt/output"   # directory for converted files; leave empty to disable ffmpeg
extra_args = ""              # extra ffmpeg arguments (appended after -map 0 -c copy)

[slave.worker]
batch_size = 1       # number of jobs to claim from master per poll
poll_interval = 5    # seconds between poll attempts when queue is empty
```

---

## Running

### Master

```bash
python -m master.master [--bind ADDRESS] [--api-port PORT] [--config FILE]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--bind` | `0.0.0.0` | Address to bind the API server |
| `--api-port` | `9000` | API port |
| `--config` | — | Path to TOML config file |

**Example:**
```bash
python -m master.master --config packa.toml
```

### Slave

```bash
python -m slave.main [--bind ADDRESS] [--api-port PORT]
                     [--master-host HOST] [--master-port PORT]
                     [--advertise-host HOST] [--config FILE]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--bind` | `0.0.0.0` | Address to bind the API server |
| `--api-port` | `8000` | API port |
| `--master-host` | — | Master hostname/IP (omit to run standalone) |
| `--master-port` | `9000` | Master API port |
| `--advertise-host` | auto | IP/hostname advertised to master. Auto-detected if omitted |
| `--config` | — | Path to TOML config file |

**Example:**
```bash
python -m slave.main --master-host 192.168.1.5 --config packa.toml
```

---

## API

### Master API (port 9000)

#### Register a slave
```
POST /slaves
```
```json
{ "config_id": "storage-01", "host": "192.168.1.10", "api_port": 8000, "file_port": 0 }
```
Called automatically by the slave on startup.

#### List slaves
```
GET /slaves
```

#### Deregister a slave
```
DELETE /slaves/{id}
```

#### Add a single file
```
POST /transfer
```
```json
{ "file_path": "/mnt/data/shows/ep1.mkv" }
```
Collects metadata for the file and creates a `pending` record. Returns the full record.

#### Claim jobs (pull model)
```
POST /jobs/claim
```
```json
{ "slave_id": "storage-01", "count": 1 }
```
Returns up to `count` pending records and marks them `assigned`. Called automatically by the slave poller.

Response:
```json
[
  {
    "id": 42,
    "file_name": "ep1.mkv",
    "file_path": "shows/ep1.mkv",
    "c_time": 1744123456.789,
    "m_time": 1744123456.789,
    "checksum": "a3f9..."
  }
]
```

#### Sync record from slave
```
POST /files/{id}/sync
```
```json
{ "slave_id": 1 }
```
Called automatically by the slave after ffmpeg finishes. Master fetches the full record from the slave and updates its own database.

#### Get records
```
GET /files
GET /files?status=pending
GET /files/{id}
```

#### Directory scan
```
POST /scan/start    — start a background scan of the configured scan.dir
POST /scan/stop     — cancel a running scan
GET  /scan/status   — current scan progress
```

`POST /scan/start` returns `202 Accepted` immediately. The scan runs in the background and creates a `pending` record for each matching file not already in the database.

`GET /scan/status` response:
```json
{ "running": true, "found": 12, "skipped": 4, "errors": 0 }
```

| Field | Description |
|-------|-------------|
| `found` | New records created during this scan |
| `skipped` | Files already in the database |
| `errors` | Files that could not be read |

---

### Slave API (port 8000)

#### Worker status
```
GET /status
```

Response when idle:
```json
{ "state": "idle", "record_id": null, "queued": 0, "progress": null }
```

Response while processing:
```json
{
  "state": "processing",
  "record_id": 42,
  "queued": 2,
  "progress": {
    "percent": 37.4,
    "speed": 1.82,
    "fps": 45.5,
    "out_time": "00:31:14.520000",
    "eta_seconds": 1043,
    "bitrate": "4821.3kbits/s",
    "current_size_bytes": 872349696,
    "projected_size_bytes": 2331952395
  }
}
```

#### Get records
```
GET /files
GET /files?status=pending
```

Filterable by status. Response:
```json
{
  "id": 42,
  "file_name": "ep1.mkv",
  "file_path": "/mnt/files/shows/ep1.mkv",
  "c_time": 1744123456.789,
  "m_time": 1744123456.789,
  "checksum": "a3f9...",
  "slave_id": "storage-01",
  "status": "complete",
  "pid": 12345,
  "output_size": 820000000,
  "started_at": "2026-04-15T08:00:00+00:00",
  "finished_at": "2026-04-15T08:17:32+00:00",
  "created_at": "2026-04-15T08:00:00+00:00",
  "updated_at": "2026-04-15T08:17:32+00:00"
}
```

#### Update status manually
```
PATCH /files/{id}/status
```
```json
{ "status": "error" }
```

---

## Status values

| Status | Description |
|--------|-------------|
| `pending` | Record created, not yet claimed by a slave |
| `assigned` | Claimed by a slave, not yet processing |
| `processing` | ffmpeg is running |
| `complete` | ffmpeg finished and output is smaller than source |
| `discarded` | ffmpeg finished but output was not smaller than source — output file deleted |
| `error` | ffmpeg exited with a non-zero code |

---

## Checksum

SHA-256 of the concatenated metadata fields:

```
SHA-256("{file_name}{file_path}{c_time}{m_time}")
```

The record ID is not included in the calculation.

---

## ffmpeg

Slaves run ffmpeg with all streams copied:

```
ffmpeg -i {file_path} -map 0 -c copy [extra_args] -progress pipe:1 -nostats {output_path}
```

- All streams (video, audio, subtitles, attachments) are copied without re-encoding
- `ffprobe` (derived from `ffmpeg.bin`) measures source duration for progress calculation
- After conversion, if `output_size >= source_size` the output is discarded
- On restart, any partial output files from interrupted jobs are deleted and those records are re-queued

---

## Example — complete flow

```bash
# 1. Start master
python -m master.master --config packa.toml

# 2. Start one or more slaves (each registers with master automatically)
python -m slave.main --master-host 192.168.1.5 --config packa.toml

# 3a. Queue a single file
curl -X POST http://localhost:9000/transfer \
     -H "Content-Type: application/json" \
     -d '{"file_path": "/mnt/data/shows/ep1.mkv"}'

# 3b. Or scan an entire directory
curl -X POST http://localhost:9000/scan/start

# 4. Poll scan progress
curl http://localhost:9000/scan/status

# 5. Check unclaimed jobs on master
curl http://localhost:9000/files?status=pending

# 6. Poll worker status on slave
curl http://192.168.1.10:8000/status

# 7. Check record on master (updated automatically when ffmpeg finishes)
curl http://localhost:9000/files/42
```
