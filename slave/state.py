import asyncio
from dataclasses import dataclass

from shared.config import TlsConfig


@dataclass
class Job:
    record_id: int
    file_path: str


@dataclass
class FfmpegProgress:
    percent: float | None = None          # 0–100
    speed: float | None = None            # e.g. 1.5 → 1.5× real-time
    fps: float | None = None
    out_time: str | None = None           # "HH:MM:SS.ms"
    eta_seconds: int | None = None
    bitrate: str | None = None            # e.g. "5000.0kbits/s"
    current_size_bytes: int | None = None
    projected_size_bytes: int | None = None


class WorkerState:
    def __init__(self) -> None:
        self.active: bool = False
        self.record_id: int | None = None
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.progress: FfmpegProgress | None = None
        self.proc: asyncio.subprocess.Process | None = None  # running ffmpeg process
        # Set after registration with master
        self.slave_id: int | None = None          # numeric ID assigned by master
        self.slave_config_id: str | None = None   # string ID from config file
        self.master_url: str | None = None
        self.tls: TlsConfig = TlsConfig()

        self.paused: bool = False          # ffmpeg suspended (SIGSTOP)
        self.drain: bool = False           # finish current job, then stop polling
        self.sleeping: bool = False        # don't start new jobs, don't poll
        self.cancel_reason: str | None = None  # "user" or "auto" when terminating
        # Encoder preset — can be changed at runtime via POST /settings
        self.encoder: str = "libx265"              # libx265 | nvenc | vaapi | videotoolbox
        self.vaapi_device: str = "/dev/dri/renderD128"

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

    @property
    def queued(self) -> int:
        return self.queue.qsize()

    def enqueue(self, job: Job) -> None:
        self.queue.put_nowait(job)


worker_state = WorkerState()
