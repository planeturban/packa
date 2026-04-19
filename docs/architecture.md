# Architecture

## Overview

```
master/    accepts file paths, stores metadata, distributes jobs
slave/     polls master for jobs, runs ffmpeg, reports results
web/       browser dashboard (BFF) — talks to master and slaves
shared/    models, schemas, CRUD, config helpers (used by all three)
```

### Default ports

| Service | Port |
|---------|------|
| Master API | 9000 |
| Slave API | 8000 |
| Web UI | 8080 |

---

## Pull model

Slaves poll master for work. When a slave's queue is empty it calls `POST /jobs/claim` to fetch one or more pending jobs. The master marks those records `assigned` and returns relative file paths. The slave creates local records, applies its path prefix, and enqueues the jobs.

If the master goes down, the slave continues processing whatever is already in its queue.

---

## Path prefix translation

Master and slave nodes may mount the same files at different paths. The master strips its own prefix before sending paths to slaves; the slave prepends its own prefix before accessing files.

```
Master sees:  /mnt/data/shows/ep1.mkv
              strip "/mnt/data/"  →  shows/ep1.mkv  (sent over API)
              prepend "/mnt/files/"
Slave sees:   /mnt/files/shows/ep1.mkv
```

---

## Databases

Each node has its own SQLite database with an identical schema. The master assigns the record ID; the slave stores the record under the same ID so both databases share the same IDs for the same file.

| Node | File |
|------|------|
| Master | `master.db` |
| Slave | `slave.db` |

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
| `assigned` | Claimed by a slave, not yet processing |
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
- When `replace_original` is enabled (set per slave in the dashboard), the output file is moved back to the original source path on success. If the move fails the record is set to `error` and the output file remains in `output_dir`.
- On restart, any partial output files from interrupted jobs are deleted and those records are re-queued as `pending`.

## Duplicate detection

When a file is added (via `/transfer` or directory scan), a content-based checksum is computed: SHA-256 of the file size concatenated with `checksum_bytes` bytes read from the middle of the file. If an existing record with the same checksum is found, the new record is marked `duplicate` and its `duplicate_of_id` points to the original. The duplicate is never sent to a slave for conversion. The dashboard shows duplicates as a separate count badge; clicking it opens a modal listing each duplicate path alongside the original path (prefix stripped).

---

## Slave ID

A slave's ID is resolved in this order:

1. `slave.id` in config / `PACKA_SLAVE_ID` env / `--id` CLI flag
2. Previously persisted ID in `slave.db`
3. Auto-generated UUID4, stored in `slave.db` for subsequent restarts

---

## Security

**Packa has no security between nodes and is intended for trusted networks only.**

- No authentication between master, slaves and the web process — any host that can reach the master API can register as a slave, claim jobs, or manipulate records. The same applies to slave APIs.
- All inter-node communication is plain HTTP.
- Web authentication (username/password) is optional and protects only the browser-facing interface, not the underlying master or slave APIs.
- Inter-node authentication is not yet implemented and is planned for a future release.

Run Packa on an isolated network or behind a firewall. Do not expose master or slave ports to untrusted networks.

---

## Web dashboard

The browser talks to the web process only. The web process acts as a backend-for-frontend (BFF), fanning out requests to the master and all registered slaves in parallel.

The dashboard auto-refreshes every 3 seconds. The slave detail modal polls at 500 ms during active conversion and 2 s when idle. Statistics refresh every 30 seconds.
