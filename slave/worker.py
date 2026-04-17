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
from shared.tls import httpx_kwargs
from shared.models import FileRecord, FileStatus

from .database import SessionLocal
from .state import FfmpegProgress, Job, worker_state


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ffprobe_bin(ffmpeg_bin: str) -> str:
    """Derive ffprobe path from ffmpeg path."""
    p = Path(ffmpeg_bin)
    return str(p.parent / "ffprobe") if p.parent.name else "ffprobe"


_VALID_ENCODERS = {"libx265", "nvenc", "vaapi", "videotoolbox"}


def _build_cmd(
    ffmpeg_bin: str,
    file_path: str,
    output_path: str,
    extra_args: str,
    encoder: str,
    presets: dict,
) -> list[str]:
    preset = presets.get(encoder)
    pre_input = shlex.split(preset.pre_input) if preset and preset.pre_input.strip() else []
    video_args = (
        shlex.split(preset.video_args)
        if preset and preset.video_args.strip()
        else ["-c:v", "libx265"]
    )

    cmd = [ffmpeg_bin] + pre_input + ["-i", file_path, "-map", "0", "-c", "copy"] + video_args
    if extra_args:
        cmd.extend(shlex.split(extra_args))
    cmd += ["-y", "-progress", "pipe:1", "-nostats", output_path]
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


