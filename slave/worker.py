"""
FFmpeg worker with an asyncio queue.

Records are enqueued by the API and processed one at a time by worker_loop().
If the slave is busy when a record arrives it is stored in the DB as PENDING
and will be picked up when the current job finishes.

All streams (video, audio, subtitles, attachments, etc.) are copied without
re-encoding via -map 0 -c copy.

After conversion:
  - Output smaller than source → COMPLETE, data written to DB, master notified
  - Output same size or larger → output file deleted → DISCARDED
  - ffmpeg non-zero exit        → ERROR

Progress is read from ffmpeg's -progress pipe:1 output and stored in
worker_state.progress for the /status endpoint to serve.
"""

import asyncio
import shlex
from datetime import datetime, timezone
from pathlib import Path

import httpx

from shared.crud import get_file_record, update_conversion_result, update_status
from shared.models import FileRecord, FileStatus

from .database import SessionLocal
from .state import FfmpegProgress, Job, worker_state


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ffprobe_bin(ffmpeg_bin: str) -> str:
    """Derive ffprobe path from ffmpeg path."""
    p = Path(ffmpeg_bin)
    return str(p.parent / "ffprobe") if p.parent.name else "ffprobe"


def _build_cmd(ffmpeg_bin: str, file_path: str, output_path: str, extra_args: str) -> list[str]:
    cmd = [ffmpeg_bin, "-i", file_path, "-map", "0", "-c", "copy"]
    if extra_args:
        cmd.extend(shlex.split(extra_args))
    cmd += ["-progress", "pipe:1", "-nostats", output_path]
    return cmd


