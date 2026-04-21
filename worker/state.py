import asyncio
from dataclasses import dataclass

from shared.config import EncoderPreset


@dataclass
class Job:
    record_id: int
    file_path: str
    duration: float | None = None


@dataclass
class FfmpegProgress:
    percent: float | None = None
    speed: float | None = None
    fps: float | None = None
    out_time: str | None = None
    eta_seconds: int | None = None
    bitrate: str | None = None
    source_size_bytes: int | None = None
    current_size_bytes: int | None = None
    projected_size_bytes: int | None = None


class WorkerState:
    def __init__(self) -> None:
        self.active: bool = False
        self.record_id: int | None = None
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.progress: FfmpegProgress | None = None
        self.proc: asyncio.subprocess.Process | None = None
        self.worker_id: int | None = None
        self.worker_config_id: str | None = None
        self.master_url: str | None = None

        self.paused: bool = False
        self.drain: bool = False
        self.sleeping: bool = False
        self.unconfigured: bool = False
        self.disk_full: bool = False
        self.cancel_reason: str | None = None
        self.encoder: str = "libx265"
        self.batch_size: int = 1
        self.current_cmd: str = ""
        self.replace_original: bool = False
        self.cancel_thresholds: list[tuple[float, float]] = []
        self.presets: dict[str, EncoderPreset] = {}
        self.available_encoders: list[str] = ["libx265", "nvenc", "vaapi", "videotoolbox"]

        self._skip_ids: set[int] = set()

    def cancel_queued(self, record_id: int) -> None:
        """Mark a queued (not yet active) job to be skipped by the worker."""
        self._skip_ids.add(record_id)

    def should_skip(self, record_id: int) -> bool:
        return record_id in self._skip_ids

    def clear_skip(self, record_id: int) -> None:
        self._skip_ids.discard(record_id)

    def start(self, record_id: int) -> None:
        self.active = True
        self.record_id = record_id
        self.progress = None
        self.proc = None

    def stop(self) -> None:
        self.active = False
        self.record_id = None
        self.progress = None
        self.proc = None
        self.paused = False
        self.cancel_reason = None
        self.current_cmd = ""

    @property
    def queued(self) -> int:
        return self.queue.qsize()

    def enqueue(self, job: Job) -> None:
        self.queue.put_nowait(job)


worker_state = WorkerState()
