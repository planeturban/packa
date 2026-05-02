# Architecture

## Overview

```
master/    accepts file paths, stores metadata, distributes jobs
worker/     polls master for jobs, runs ffmpeg, reports results
web/       browser dashboard (BFF) — talks to master and workers
shared/    models, schemas, CRUD, config helpers, DB helpers (used by all three)
```

### Default ports

| Service | Port |
|---------|------|
| Master API | 9000 |
| Worker API | 8000 |
| Web UI | 8080 |

---

## Pull model

Workers poll master for work. When a worker's queue is empty it calls `POST /jobs/claim` to fetch one or more pending jobs. The master marks those records `assigned` and returns relative file paths. The worker creates local records, applies its path prefix, and enqueues the jobs.

If the master goes down, the worker continues processing whatever is already in its queue.

---

## Path prefix translation

Master and worker nodes may mount the same files at different paths. The master strips its own prefix before sending paths to workers; the worker prepends its own prefix before accessing files.

```
Master sees:  /mnt/data/shows/ep1.mkv
              strip "/mnt/data/"  →  shows/ep1.mkv  (sent over API)
              prepend "/mnt/files/"
Worker sees:   /mnt/files/shows/ep1.mkv
```

---

## Databases

Each node has its own SQLite database with an identical schema. The master assigns the record ID; the worker stores the record under the same ID so both databases share the same IDs for the same file.

| Node | File |
|------|------|
| Master | `master.db` |
| Worker | `worker.db` |

Both master and worker use `NullPool` for their SQLite connections — each request gets a fresh connection with no pooling, which avoids exhaustion under concurrent async polling.

---

## File status lifecycle

```
SCANNING → PENDING → ASSIGNED → DISCARDED   (already HEVC — detected by master probe loop)
         → DUPLICATE            (same content exists at another path)
                             → PROCESSING → COMPLETE
                                          → CANCELLED   (user stop, or output too large)
                                          → ERROR
```

| Status | Description |
|--------|-------------|
| `scanning` | Discovered by scan or `/transfer`; awaiting ffprobe analysis by master |
| `pending` | Probed and ready — codec, resolution, bitrate and duration are known; not yet claimed by a worker |
| `assigned` | Claimed by a worker, not yet processing |
| `processing` | ffmpeg is running |
| `complete` | Converted successfully; output is smaller than source |
| `discarded` | Already HEVC — detected by master probe loop before the file is ever sent to a worker |
| `duplicate` | Same content (by checksum) already exists at another path |
| `cancelled` | Stopped by user (`cancel_reason = "user"`) or because output exceeded the size limit (`cancel_reason = "auto"`) |
| `error` | ffmpeg exited with a non-zero code, or the converted file could not be moved back to the original path |

---

## ffmpeg

```
ffmpeg [input_args] -i {file} -map 0 -c copy {video_args} [extra_args] -progress pipe:1 -nostats {output}
```

`input_args` is only present when the encoder preset defines it — used for hardware decode options that must precede `-i` (e.g. `-hwaccel vaapi`).

- All streams (audio, subtitles, attachments) are copied; only the video stream is re-encoded.
- The worker does not run ffprobe. The master probe loop analyses every `scanning` record (codec, resolution, bitrate, duration) and either promotes it to `pending` or sets it to `discarded` (already HEVC). Only `pending` records with a known duration are sent to workers.
- Output size is monitored every 5 seconds. If the actual output grows larger than the source, ffmpeg is terminated and the record is set to `cancelled`.
- The projected output size (estimated from progress and current bitrate) is also checked per progress frame against a set of stepped thresholds (`cancel_thresholds`). Each threshold is a `[progress%, ratio]` pair. Once that progress percentage is reached, ffmpeg is terminated early if the projection exceeds `source_size × ratio`. The tightest (highest progress) reached threshold applies. An empty list disables the check.
- When `replace_original` is enabled (set per worker in the dashboard), the output is verified with ffprobe before being moved back to the source path. If the output has no readable video or zero duration it is deleted and the record is set to `error` — the source is never overwritten with a corrupt file. If the move itself fails the record is set to `error` and the output remains in `output_dir`.
- A stall watchdog monitors ffmpeg progress. If no progress frame arrives within `stall_timeout` seconds (default 120, 0 = disabled), ffmpeg is killed and the record is set to `error`. This handles both "never started" and "froze mid-encode" cases.
- On restart, any partial output files from interrupted jobs are deleted and those records are re-queued as `pending`.

