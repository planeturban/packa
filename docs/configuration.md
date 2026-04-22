# Configuration

All three processes share one config file (`packa.toml`). Copy the example to get started:

```bash
cp packa.example.toml packa.toml
```

Settings are applied in this order — later wins:

```
default  <  config file  <  environment variable  <  database  <  CLI flag
```

Worker and web processes use the three-layer form (`config file < env < CLI`). Master adds a **database layer** backed by its `master_settings` table — values edited from the dashboard live here and override file and env but never the CLI.

---

## Master

The master can start with no config file at all — every setting has a built-in default. The dashboard's **Master** tab exposes every key as an editable form, writes edits to the database, and shows which layer each value currently comes from. See [UI reference — Master tab](ui.md#master-tab) for the editor.

```toml
[master]
bind     = "localhost"   # use "any" for 0.0.0.0
api_port = 9000

[master.paths]
prefix = "/mnt/data/"   # stripped before sending paths to workers; used as scan root (empty disables the scanner)

[master.scan]
extensions = [".mkv", ".mp4", ".avi", ".mov"]
# min_size = 0                # MB — 0 = no limit
# max_size = 0
# checksum_bytes = 4194304    # bytes read from middle of file for duplicate detection (default 4 MB)
# probe_batch_size = 20       # files probed concurrently per tick
# probe_interval = 60         # seconds to sleep when the probe queue is empty

# [master.scan.periodic]
# enabled  = false            # periodic re-scan of the path prefix
# interval = 60               # seconds between periodic scans (min 10)

# [master.tls]                # TLS is auto-configured on first start
# disabled = true             # opt out entirely
# cert = "/etc/packa/master.crt"   # BYO cert (overrides auto-generated)
# key  = "/etc/packa/master.key"
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
| `PACKA_MASTER_PROBE_BATCH_SIZE` | `master.scan.probe_batch_size` |
| `PACKA_MASTER_PROBE_INTERVAL` | `master.scan.probe_interval` |
| `PACKA_MASTER_SCAN_PERIODIC_ENABLED` | `master.scan.periodic.enabled` |
| `PACKA_MASTER_SCAN_INTERVAL` | `master.scan.periodic.interval` (seconds) |
| `PACKA_MASTER_TLS_DISABLED` | `master.tls.disabled` |
| `PACKA_MASTER_TLS_CERT` | `master.tls.cert` |
| `PACKA_MASTER_TLS_KEY` | `master.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` (shared CA for BYO-cert setups) |

### Database layer and runtime edits

On first start the master seeds `master_settings` with the effective file + env + default values. From then on the database row wins over file and env; edits from the dashboard are persisted immediately.

- **Save** — writes the new value to the database. For `bind` and `api_port` the change takes effect on the next restart; everything else is picked up live.
- **Restore from file / env / default** — copies that layer's value into the database. Use this when you want to pin a known-working value against future edits.
- **Revert** — deletes the database override so the value falls back through env → file → default.
- **CLI flags** (`--bind`, `--api-port`) are never persisted. While a flag is active the database row is still editable but only takes effect after the process is restarted without the flag; the editor shows a notice in that case.

---

## Worker

```toml
[worker]
bind             = "localhost"
api_port         = 8000
master_host      = "localhost"
master_port      = 9000
id               = "storage-01"   # unique ID; omit to auto-generate and persist a UUID
# bootstrap_token = ""            # copy from master log on first run; stored after bootstrap

[worker.paths]
prefix = "/mnt/files/"   # prepended to paths from master; omit to reuse master prefix

[worker.ffmpeg]
bin        = "ffmpeg"
output_dir = "/mnt/output"
# extra_args = ""

[worker.worker]
poll_interval     = 5   # seconds between polls when queue is empty
cancel_thresholds = [[10.0, 1.10], [25.0, 1.05], [50.0, 1.0]]

