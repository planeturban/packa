# Packa

Distributed system for converting video files. The master receives file paths via API or directory scan, stores metadata, and distributes work to one or more slaves. Slaves pull jobs from master, run ffmpeg, and report results back.

No files are transferred over the network — slaves access files directly via the filesystem. Only metadata travels over HTTP.

## Architecture

```
master/          — accepts file paths, stores metadata, distributes jobs to slaves
slave/           — polls master for jobs, runs ffmpeg, reports back
web/             — browser dashboard (BFF: talks mTLS to master/slaves, plain HTTP to browser)
shared/          — common models, schemas, CRUD, config and TLS helpers (used by all)
```

### Ports

| Service    | Protocol    | Default |
|------------|-------------|---------|
| Master API | HTTP(S)     | 9000    |
| Slave API  | HTTP(S)     | 8000    |
| Web UI     | HTTP(S)     | 8080    |

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

All three processes share one config file. Settings are applied in this order — later wins:

```
config file  <  environment variable  <  CLI flag
```

Copy the example file and adjust values:

```bash
cp packa.example.toml packa.toml
```

### Master section

```toml
[master]
bind     = "localhost"   # use "any" for 0.0.0.0
api_port = 9000

[master.paths]
prefix = "/mnt/data/"   # root path: stripped from file paths sent to slaves,
                        # and used as the scan root for POST /scan/start

[master.scan]
extensions = [".mkv", ".mp4", ".avi", ".mov"]
```

#### Master environment variables

| Variable | Config equivalent |
|----------|-------------------|
| `PACKA_MASTER_BIND` | `master.bind` |
| `PACKA_MASTER_API_PORT` | `master.api_port` |
| `PACKA_MASTER_PREFIX` | `master.paths.prefix` |
| `PACKA_MASTER_EXTENSIONS` | `master.scan.extensions` (comma-separated) |
| `PACKA_MASTER_TLS_CERT` | `master.tls.cert` |
| `PACKA_MASTER_TLS_KEY` | `master.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` (shared) |

### Slave section

```toml
[slave]
bind        = "localhost"   # use "any" for 0.0.0.0
api_port    = 8000
master_host = "localhost"
master_port = 9000
id          = "storage-01"  # unique string ID, used by master to track which slave holds which file
                            # if omitted, a UUID is loaded from slave.db (or generated on first run)

[slave.paths]
prefix = "/mnt/files/"  # prepended to relative paths received from master
                        # if omitted, master.paths.prefix is used instead

[slave.ffmpeg]
bin        = "ffmpeg"
output_dir = "/mnt/output"   # directory for converted files; leave empty to disable ffmpeg
extra_args = ""              # extra ffmpeg arguments (appended after video codec args)
encoder    = "libx265"       # default encoder: libx265 | nvenc | vaapi | videotoolbox
                             # can also be changed at runtime from the web dashboard
# vaapi_device = "/dev/dri/renderD128"   # render device for vaapi encoder
# encoders = ["libx265", "videotoolbox"] # encoders shown in the web dashboard dropdown
                                         # defaults to all four if omitted

[slave.worker]
batch_size    = 1   # number of jobs to claim from master per poll
poll_interval = 5   # seconds between poll attempts when queue is empty
```

#### Per-encoder ffmpeg argument overrides

Each encoder has built-in defaults. Add a `[slave.ffmpeg.<name>]` section to override for this machine only — omit any section to use the defaults.

| Key | Description |
|-----|-------------|
| `pre_input` | Arguments inserted before `-i` (e.g. hardware device init) |
| `video_args` | Video codec arguments replacing the encoder's default flags |

```toml
# Built-in defaults — shown here so you can copy and adjust:

[slave.ffmpeg.libx265]
video_args = "-c:v libx265"

[slave.ffmpeg.nvenc]
video_args = "-c:v hevc_nvenc -preset p5 -cq 24"

[slave.ffmpeg.vaapi]
pre_input  = "-vaapi_device /dev/dri/renderD128"
video_args = "-c:v hevc_vaapi -vf format=nv12,hwupload -qp 24"

[slave.ffmpeg.videotoolbox]
video_args = "-c:v hevc_videotoolbox -q:v 65"
```

#### Slave environment variables

| Variable | Config equivalent |
|----------|-------------------|
| `PACKA_SLAVE_BIND` | `slave.bind` |
| `PACKA_SLAVE_API_PORT` | `slave.api_port` |
| `PACKA_SLAVE_MASTER_HOST` | `slave.master_host` |
| `PACKA_SLAVE_MASTER_PORT` | `slave.master_port` |
| `PACKA_SLAVE_ADVERTISE_HOST` | `slave.advertise_host` |
| `PACKA_SLAVE_ID` | `slave.id` |
| `PACKA_SLAVE_PREFIX` | `slave.paths.prefix` |
| `PACKA_SLAVE_FFMPEG_BIN` | `slave.ffmpeg.bin` |
| `PACKA_SLAVE_FFMPEG_OUTPUT_DIR` | `slave.ffmpeg.output_dir` |
| `PACKA_SLAVE_FFMPEG_EXTRA_ARGS` | `slave.ffmpeg.extra_args` |
| `PACKA_SLAVE_FFMPEG_ENCODER` | `slave.ffmpeg.encoder` |
| `PACKA_SLAVE_FFMPEG_VAAPI_DEVICE` | `slave.ffmpeg.vaapi_device` |
| `PACKA_SLAVE_BATCH_SIZE` | `slave.worker.batch_size` |
| `PACKA_SLAVE_POLL_INTERVAL` | `slave.worker.poll_interval` |
| `PACKA_SLAVE_TLS_CERT` | `slave.tls.cert` |
| `PACKA_SLAVE_TLS_KEY` | `slave.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` (shared) |