async def _get_duration(ffprobe: str, file_path: str) -> float | None:
    """Return file duration in seconds using ffprobe, or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return float(stdout.decode().strip())
    except Exception:
        return None


def _parse_progress(frame: dict[str, str], duration_s: float | None) -> FfmpegProgress:
    p = FfmpegProgress()

    # Current output position
    out_time_us = int(frame.get("out_time_us") or 0)
    out_time_s = out_time_us / 1_000_000
    p.out_time = (frame.get("out_time") or "").strip() or None

    # Speed  (e.g. "1.50x" → 1.5)
    speed_raw = (frame.get("speed") or "").replace("x", "").strip()
    try:
        p.speed = float(speed_raw) if speed_raw and speed_raw != "N/A" else None
    except ValueError:
        pass

    # FPS
    try:
        p.fps = float(frame.get("fps") or 0) or None
    except ValueError:
        pass

    # Bitrate (keep as string, e.g. "5000.0kbits/s")
    p.bitrate = (frame.get("bitrate") or "").strip() or None

    # Current output file size
    try:
        p.current_size_bytes = int(frame.get("total_size") or 0) or None
    except ValueError:
        pass

    # Derived fields that need duration
    if duration_s and duration_s > 0 and out_time_s > 0:
        ratio = out_time_s / duration_s
        p.percent = round(min(ratio * 100, 100.0), 1)

        remaining_s = duration_s - out_time_s
        if p.speed and p.speed > 0:
            p.eta_seconds = max(0, round(remaining_s / p.speed))

        if p.current_size_bytes and ratio > 0:
            p.projected_size_bytes = int(p.current_size_bytes / ratio)

    return p


async def _stream_progress(stdout: asyncio.StreamReader, duration_s: float | None) -> None:
    """Read ffmpeg -progress output line by line and update worker_state.progress."""
    frame: dict[str, str] = {}
    async for raw in stdout:
        line = raw.decode(errors="replace").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        frame[key.strip()] = value.strip()
        if key.strip() == "progress":
            worker_state.progress = _parse_progress(frame, duration_s)
            frame = {}


async def _collect_stderr(stderr: asyncio.StreamReader) -> str:
    chunks: list[str] = []
    async for line in stderr:
        chunks.append(line.decode(errors="replace"))
    return "".join(chunks)


async def _notify_master(record_id: int) -> None:
    if not worker_state.master_url or worker_state.slave_id is None:
        return
    url = f"{worker_state.master_url}/files/{record_id}/sync"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json={"slave_id": worker_state.slave_id})
            response.raise_for_status()
        print(f"[worker] master notified for record {record_id}")
    except Exception as exc:
        print(f"[worker] failed to notify master for record {record_id}: {exc}")


async def _process(job: Job, ffmpeg_bin: str, output_dir: str, extra_args: str) -> None:
    output_path = str(Path(output_dir) / Path(job.file_path).name)
    db = SessionLocal()
    try:
        ffprobe = _ffprobe_bin(ffmpeg_bin)
        duration_s = await _get_duration(ffprobe, job.file_path)

        cmd = _build_cmd(ffmpeg_bin, job.file_path, output_path, extra_args)
        print(f"[worker] record {job.record_id} → {' '.join(cmd)}")

        started_at = _utcnow()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        record = get_file_record(db, job.record_id)
        if record:
            record.pid = proc.pid
            record.status = FileStatus.PROCESSING
            record.started_at = started_at
            db.commit()
        print(f"[worker] record {job.record_id} pid={proc.pid}  duration={duration_s}s")

        # Read stdout (progress) and stderr (errors) concurrently.
        stderr_text = await asyncio.gather(
            _stream_progress(proc.stdout, duration_s),
            _collect_stderr(proc.stderr),
        )
        stderr_output: str = stderr_text[1]
        await proc.wait()
        finished_at = _utcnow()

        if proc.returncode != 0:
            update_conversion_result(
                db, job.record_id,
                status=FileStatus.ERROR,
                pid=proc.pid,
                output_size=None,
                started_at=started_at,
                finished_at=finished_at,
            )
            print(f"[worker] record {job.record_id} error (exit {proc.returncode}):")
            for line in stderr_output.splitlines():
                print(f"[ffmpeg]   {line}")
            return

        source_size = Path(job.file_path).stat().st_size
        output_size = Path(output_path).stat().st_size

        if output_size >= source_size:
            Path(output_path).unlink()
            update_conversion_result(
                db, job.record_id,
                status=FileStatus.DISCARDED,
                pid=proc.pid,
                output_size=output_size,
                started_at=started_at,
                finished_at=finished_at,
            )
            print(
                f"[worker] record {job.record_id} discarded — "
                f"output ({output_size} B) >= source ({source_size} B)"
            )
        else:
            update_conversion_result(
                db, job.record_id,
                status=FileStatus.COMPLETE,
                pid=proc.pid,
                output_size=output_size,
                started_at=started_at,
                finished_at=finished_at,
            )
            print(
                f"[worker] record {job.record_id} complete — "
                f"saved {source_size - output_size} B "
                f"({100 * (source_size - output_size) // source_size}%)"
            )
            await _notify_master(job.record_id)

    except Exception as exc:
        print(f"[worker] record {job.record_id} exception: {exc}")
        try:
            update_status(db, job.record_id, FileStatus.ERROR)
        except Exception:
            pass
    finally:
        db.close()


def recover(output_dir: str) -> None:
    """Called at startup. Resets interrupted jobs and re-queues all pending records."""
    db = SessionLocal()
    try:
        interrupted = (
            db.query(FileRecord)
            .filter(FileRecord.status == FileStatus.PROCESSING)
            .all()
        )
        for record in interrupted:
            output_path = Path(output_dir) / Path(record.file_path).name
            if output_path.exists():
                output_path.unlink()
                print(f"[worker] removed partial file: {output_path}")
            record.status = FileStatus.PENDING
            record.pid = None
        if interrupted:
            db.commit()
            print(f"[worker] reset {len(interrupted)} interrupted record(s) to pending")

        pending = (
            db.query(FileRecord)
            .filter(FileRecord.status == FileStatus.PENDING)
            .order_by(FileRecord.id)
            .all()
        )
        for record in pending:
            worker_state.enqueue(Job(record_id=record.id, file_path=record.file_path))

        print(f"[worker] recovery complete — {len(pending)} record(s) queued")
    finally:
        db.close()


async def worker_loop(ffmpeg_bin: str, output_dir: str, extra_args: str) -> None:
    print("[worker] loop started")
    while True:
        job = await worker_state.queue.get()
        worker_state.start(job.record_id)
        try:
            await _process(job, ffmpeg_bin, output_dir, extra_args)
        finally:
            worker_state.stop()
            worker_state.queue.task_done()