# [worker.tls]                     # BYO cert (overrides bootstrapped certs)
# cert = "/etc/packa/worker.crt"
# key  = "/etc/packa/worker.key"
```

`cancel_thresholds` is a list of `[progress%, ratio]` pairs. Once the given progress percentage is reached, ffmpeg is terminated early if the projected output size exceeds `source_size × ratio`. The tightest (highest progress) reached threshold applies. Set to `[]` to disable. As an environment variable: `PACKA_WORKER_CANCEL_THRESHOLDS=10.0:1.10,25.0:1.05,50.0:1.0`.

| Environment variable | Config key |
|----------------------|------------|
| `PACKA_WORKER_BIND` | `worker.bind` |
| `PACKA_WORKER_API_PORT` | `worker.api_port` |
| `PACKA_WORKER_ID` | `worker.id` |
| `PACKA_WORKER_MASTER_HOST` | `worker.master_host` |
| `PACKA_WORKER_MASTER_PORT` | `worker.master_port` |
| `PACKA_WORKER_ADVERTISE_HOST` | `worker.advertise_host` |
| `PACKA_WORKER_PREFIX` | `worker.paths.prefix` |
| `PACKA_WORKER_FFMPEG_BIN` | `worker.ffmpeg.bin` |
| `PACKA_WORKER_FFMPEG_OUTPUT_DIR` | `worker.ffmpeg.output_dir` |
| `PACKA_WORKER_FFMPEG_EXTRA_ARGS` | `worker.ffmpeg.extra_args` |
| `PACKA_WORKER_POLL_INTERVAL` | `worker.worker.poll_interval` |
| `PACKA_WORKER_CANCEL_THRESHOLDS` | `worker.worker.cancel_thresholds` (format: `"10.0:1.10,25.0:1.05"`) |
| `PACKA_WORKER_BOOTSTRAP_TOKEN` | `worker.bootstrap_token` |
| `PACKA_WORKER_TLS_CERT` | `worker.tls.cert` |
| `PACKA_WORKER_TLS_KEY` | `worker.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` (shared CA for BYO-cert setups) |

### Encoder presets

Each `[worker.ffmpeg.encoder.<key>]` section defines one encoder. Only the encoders you define appear in the dashboard dropdown. If none are defined, a bare `libx265` preset is used as a fallback.

| Field | Description |
|-------|-------------|
| `display_name` | Optional human-readable label shown in the dropdown |
| `video_args` | ffmpeg video codec arguments, placed after `-i` |
| `input_args` | Optional ffmpeg input options placed **before** `-i` (e.g. `-hwaccel vaapi`) |

The active encoder defaults to the first defined encoder and can be changed at runtime from the dashboard; the choice is persisted in `worker.db`. Adding, removing, or modifying encoder presets requires editing `packa.toml` and restarting the worker.

The **Replace original** flag (also in the worker modal) moves the converted file back to the source path on success. If the move fails, the record is set to `error`. This setting is persisted in `worker.db` and is off by default.

```toml
[worker.ffmpeg.encoder.libx265]
display_name = "Software"
video_args   = "-c:v libx265"

[worker.ffmpeg.encoder.nvenc]
display_name = "NVIDIA"
video_args   = "-c:v hevc_nvenc -preset p5 -cq 24"

[worker.ffmpeg.encoder.vaapi]
display_name = "Intel/AMD"
video_args   = "-init_hw_device vaapi=va:/dev/dri/renderD128 -filter_hw_device va -vf format=nv12,hwupload -c:v hevc_vaapi -rc_mode ICQ -global_quality 23"

[worker.ffmpeg.encoder.videotoolbox]
display_name = "Apple"
video_args   = "-c:v hevc_videotoolbox -q:v 65"

[worker.ffmpeg.encoder.rkmpp]
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
# bootstrap_token = ""    # copy from master log on first run; stored after bootstrap

# [web.tls]               # BYO cert (overrides bootstrapped certs)
# cert = "/etc/packa/web.crt"
# key  = "/etc/packa/web.key"
```

`secret_key` is auto-generated and persisted in `web.db` — no need to set it manually.

| Environment variable | Config key |
|----------------------|------------|
| `PACKA_WEB_BIND` | `web.bind` |
| `PACKA_WEB_PORT` | `web.port` |
| `PACKA_WEB_MASTER_HOST` | `web.master_host` |
| `PACKA_WEB_MASTER_PORT` | `web.master_port` |
| `PACKA_WEB_USERNAME` | `web.username` |
| `PACKA_WEB_PASSWORD` | `web.password` |
| `PACKA_WEB_SECRET_KEY` | `web.secret_key` |
| `PACKA_WEB_BOOTSTRAP_TOKEN` | `web.bootstrap_token` |
| `PACKA_WEB_TLS_CERT` | `web.tls.cert` |
| `PACKA_WEB_TLS_KEY` | `web.tls.key` |
| `PACKA_TLS_CA` | `tls.ca` (shared CA for BYO-cert setups) |
