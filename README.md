# Packa

> **Note:** This project is 100% AI-generated using [Claude](https://claude.ai) by Anthropic.

Distributed video conversion system. A master node accepts file paths via API or directory scan and distributes work to one or more slave nodes. Slaves pull jobs from the master, run ffmpeg, and report results back. A web frontend provides a browser dashboard.

Files are never transferred over the network — slaves access them directly via the filesystem. Only metadata travels over HTTP.

## Architecture

```
master/    accepts file paths, stores metadata, distributes jobs
slave/     polls master for jobs, runs ffmpeg, reports results
web/       browser dashboard — talks to master and slaves, serves plain HTTP to the browser
shared/    models, schemas, CRUD, config and TLS helpers (used by all three)
```

### Ports

| Service    | Default |
|------------|---------|
| Master API | 9000    |
| Slave API  | 8000    |
| Web UI     | 8080    |

### Pull model

Slaves poll master for work. When a slave's queue is empty it calls `POST /jobs/claim` to fetch one or more pending jobs. The master marks those records `assigned` and returns relative paths. The slave creates local records, applies its path prefix, and enqueues the jobs.

If master goes down, the slave continues processing whatever is already queued.

### Path prefix translation

```
Master:  /mnt/data/shows/ep1.mkv
         strip master prefix "/mnt/data/"  →  shows/ep1.mkv  (sent over API)
         prepend slave prefix "/mnt/files/"
Slave:   /mnt/files/shows/ep1.mkv
```

### Databases

Each node has its own SQLite database. The master assigns the record ID; the slave stores the record under the same ID.

| Node   | File      |
|--------|-----------|
| Master | master.db |
| Slave  | slave.db  |

---

## Docker

Pre-built image: `ghcr.io/planeturban/packa`

A single image covers all three roles. Set `PACKA_ROLE` to `master`, `slave`, or `web` (default: `master`).

```bash
docker compose up
```

The compose file pulls `ghcr.io/planeturban/packa`, mounts `./packa.toml` into each container, and sets the right environment variables per service. Adjust the volume paths for your setup before starting.

---

## Installation (without Docker)

Requires Python 3.11+. ffmpeg and ffprobe must be installed on slave nodes.

```bash
pip install -r requirements.txt

python -m master.master --config packa.toml
python -m slave.main   --config packa.toml
python -m web.main     --config packa.toml
```

---

## Configuration

All three processes share one config file. Copy the example and adjust:

```bash
cp packa.example.toml packa.toml
```

Settings are applied in this order — later wins:

```
config file  <  environment variable  <  CLI flag
```

### Master

```toml
[master]
bind     = "localhost"   # "any" for 0.0.0.0
api_port = 9000

[master.paths]
prefix = "/mnt/data/"   # stripped before sending paths to slaves; used as scan root

[master.scan]
extensions = [".mkv", ".mp4", ".avi", ".mov"]
# min_size = 0   # bytes — 0 = no limit
# max_size = 0
```

| Environment variable | Config key |
|----------------------|------------|
| `PACKA_MASTER_BIND` | `master.bind` |
| `PACKA_MASTER_API_PORT` | `master.api_port` |
| `PACKA_MASTER_PREFIX` | `master.paths.prefix` |
| `PACKA_MASTER_EXTENSIONS` | `master.scan.extensions` (comma-separated) |
| `PACKA_MASTER_TLS_CERT` | `master.tls.cert` |
| `PACKA_MASTER_TLS_KEY` | `master.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` |

### Slave

```toml
[slave]
bind        = "localhost"
api_port    = 8000
master_host = "localhost"
master_port = 9000
id          = "storage-01"   # unique ID; omit to auto-generate and persist a UUID

[slave.paths]
prefix = "/mnt/files/"   # prepended to paths from master; omit to reuse master prefix

[slave.ffmpeg]
bin        = "ffmpeg"
output_dir = "/mnt/output"
# extra_args = ""
# encoders = ["libx265", "nvenc"]   # restrict the dashboard dropdown

[slave.worker]
poll_interval = 5   # seconds between polls when queue is empty
```

| Environment variable | Config key |
|----------------------|------------|
| `PACKA_SLAVE_BIND` | `slave.bind` |
| `PACKA_SLAVE_API_PORT` | `slave.api_port` |
| `PACKA_SLAVE_ID` | `slave.id` |
| `PACKA_SLAVE_MASTER_HOST` | `slave.master_host` |
| `PACKA_SLAVE_MASTER_PORT` | `slave.master_port` |
| `PACKA_SLAVE_ADVERTISE_HOST` | `slave.advertise_host` |
| `PACKA_SLAVE_PREFIX` | `slave.paths.prefix` |
| `PACKA_SLAVE_FFMPEG_BIN` | `slave.ffmpeg.bin` |
| `PACKA_SLAVE_FFMPEG_OUTPUT_DIR` | `slave.ffmpeg.output_dir` |
| `PACKA_SLAVE_FFMPEG_EXTRA_ARGS` | `slave.ffmpeg.extra_args` |
| `PACKA_SLAVE_POLL_INTERVAL` | `slave.worker.poll_interval` |
| `PACKA_SLAVE_TLS_CERT` | `slave.tls.cert` |
| `PACKA_SLAVE_TLS_KEY` | `slave.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` |

#### Encoder presets

Encoders are fully config-driven. Define one `[slave.ffmpeg.encoder.<key>]` section per encoder — only the encoders you define appear in the dashboard dropdown.

| Field | Description |
|-------|-------------|
| `display_name` | Optional human-readable label; shown as `display_name (key)` in the dropdown |
| `video_args` | ffmpeg video codec arguments |

```toml
[slave.ffmpeg.encoder.libx265]
display_name = "Software"
video_args   = "-c:v libx265"

[slave.ffmpeg.encoder.nvenc]
display_name = "NVIDIA"
video_args   = "-c:v hevc_nvenc -preset p5 -cq 24"

[slave.ffmpeg.encoder.vaapi]
display_name = "Intel/AMD"
video_args   = "-init_hw_device vaapi=va:/dev/dri/renderD128 -filter_hw_device va -vf format=nv12,hwupload -c:v hevc_vaapi -rc_mode ICQ -global_quality 23"

[slave.ffmpeg.encoder.videotoolbox]
display_name = "Apple"
video_args   = "-c:v hevc_videotoolbox -q:v 65"
```

If no encoders are defined, a bare `libx265` preset is used as a fallback. The active encoder defaults to the first defined encoder and can be changed at runtime from the web dashboard; the choice is persisted in `slave.db`.

### Web

```toml
[web]
bind        = "localhost"
port        = 8080
master_host = "localhost"
master_port = 9000

username   = "admin"      # omit username or password to disable authentication
password   = "change-me"
secret_key = "long-random-string"   # auto-generated if omitted (sessions won't survive restarts)
```

| Environment variable | Config key |
|----------------------|------------|
| `PACKA_WEB_BIND` | `web.bind` |
| `PACKA_WEB_PORT` | `web.port` |
| `PACKA_WEB_MASTER_HOST` | `web.master_host` |
| `PACKA_WEB_MASTER_PORT` | `web.master_port` |
| `PACKA_WEB_USERNAME` | `web.username` |
| `PACKA_WEB_PASSWORD` | `web.password` |
| `PACKA_WEB_SECRET_KEY` | `web.secret_key` |
| `PACKA_WEB_TLS_CERT` | `web.tls.cert` |
| `PACKA_WEB_TLS_KEY` | `web.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` |

### mTLS (optional)

All three fields (ca, cert, key) must be set on a node to enable mTLS. If master has mTLS enabled, slaves without a valid client certificate are rejected.

```toml
[tls]
ca = "/etc/packa/ca.crt"

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

The web process acts as a BFF: it uses its own client certificate when talking to master and slaves, while the browser connects without a client certificate.

---

## Web dashboard

Served at port 8080. If `username` and `password` are both set, a login page is shown.

- File counts by status — clickable, opens a filtered file list with search and bulk actions
- Scan controls and periodic scan toggle
- Per-slave cards: status badge, queue depth, live ffmpeg progress (speed, FPS, ETA, sizes), encoder badge
- Slave detail modal: live progress, encoder selector, full file history with encoder filter

**Encoder badges** are colour-coded and appear on slave cards, in the detail modal, and in file lists. File tables can be filtered by encoder.

**Queue size:** controls how many jobs the slave claims from master per poll. When greater than 1, multiple files are pre-fetched and marked `assigned` on the master while they wait in the slave's queue. Configurable from the slave detail modal and persisted in `slave.db`.

**ffmpeg command:** while a conversion is running, clicking the active encoder badge in the slave modal reveals the exact ffmpeg command being used.

**Unconfigured state:** a slave with no prior configuration starts in an unconfigured state — it will not poll or process jobs until an encoder is selected from the dashboard.

**Controls per slave:** Pause, Resume, Finish current (drain — completes the active job then sleeps), Stop, Sleep, Wake.

The page auto-refreshes every 3 seconds. The slave modal polls at 500 ms during conversion and 2 s when idle. Dark mode follows the system preference with a manual override in the nav bar.

---

## File status

| Status | Description |
|--------|-------------|
| `pending` | Created, not yet claimed |
| `assigned` | Claimed by a slave, not yet processing |
| `processing` | ffmpeg is running |
| `complete` | Converted successfully; output is smaller than source |
| `discarded` | Already HEVC — no conversion needed |
| `cancelled` | Stopped by user (`cancel_reason = "user"`) or automatically because output exceeded source size (`cancel_reason = "auto"`) |
| `error` | ffmpeg exited with a non-zero code |

---

## ffmpeg

```
ffmpeg -i {file} -map 0 -c copy {video_args} [extra_args] -progress pipe:1 -nostats {output}
```

- `ffprobe` checks the video codec before starting. If the file is already HEVC, the record is immediately set to `discarded` and ffmpeg is never run.
- Audio, subtitles and attachments are always copied (`-map 0 -c copy`).
- Output size is checked every 5 seconds while ffmpeg runs. If the output grows larger than the source, ffmpeg is terminated and the record is `cancelled` (`cancel_reason = "auto"`).
- On restart, partial output files from interrupted jobs are deleted and those records are re-queued.

---

## API summary

### Master (port 9000)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/slaves` | Register a slave (called automatically on startup) |
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
| `POST` | `/scan/stop` | Cancel running scan |
| `GET` | `/scan/status` | Scan progress |
| `GET/POST` | `/scan/settings` | Periodic scan interval and enabled flag |

### Slave (port 8000)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Worker state, queue depth, live ffmpeg progress |
| `GET` | `/files` | List records, filterable by `?status=` |
| `GET` | `/files/{id}` | Get a single record |
| `DELETE` | `/files/{id}` | Delete record (stops ffmpeg if running) |
| `PATCH` | `/files/{id}/status` | Update record status |
| `POST` | `/conversion/stop` | Terminate ffmpeg (`cancel_reason = "user"`) |
| `POST` | `/conversion/pause` | Suspend ffmpeg (SIGSTOP) |
| `POST` | `/conversion/resume` | Resume paused ffmpeg |
| `POST` | `/conversion/drain` | Finish current job then sleep |
| `POST` | `/conversion/sleep` | Enter sleep mode |
| `POST` | `/conversion/wake` | Leave sleep mode |
| `GET` | `/settings` | Current encoder |
| `POST` | `/settings` | Change encoder `{"encoder": "nvenc"}` |