async def _get_video_codec(ffprobe: str, file_path: str) -> str | None:
    """Return the codec name of the first video stream, or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() or None
    except Exception:
        return None


def _safe_int(val: str | None) -> int:
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0


def _safe_float(val: str | None) -> float:
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0


def _parse_progress(frame: dict[str, str], duration_s: float | None) -> FfmpegProgress:
    p = FfmpegProgress()

    # Current output position
    out_time_us = _safe_int(frame.get("out_time_us"))
    out_time_s = out_time_us / 1_000_000
    p.out_time = (frame.get("out_time") or "").strip() or None

    # Speed (e.g. "1.50x" → 1.5)
    speed_raw = (frame.get("speed") or "").replace("x", "").strip()
    speed = _safe_float(speed_raw) if speed_raw and speed_raw != "N/A" else 0.0
    p.speed = speed or None

    # FPS
    fps = _safe_float(frame.get("fps"))
    p.fps = fps or None

    # Bitrate (keep as string, e.g. "5000.0kbits/s")
    bitrate = (frame.get("bitrate") or "").strip()
    p.bitrate = bitrate if bitrate and bitrate != "N/A" else None

    # Current output file size
    size = _safe_int(frame.get("total_size"))
    p.current_size_bytes = size or None

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


async def _update_master_status(record_id: int, status: str) -> None:
    if not worker_state.master_url:
        return
    url = f"{worker_state.master_url}/files/{record_id}/status"
    try:
        async with httpx.AsyncClient(timeout=5, **httpx_kwargs(worker_state.tls)) as client:
            await client.patch(url, json={"status": status})
    except Exception as exc:
        print(f"[worker] failed to update master status for record {record_id}: {exc}")


async def _report_result_to_master(
    record_id: int,
    status: FileStatus,
    pid: int | None = None,
    output_size: int | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    cancel_reason: str | None = None,
) -> None:
    """Push final conversion result directly to master — no callback needed."""
    if not worker_state.master_url:
        return
    url = f"{worker_state.master_url}/files/{record_id}/result"
    body: dict = {"status": status.value}
    if pid is not None:
        body["pid"] = pid
    if output_size is not None:
        body["output_size"] = output_size
    if started_at is not None:
        body["started_at"] = started_at.isoformat()
    if finished_at is not None:
        body["finished_at"] = finished_at.isoformat()
    if cancel_reason is not None:
        body["cancel_reason"] = cancel_reason
    try:
        async with httpx.AsyncClient(timeout=10, **httpx_kwargs(worker_state.tls)) as client:
            response = await client.patch(url, json=body)
            response.raise_for_status()
        print(f"[worker] master updated record {record_id} → {status.value}")
    except Exception as exc:
        print(f"[worker] failed to update master for record {record_id}: {exc}")


async def _monitor_output_size(output_path: str, source_size: int, proc: asyncio.subprocess.Process) -> None:
    """Terminate ffmpeg if the output file grows larger than the source."""
    while proc.returncode is None:
        await asyncio.sleep(5)
        try:
            if Path(output_path).stat().st_size >= source_size:
                print(f"[worker] output already larger than source ({source_size} B) — terminating")
                worker_state.cancel_reason = "auto"
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
                break
        except OSError:
            pass


async def _process(job: Job, ffmpeg_bin: str, output_dir: str, extra_args: str) -> None:
    output_path = str(Path(output_dir) / Path(job.file_path).name)
    db = SessionLocal()
    try:
        source_size = Path(job.file_path).stat().st_size

        ffprobe = _ffprobe_bin(ffmpeg_bin)
        duration_s, video_codec = await asyncio.gather(
            _get_duration(ffprobe, job.file_path),
            _get_video_codec(ffprobe, job.file_path),
        )
        already_hevc = (video_codec or "").lower() == "hevc"
        print(f"[worker] record {job.record_id} codec={video_codec!r}")

        if already_hevc:
            update_conversion_result(
                db, job.record_id,
                status=FileStatus.DISCARDED,
                pid=None, output_size=None,
                started_at=None, finished_at=_utcnow(),
            )
            print(f"[worker] record {job.record_id} discarded — already HEVC")
            await _report_result_to_master(job.record_id, FileStatus.DISCARDED)
            return

        cmd = _build_cmd(ffmpeg_bin, job.file_path, output_path, extra_args,
                         worker_state.encoder, worker_state.presets)
        print(f"[worker] record {job.record_id} encoder={worker_state.encoder!r} → {' '.join(cmd)}")

        started_at = _utcnow()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        worker_state.proc = proc

        record = get_file_record(db, job.record_id)
        if record:
            record.pid = proc.pid
            record.status = FileStatus.PROCESSING
            record.started_at = started_at
            db.commit()
        print(f"[worker] record {job.record_id} pid={proc.pid}  duration={duration_s}s  source={source_size}B")
        await _update_master_status(job.record_id, "processing")

        # Read stdout (progress), stderr (errors) and monitor output size concurrently.
        results = await asyncio.gather(
            _stream_progress(proc.stdout, duration_s),
            _collect_stderr(proc.stderr),
            _monitor_output_size(output_path, source_size, proc),
        )
        stderr_output: str = results[1]
        await proc.wait()
        finished_at = _utcnow()

        if proc.returncode != 0:
            Path(output_path).unlink(missing_ok=True)
            cancel_reason = worker_state.cancel_reason  # "user", "auto", or None
            if cancel_reason:
                update_conversion_result(
                    db, job.record_id,
                    status=FileStatus.CANCELLED,
                    pid=proc.pid,
                    output_size=None,
                    started_at=started_at,
                    finished_at=finished_at,
                    cancel_reason=cancel_reason,
                )
                print(f"[worker] record {job.record_id} cancelled ({cancel_reason})")
                await _report_result_to_master(
                    job.record_id, FileStatus.CANCELLED,
                    pid=proc.pid, started_at=started_at, finished_at=finished_at,
                    cancel_reason=cancel_reason,
                )
            else:
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
                await _report_result_to_master(
                    job.record_id, FileStatus.ERROR,
                    pid=proc.pid, started_at=started_at, finished_at=finished_at,
                )
            return

        output_size = Path(output_path).stat().st_size

        if output_size >= source_size:
            Path(output_path).unlink()
            update_conversion_result(
                db, job.record_id,
                status=FileStatus.CANCELLED,
                pid=proc.pid,
                output_size=output_size,
                started_at=started_at,
                finished_at=finished_at,
                cancel_reason="auto",
            )
            print(
                f"[worker] record {job.record_id} cancelled — "
                f"output ({output_size} B) >= source ({source_size} B)"
            )
            await _report_result_to_master(
                job.record_id, FileStatus.CANCELLED,
                pid=proc.pid, output_size=output_size,
                started_at=started_at, finished_at=finished_at,
                cancel_reason="auto",
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
            await _report_result_to_master(
                job.record_id, FileStatus.COMPLETE,
                pid=proc.pid, output_size=output_size,
                started_at=started_at, finished_at=finished_at,
            )

    except Exception as exc:
        print(f"[worker] record {job.record_id} exception: {exc}")
        finished_at = _utcnow()
        try:
            update_status(db, job.record_id, FileStatus.ERROR)
        except Exception:
            pass
        await _report_result_to_master(job.record_id, FileStatus.ERROR, finished_at=finished_at)
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
        while worker_state.sleeping:
            await asyncio.sleep(1)
        try:
            job = await asyncio.wait_for(worker_state.queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        worker_state.start(job.record_id)
        try:
            await _process(job, ffmpeg_bin, output_dir, extra_args)
        finally:
            if worker_state.drain:
                worker_state.drain = False
                worker_state.sleeping = True
                print("[worker] drain complete — entering sleep mode")
            worker_state.stop()
            worker_state.queue.task_done()