## Duplicate detection

When a file is added (via `/transfer` or directory scan), a content-based checksum is computed: SHA-256 of the file size concatenated with `checksum_bytes` bytes read from the middle of the file. If an existing record with the same checksum is found, the new record is marked `duplicate` and its `duplicate_of_id` points to the original. The duplicate is never sent to a worker for conversion.

---

## Worker ID

A worker's ID is resolved in this order:

1. `worker.id` in config / `PACKA_WORKER_ID` env / `--id` CLI flag
2. Previously persisted ID in `worker.db`
3. Auto-generated UUID4, stored in `worker.db` for subsequent restarts

---

## Security

**mTLS is strongly recommended for all inter-node communication.**

### Bootstrap

- On first start master auto-generates a CA and server cert (stored in `master.db`). A bootstrap token (valid 10 minutes) is generated and stored; retrieve it with `packa bootstrap-token --config packa.toml`. The token is **not** printed to the log.
- Workers and the web process exchange this token for a signed client cert via `POST /bootstrap`. Before doing so they fetch the master's CA fingerprint from `GET /tls/status` and abort if the fingerprint does not match the `bootstrap_ca_fingerprint` value in config. This prevents TOFU being silently bypassed. All subsequent connections verify against the CA.
- Bootstrapped certs are persisted in `worker.db` and `web.db` and loaded automatically on restart.
- BYO certs are supported — set `cert`/`key` in the relevant `[*.tls]` section; those override any bootstrapped certs.

### Server behaviour

- Master runs with `CERT_OPTIONAL` so `/bootstrap` stays reachable before a node has a cert. Workers run with `CERT_REQUIRED` — once bootstrapped they only accept connections from CA-signed clients.
- Sensitive master endpoints (`/tls/token`, `/restart`) require either a loopback origin or a verified CA-signed client certificate. A TLS connection without a client cert is not sufficient.
- All issued certificates carry explicit **KeyUsage** (digitalSignature, keyEncipherment) and **ExtendedKeyUsage** (serverAuth, clientAuth, or both) extensions. Client and server certs are purpose-restricted.
- TLS temp files (written to satisfy uvicorn's file-path API) use `mkstemp` with unpredictable names and are cleaned up at process exit.

### Web — browser-facing HTTPS

The web process enforces HTTPS on non-loopback addresses:

- **Option A — direct TLS:** set `[web.browser_tls]` cert + key; web terminates HTTPS itself.
- **Option B — behind proxy:** set `behind_proxy = true`; web listens HTTP but sets `Secure` + `SameSite=Lax` on session cookies.
- Without either option, web refuses to bind to a non-loopback address. Pass `--insecure-no-https` to override for local dev only.

Note: `[web.browser_tls]` is the **browser-facing** certificate. It is separate from `[web.tls]`, which holds the mTLS client cert used for outbound connections to master and workers.

### Access controls

- **Worker** refuses to bind to a non-loopback address when TLS is not yet enabled. Use `--insecure-no-tls` to override (dev/testing only).
- **Web** refuses to bind to a non-loopback address without `username` and `password` configured and without HTTPS enabled. Use `--insecure-no-auth` / `--insecure-no-https` to override (dev/testing only).
- Web authentication (username/password) protects the browser-facing interface. `secret_key` is auto-generated and persisted in `web.db`.
- The web BFF validates that every worker host/port it proxies to is a registered worker. Arbitrary host/port injection via BFF action endpoints is rejected.
- All outbound TLS connections from web and worker use `check_hostname=True` — the server's certificate must match the hostname or IP address the connection is made to.
- Master and worker APIs have no per-request application-layer authentication beyond mTLS — do not expose them to untrusted networks.

---

## Web dashboard

The browser talks to the web process only. The web process acts as a backend-for-frontend (BFF), fanning out requests to the master and all registered workers in parallel.

See [UI reference](ui.md) for a full description of the dashboard tabs, file filtering, worker cards, and keyboard/mouse interactions.
