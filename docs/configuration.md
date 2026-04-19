# Configuration

All three processes share one config file (`packa.toml`). Copy the example to get started:

```bash
cp packa.example.toml packa.toml
```

Settings are applied in this order — later wins:

```
config file  <  environment variable  <  CLI flag
```

---

## Master

```toml
[master]
bind     = "localhost"   # use "any" for 0.0.0.0
api_port = 9000

[master.paths]
prefix = "/mnt/data/"   # stripped before sending paths to slaves; used as scan root

[master.scan]
extensions = [".mkv", ".mp4", ".avi", ".mov"]
# min_size = 0   # MB — 0 = no limit
# max_size = 0
```

| Environment variable | Config key |
|----------------------|------------|
| `PACKA_MASTER_BIND` | `master.bind` |
| `PACKA_MASTER_API_PORT` | `master.api_port` |
| `PACKA_MASTER_PREFIX` | `master.paths.prefix` |
| `PACKA_MASTER_EXTENSIONS` | `master.scan.extensions` (comma-separated) |
| `PACKA_MASTER_MIN_SIZE` | `master.scan.min_size` (MB) |
| `PACKA_MASTER_MAX_SIZE` | `master.scan.max_size` (MB) |
| `PACKA_MASTER_CHECKSUM_BYTES` | `master.scan.checksum_bytes` |

---

## Slave

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

### Encoder presets

Each `[slave.ffmpeg.encoder.<key>]` section defines one encoder. Only the encoders you define appear in the dashboard dropdown. If none are defined, a bare `libx265` preset is used as a fallback.

| Field | Description |
|-------|-------------|
| `display_name` | Optional human-readable label shown in the dropdown |
| `video_args` | ffmpeg video codec arguments |

The active encoder defaults to the first defined encoder and can be changed at runtime from the dashboard; the choice is persisted in `slave.db`.

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

[slave.ffmpeg.encoder.rkmpp]
display_name = "Rockchip"
video_args   = "-c:v hevc_rkmpp -rc_mode CQP -qp_init 28"
```

---

## Web

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
