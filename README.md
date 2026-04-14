# Packa

Distributed system for transferring video file metadata from a master to one or more slaves. The master receives file paths via API, collects metadata and distributes it to registered slaves using round-robin. Slaves optionally run ffmpeg on received files.

No files are transferred over the network — slaves access files directly via the filesystem. Only metadata travels over HTTP.

## Architecture

```
master/          — receives file paths, collects metadata, distributes to slaves
slave/           — receives metadata, runs ffmpeg, reports back to master
shared/          — common models, schemas, CRUD and config (used by both)
```

### Ports

| Service        | Protocol | Default |
|----------------|----------|---------|
| Master API     | HTTP     | 9000    |
| Slave API      | HTTP     | 8000    |

### Databases

Each node has its own SQLite database with an identical schema. The master assigns the record ID — the slave stores the record under the same ID.

| Node   | File       |
|--------|------------|
| Master | master.db  |
| Slave  | slave.db   |

### Path prefix translation

Files are not transferred — instead, a path is translated between nodes:

```
Master file:  /mnt/data/shows/ep1.mkv
              strip master prefix "/mnt/data/"
              ──────────────────────────────►  shows/ep1.mkv  (sent over API)
              prepend slave prefix "/mnt/files/"
Slave file:   /mnt/files/shows/ep1.mkv
```

---

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.11+. ffmpeg and ffprobe must be installed on slave nodes.

---

## Configuration

Copy the example files and adjust:

```bash
cp master.example.toml master.toml
cp slave.example.toml slave.toml
```

### Master config

```toml
[paths]
prefix = "/mnt/data/"   # stripped from file_path before sending to slave
```

### Slave config

```toml
id = "storage-01"       # unique string ID, used by master to track which slave holds which file

[paths]
prefix = "/mnt/files/"  # prepended to relative paths received from master

[ffmpeg]
bin = "ffmpeg"
output_dir = "/mnt/output"   # directory for converted files; omit to disable ffmpeg
extra_args = ""              # extra ffmpeg arguments (appended after -map 0 -c copy)
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
python -m master.master --config master.toml
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
python -m slave.main --master-host 192.168.1.5 --config slave.toml
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

#### Start a transfer
```
POST /transfer
```
```json
{ "file_path": "/mnt/data/shows/ep1.mkv" }
```

Response `201 Created`:
```json
{
  "record_id": 42,
  "slave_id": 1,
  "slave_host": "192.168.1.10",
  "file_name": "ep1.mkv",
  "file_path": "/mnt/data/shows/ep1.mkv",
  "checksum": "a3f9..."
}
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
GET /files/{id}
```

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
  "slave_id": null,
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
| `pending` | Record created, ffmpeg not yet started |
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
python -m master.master --config master.toml

# 2. Start one or more slaves (each registers with master automatically)
python -m slave.main --master-host 192.168.1.5 --config slave.toml

# 3. Trigger a transfer
curl -X POST http://localhost:9000/transfer \
     -H "Content-Type: application/json" \
     -d '{"file_path": "/mnt/data/shows/ep1.mkv"}'

# 4. Poll status on slave
curl http://192.168.1.10:8000/status

# 5. Check record on master (updated automatically when ffmpeg finishes)
curl http://localhost:9000/files/42
```