### Web section

```toml
[web]
bind        = "localhost"   # use "any" for 0.0.0.0
port        = 8080
master_host = "localhost"
master_port = 9000

# Login credentials — if either is omitted, the dashboard is open without authentication.
username    = "admin"
password    = "change-me"

# Signs session cookies. Auto-generated at startup if omitted (sessions won't survive restarts).
secret_key  = "change-me-use-a-long-random-string"

[web.tls]
cert = "/etc/packa/web.crt"
key  = "/etc/packa/web.key"
```

#### Web environment variables

| Variable | Config equivalent |
|----------|-------------------|
| `PACKA_WEB_BIND` | `web.bind` |
| `PACKA_WEB_PORT` | `web.port` |
| `PACKA_WEB_MASTER_HOST` | `web.master_host` |
| `PACKA_WEB_MASTER_PORT` | `web.master_port` |
| `PACKA_WEB_USERNAME` | `web.username` |
| `PACKA_WEB_PASSWORD` | `web.password` |
| `PACKA_WEB_SECRET_KEY` | `web.secret_key` |
| `PACKA_WEB_TLS_CERT` | `web.tls.cert` |
| `PACKA_WEB_TLS_KEY` | `web.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` (shared) |

### mTLS (optional)

Mutual TLS can be enabled by adding certificate paths to the config. All three fields (ca, cert, key) must be set for a node to enable mTLS.

```toml
[tls]
ca = "/etc/packa/ca.crt"      # CA certificate — shared by all nodes

[master.tls]
cert = "/etc/packa/master.crt"
key  = "/etc/packa/master.key"

[slave.tls]
cert = "/etc/packa/slave.crt"
key  = "/etc/packa/slave.key"

[web.tls]
cert = "/etc/packa/web.crt"
key  = "/etc/packa/web.key"
```

If master has mTLS enabled, slaves without a valid client certificate are rejected. If master has no mTLS, slaves use plain HTTP regardless of their own TLS config.

The web process acts as a backend-for-frontend (BFF): it uses its own client certificate to communicate with master and slaves, while serving plain HTTP(S) to browsers. Browsers never need client certificates.

---

## Running

```bash
# Master
python -m master.master --config packa.toml

# Slave (registers with master automatically on startup)
python -m slave.main --config packa.toml

# Web dashboard
python -m web.main --config packa.toml
```

### Master flags

```
python -m master.master [--bind ADDRESS] [--api-port PORT] [--config FILE]
```

| Flag | Description |
|------|-------------|
| `--bind` | Address to bind (`any` → `0.0.0.0`) |
| `--api-port` | API port |
| `--config` | Path to TOML config file |

### Slave flags

```
python -m slave.main [--bind ADDRESS] [--api-port PORT]
                     [--master-host HOST] [--master-port PORT]
                     [--advertise-host HOST] [--config FILE]
```

| Flag | Description |
|------|-------------|
| `--bind` | Address to bind (`any` → `0.0.0.0`) |
| `--api-port` | API port |
| `--master-host` | Master hostname/IP |
| `--master-port` | Master API port |
| `--advertise-host` | IP/hostname advertised to master (auto-detected if omitted) |
| `--config` | Path to TOML config file |

### Web flags

```
python -m web.main [--bind ADDRESS] [--port PORT]
                   [--master-host HOST] [--master-port PORT]
                   [--config FILE]
```

| Flag | Description |
|------|-------------|
| `--bind` | Address to bind (`any` → `0.0.0.0`) |
| `--port` | HTTP port |
| `--master-host` | Master hostname/IP |
| `--master-port` | Master API port |
| `--config` | Path to TOML config file |

---

## Web dashboard

The web process serves a browser dashboard at port 8080 (default). If `username` and `password` are set in the config, a login page is shown — otherwise the dashboard is accessible without authentication. The dashboard shows:

- Master file counts by status — each is clickable and opens a filtered file list
- Active scan state and progress, periodic scan toggle and interval
- Per-slave status cards: idle/converting/sleeping/draining/unconfigured badge, queue depth, ffmpeg progress with speed/FPS/ETA/size
- Full file table with search, status filter, bulk actions (delete / set to pending) and pagination

Each slave card has controls for Pause, Finish current (drain — completes the active job then sleeps), Stop, and Sleep/Wake. Clicking a slave card opens a detail modal with live progress, encoder selection, and the slave's full file history.

