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
PENDING → ASSIGNED → DISCARDED   (already HEVC — skipped before ffmpeg runs)
        → DUPLICATE               (same content exists at another path)
                   → PROCESSING → COMPLETE
                                → CANCELLED   (user stop, or output too large)
                                → ERROR
```

| Status | Description |
|--------|-------------|
| `pending` | Created, not yet claimed |
| `assigned` | Claimed by a worker, not yet processing |
| `processing` | ffmpeg is running |
| `complete` | Converted successfully; output is smaller than source |
| `discarded` | Already HEVC — no conversion needed |
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
- `ffprobe` checks the video codec before starting. If already HEVC the record is immediately set to `discarded`.
- Output size is monitored every 5 seconds. If the actual output grows larger than the source, ffmpeg is terminated and the record is set to `cancelled`.
- The projected output size (estimated from progress and current bitrate) is also checked per progress frame against a set of stepped thresholds (`cancel_thresholds`). Each threshold is a `[progress%, ratio]` pair. Once that progress percentage is reached, ffmpeg is terminated early if the projection exceeds `source_size × ratio`. The tightest (highest progress) reached threshold applies. An empty list disables the check.
- When `replace_original` is enabled (set per worker in the dashboard), the output file is moved back to the original source path on success. If the move fails the record is set to `error` and the output file remains in `output_dir`.
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

**Packa has no security between nodes and is intended for trusted networks only.**

- No authentication between master, workers and the web process — any host that can reach the master API can register as a worker, claim jobs, or manipulate records. The same applies to worker APIs.
- All inter-node communication is plain HTTP.
- Web authentication (username/password) is optional and protects only the browser-facing interface, not the underlying master or worker APIs.
- Inter-node authentication is not yet implemented and is planned for a future release.

Run Packa on an isolated network or behind a firewall. Do not expose master or worker ports to untrusted networks.

---

## Web dashboard

The browser talks to the web process only. The web process acts as a backend-for-frontend (BFF), fanning out requests to the master and all registered workers in parallel.

The dashboard auto-refreshes every 3 seconds. It has six tabs:

| Tab | Contents |
|-----|----------|
| **Overview** | 8 clickable status chips (Pending, Assigned, Processing, Complete, Discarded, Cancelled, Error, Duplicate), overall progress bar, worker summary. Each chip opens a modal listing files with that status, with bulk actions. |
| **Files** | Full file table with status filter chips, search by filename or worker name, checkboxes and bulk actions (Set → Pending, Set → Cancelled, Delete, Queue to worker). |
| **Statistics** | Aggregated and per-worker conversion stats: jobs, input/output size, space saved, compression ratio, avg duration, throughput over time. |
| **Workers** | Per-worker cards with live ffmpeg progress (%, FPS, speed, bitrate, size), encoder selector, batch size, pause/drain/stop/sleep controls. |
| **Scan** | Manual scan trigger and periodic scan toggle with interval setting. |
| **Settings** | Poll interval and other dashboard preferences. |

Fonts (IBM Plex Sans and IBM Plex Mono) are served locally from `/static/fonts/` — no external network requests are made by the UI.
