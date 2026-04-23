"""
FFmpeg worker with an asyncio queue.

Records are enqueued by the poller and processed one at a time by worker_loop().
All streams are copied via -map 0 -c copy; video is re-encoded to HEVC.

After conversion:
  - Output smaller than source → COMPLETE
  - Output same size or larger → output deleted → CANCELLED (cancel_reason="auto")
  - ffmpeg non-zero exit        → ERROR (or CANCELLED if user/auto triggered)

Progress is read from ffmpeg's -progress pipe:1 output.
"""

import asyncio
import shlex
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx

from shared.crud import get_file_record, update_conversion_result, update_status
from shared.models import FileRecord, FileStatus

from .database import SessionLocal
from .state import FfmpegProgress, Job, worker_state


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)



def _build_cmd(
    ffmpeg_bin: str,
    file_path: str,
    output_path: str,
    extra_args: str,
    encoder: str,
    presets: dict,
) -> list[str]:
    preset = presets.get(encoder)
    video_args = (
        shlex.split(preset.video_args)
        if preset and preset.video_args.strip()
        else ["-c:v", "libx265"]
    )
    input_args = shlex.split(preset.input_args) if preset and preset.input_args.strip() else []
    cmd = [ffmpeg_bin] + input_args + ["-i", file_path, "-map", "0", "-c", "copy"] + video_args
    if extra_args:
        cmd.extend(shlex.split(extra_args))
    cmd += ["-y", "-progress", "pipe:1", "-nostats", output_path]
    return cmd



_MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB


def _has_disk_space(path: str) -> bool:
    try:
        return shutil.disk_usage(path).free >= _MIN_FREE_BYTES
    except OSError:
        return True


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



def _parse_progress(frame: dict[str, str], duration_s: float | None, source_size: int = 0, prev_out_time_us: int = 0) -> FfmpegProgress:
    p = FfmpegProgress(source_size_bytes=source_size or None)

    out_time_us = _safe_int(frame.get("out_time_us"))
    out_time_s = out_time_us / 1_000_000
    p.out_time = (frame.get("out_time") or "").strip() or None

    speed_raw = (frame.get("speed") or "").replace("x", "").strip()
    speed = _safe_float(speed_raw) if speed_raw and speed_raw != "N/A" else 0.0
    p.speed = speed or None

    fps = _safe_float(frame.get("fps"))
    p.fps = fps or None

    bitrate = (frame.get("bitrate") or "").strip()
    p.bitrate = bitrate if bitrate and bitrate != "N/A" else None

    size = _safe_int(frame.get("total_size"))
    p.current_size_bytes = size or None

    if duration_s and duration_s > 0 and out_time_s > 0:
        ratio = out_time_s / duration_s
        p.percent = round(min(ratio * 100, 100.0), 1)
        remaining_s = duration_s - out_time_s
        if p.speed and p.speed > 0:
            p.eta_seconds = max(0, round(remaining_s / p.speed))
        stalled = out_time_us > 0 and out_time_us == prev_out_time_us
        p.stalled = stalled
        if not stalled and p.current_size_bytes and ratio > 0:
            p.projected_size_bytes = int(p.current_size_bytes / ratio)

    return p