**Encoder selection:** each slave's encoder can be changed at runtime from the detail modal. Select an encoder from the dropdown and press Save. The choice is persisted in the slave's local database and survives restarts. The available encoders shown in the dropdown can be restricted with `encoders = [...]` in `[slave.ffmpeg]`.

**Unconfigured state:** a brand-new slave (no prior configuration in its database) starts in an unconfigured state — it will not poll master or accept jobs until an encoder is selected and saved via the web dashboard.

The page auto-refreshes every 3 seconds with smooth DOM updates (no page reload). The slave modal polls live progress at 500 ms during conversion and 2 s when idle. Checkboxes in the file table survive refreshes.

**Dark mode:** the dashboard respects the system colour scheme preference and has a manual Light / System / Dark picker in the nav bar. The preference is saved to `localStorage`.

---

## API

### Master API (port 9000)

#### Register a slave
```
POST /slaves
```
```json
{ "config_id": "storage-01", "host": "192.168.1.10", "api_port": 8000 }
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
POST /scan/start    — start a background scan of master.paths.prefix
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
{
  "state": "idle",
  "record_id": null,
  "queued": 0,
  "progress": null,
  "paused": false,
  "drain": false,
  "sleeping": false,
  "unconfigured": false,
  "encoder": "libx265",
  "available_encoders": ["libx265", "nvenc", "vaapi", "videotoolbox"]
}
```

Response while processing:
```json
{
  "state": "processing",
  "record_id": 42,
  "queued": 2,
  "paused": false,
  "drain": false,
  "sleeping": false,
  "unconfigured": false,
  "encoder": "nvenc",
  "available_encoders": ["libx265", "nvenc"],
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

#### Encoder settings
```
GET  /settings
POST /settings
```

`GET /settings` returns the current encoder and vaapi device.

`POST /settings` changes the encoder at runtime:
```json
{ "encoder": "nvenc" }
```
Valid values: `libx265`, `nvenc`, `vaapi`, `videotoolbox`. The choice is persisted to the slave database and applied immediately. If the slave was in unconfigured state, this activates it and begins normal operation.

#### Stop current conversion
```
POST /conversion/stop
```
Terminates the running ffmpeg process. Returns `409` if nothing is running. The record status is set to `cancelled` with `cancel_reason = "user"`.

#### Sleep / wake
```
POST /conversion/sleep   — stop polling and processing (even with queued files)
POST /conversion/wake    — resume normal operation
```

`sleep` also cancels any active drain. While sleeping the slave will not poll master or start new jobs. A sleeping slave is visible in the dashboard and can be woken from there.

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
| `discarded` | File was already HEVC — skipped, no conversion needed |
| `cancelled` | Conversion was stopped: by the user, or automatically because output exceeded source size. The `cancel_reason` field is `"user"` or `"auto"`. |
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

Slaves run ffmpeg using the configured encoder preset. The general form is:

```
ffmpeg [pre_input] -i {file_path} -map 0 -c copy {video_args} [extra_args] -progress pipe:1 -nostats {output_path}
```

Where `pre_input` and `video_args` come from the active encoder preset (see [Per-encoder ffmpeg argument overrides](#per-encoder-ffmpeg-argument-overrides) above). `extra_args` is appended from `slave.ffmpeg.extra_args`.

- `ffprobe` (derived from `ffmpeg.bin`) is run first to detect the video codec
- If the file is already HEVC the record is immediately marked `discarded` — ffmpeg is never started
- Audio, subtitles and attachments are always copied without re-encoding (`-map 0 -c copy`)
- Output size is monitored continuously. If the output file grows larger than the source before ffmpeg finishes, ffmpeg is terminated and the record is set to `cancelled` (`cancel_reason = "auto"`)
- After conversion, if `output_size >= source_size` the output file is deleted and the record is set to `cancelled` (`cancel_reason = "auto"`)
- Deleting a file that is currently being converted stops ffmpeg immediately
- On restart, any partial output files from interrupted jobs are deleted and those records are re-queued

---

## Example — complete flow

```bash
# 1. Start master
python -m master.master --config packa.toml

# 2. Start one or more slaves (each registers with master automatically)
python -m slave.main --config packa.toml

# 3. Start the web dashboard
python -m web.main --config packa.toml
# Open http://localhost:8080 in a browser

# 4a. Queue a single file
curl -X POST http://localhost:9000/transfer \
     -H "Content-Type: application/json" \
     -d '{"file_path": "/mnt/data/shows/ep1.mkv"}'

# 4b. Or scan an entire directory
curl -X POST http://localhost:9000/scan/start

# 5. Poll scan progress
curl http://localhost:9000/scan/status

# 6. Check unclaimed jobs on master
curl http://localhost:9000/files?status=pending

# 7. Poll worker status on slave
curl http://192.168.1.10:8000/status

# 8. Check record on master (updated automatically when ffmpeg finishes)
curl http://localhost:9000/files/42
```