async def _stream_progress(
    stdout: asyncio.StreamReader,
    duration_s: float | None,
    source_size: int,
    proc: asyncio.subprocess.Process,
) -> tuple[float | None, float | None]:
    frame: dict[str, str] = {}
    fps_samples: list[float] = []
    speed_samples: list[float] = []
    thresholds = sorted(worker_state.cancel_thresholds)
    prev_out_time_us: int = 0
    async for raw in stdout:
        line = raw.decode(errors="replace").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        frame[key.strip()] = value.strip()
        if key.strip() == "progress":
            p = _parse_progress(frame, duration_s, source_size, prev_out_time_us)
            prev_out_time_us = _safe_int(frame.get("out_time_us"))
            worker_state.progress = p
            if p.fps:
                fps_samples.append(p.fps)
            if p.speed:
                speed_samples.append(p.speed)
            frame = {}
            if (thresholds and source_size > 0
                    and p.percent is not None and p.projected_size_bytes is not None):
                ratio = None
                for min_pct, r in thresholds:
                    if p.percent >= min_pct:
                        ratio = r
                if ratio is not None and p.projected_size_bytes > source_size * ratio:
                    over_pct = round((p.projected_size_bytes / source_size - 1) * 100)
                    print(
                        f"[worker] projected size {p.projected_size_bytes} B "
                        f"> {ratio}x source ({source_size} B) at {p.percent:.1f}% — terminating early"
                    )
                    worker_state.cancel_reason = "auto"
                    worker_state.cancel_detail = f"{p.percent:.0f}% — output {over_pct}% over source"
                    try:
                        proc.terminate()
                    except ProcessLookupError:
                        pass
    avg_fps = sum(fps_samples) / len(fps_samples) if fps_samples else None
    avg_speed = sum(speed_samples) / len(speed_samples) if speed_samples else None
    return avg_fps, avg_speed


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
        async with httpx.AsyncClient(timeout=5, **worker_state.tls.httpx_kwargs()) as client:
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
    cancel_detail: str | None = None,
    encoder: str | None = None,
    avg_fps: float | None = None,
    avg_speed: float | None = None,
) -> None:
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
    if cancel_detail is not None:
        body["cancel_detail"] = cancel_detail
    if encoder is not None:
        body["encoder"] = encoder
    if avg_fps is not None:
        body["avg_fps"] = round(avg_fps, 1)
    if avg_speed is not None:
        body["avg_speed"] = round(avg_speed, 2)
    try:
        async with httpx.AsyncClient(timeout=10, **worker_state.tls.httpx_kwargs()) as client:
            response = await client.patch(url, json=body)
            response.raise_for_status()
        print(f"[worker] master updated record {record_id} → {status.value}")
    except Exception as exc:
        print(f"[worker] failed to update master for record {record_id}: {exc}")


async def _monitor_output_size(output_path: str, source_size: int, proc: asyncio.subprocess.Process, output_dir: str) -> None:
    while proc.returncode is None:
        await asyncio.sleep(5)
        if not _has_disk_space(output_dir):
            print(f"[worker] disk full in {output_dir!r} — terminating ffmpeg")
            worker_state.disk_full = True
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            break
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


async def _process(job: Job) -> None:
    ffmpeg_bin = worker_state.ffmpeg_bin
    output_dir = worker_state.output_dir
    extra_args = worker_state.extra_args
    output_path = str(Path(output_dir) / Path(job.file_path).name)
    encoder = worker_state.encoder  # snapshot — user may change encoder mid-conversion
    db = SessionLocal()
    try:
        if worker_state.should_skip(job.record_id):
            worker_state.clear_skip(job.record_id)
            print(f"[worker] record {job.record_id} was cancelled while queued — skipping")
            return
        if not get_file_record(db, job.record_id):
            print(f"[worker] record {job.record_id} no longer exists — skipping")
            return
        source_size = Path(job.file_path).stat().st_size

        if not _has_disk_space(output_dir):
            print(f"[worker] disk full in {output_dir!r} — sleeping")
            worker_state.disk_full = True
            worker_state.sleeping = True
            await _update_master_status(job.record_id, "pending")
            return

        duration_s = job.duration
        worker_state.progress = FfmpegProgress(source_size_bytes=source_size)
        worker_state.current_file = job.file_path
        cmd = _build_cmd(ffmpeg_bin, job.file_path, output_path, extra_args,
                         encoder, worker_state.presets)
        worker_state.current_cmd = ' '.join(cmd)
        print(f"[worker] record {job.record_id} encoder={encoder!r} → {worker_state.current_cmd}")

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
            record.encoder = encoder
            record.started_at = started_at
            db.commit()
        print(f"[worker] record {job.record_id} pid={proc.pid}  duration={duration_s}s  source={source_size}B")
        await _update_master_status(job.record_id, "processing")

        results = await asyncio.gather(
            _stream_progress(proc.stdout, duration_s, source_size, proc),
            _collect_stderr(proc.stderr),
            _monitor_output_size(output_path, source_size, proc, output_dir),
        )
        avg_fps, avg_speed = results[0]
        stderr_output: str = results[1]
        await proc.wait()
        finished_at = _utcnow()

        if proc.returncode != 0:
            Path(output_path).unlink(missing_ok=True)
            if worker_state.disk_full:
                update_status(db, job.record_id, FileStatus.PENDING)
                await _update_master_status(job.record_id, "pending")
                worker_state.sleeping = True
                print(f"[worker] record {job.record_id} reset to pending — disk full")
                return
            cancel_reason = worker_state.cancel_reason
            cancel_detail = worker_state.cancel_detail
            if cancel_reason:
                update_conversion_result(
                    db, job.record_id,
                    status=FileStatus.CANCELLED,
                    pid=proc.pid, output_size=None,
                    started_at=started_at, finished_at=finished_at,
                    cancel_reason=cancel_reason, cancel_detail=cancel_detail,
                    encoder=encoder,
                    avg_fps=avg_fps, avg_speed=avg_speed,
                )
                print(f"[worker] record {job.record_id} cancelled ({cancel_reason})")
                await _report_result_to_master(
                    job.record_id, FileStatus.CANCELLED,
                    pid=proc.pid, started_at=started_at, finished_at=finished_at,
                    cancel_reason=cancel_reason, cancel_detail=cancel_detail,
                    encoder=encoder,
                    avg_fps=avg_fps, avg_speed=avg_speed,
                )
            else:
                update_conversion_result(
                    db, job.record_id,
                    status=FileStatus.ERROR,
                    pid=proc.pid, output_size=None,
                    started_at=started_at, finished_at=finished_at,
                    encoder=encoder,
                    avg_fps=avg_fps, avg_speed=avg_speed,
                )
                print(f"[worker] record {job.record_id} error (exit {proc.returncode}):")
                for line in stderr_output.splitlines():
                    print(f"[ffmpeg]   {line}")
                await _report_result_to_master(
                    job.record_id, FileStatus.ERROR,
                    pid=proc.pid, started_at=started_at, finished_at=finished_at,
                    encoder=encoder,
                    avg_fps=avg_fps, avg_speed=avg_speed,
                )
            return

        output_size = Path(output_path).stat().st_size

        if output_size >= source_size:
            Path(output_path).unlink()
            update_conversion_result(
                db, job.record_id,
                status=FileStatus.CANCELLED,
                pid=proc.pid, output_size=output_size,
                started_at=started_at, finished_at=finished_at,
                cancel_reason="auto",
                encoder=encoder,
                avg_fps=avg_fps, avg_speed=avg_speed,
            )
            print(
                f"[worker] record {job.record_id} cancelled — "
                f"output ({output_size} B) >= source ({source_size} B)"
            )
            await _report_result_to_master(
                job.record_id, FileStatus.CANCELLED,
                pid=proc.pid, output_size=output_size,
                started_at=started_at, finished_at=finished_at,
                cancel_reason="auto", encoder=encoder,
                avg_fps=avg_fps, avg_speed=avg_speed,
            )
        else:
            if worker_state.replace_original:
                try:
                    shutil.move(output_path, job.file_path)
                    print(f"[worker] record {job.record_id} moved output → {job.file_path}")
                except Exception as exc:
                    print(f"[worker] record {job.record_id} failed to replace original: {exc}")
                    update_conversion_result(
                        db, job.record_id,
                        status=FileStatus.ERROR,
                        pid=proc.pid, output_size=output_size,
                        started_at=started_at, finished_at=finished_at,
                        encoder=encoder,
                        avg_fps=avg_fps, avg_speed=avg_speed,
                    )
                    await _report_result_to_master(
                        job.record_id, FileStatus.ERROR,
                        pid=proc.pid, output_size=output_size,
                        started_at=started_at, finished_at=finished_at,
                        encoder=encoder,
                        avg_fps=avg_fps, avg_speed=avg_speed,
                    )
                    return

            update_conversion_result(
                db, job.record_id,
                status=FileStatus.COMPLETE,
                pid=proc.pid, output_size=output_size,
                started_at=started_at, finished_at=finished_at,
                encoder=encoder,
                avg_fps=avg_fps, avg_speed=avg_speed,
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
                encoder=encoder,
                avg_fps=avg_fps, avg_speed=avg_speed,
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


def recover() -> None:
    """Called at startup. Resets interrupted jobs and re-queues all pending records."""
    output_dir = worker_state.output_dir
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


async def worker_loop() -> None:
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
            await _process(job)
        finally:
            if worker_state.drain:
                worker_state.drain = False
                worker_state.sleeping = True
                print("[worker] drain complete — entering sleep mode")
            worker_state.stop()
            worker_state.queue.task_done()
