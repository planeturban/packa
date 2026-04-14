import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScanConfig:
    dir: str = ""                                          # Directory to scan recursively
    extensions: list[str] = field(                        # File extensions to include
        default_factory=lambda: [".mkv", ".mp4", ".avi", ".mov"]
    )


@dataclass
class FfmpegConfig:
    bin: str = "ffmpeg"
    output_dir: str = ""  # Directory where ffmpeg writes the output file
    extra_args: str = ""  # Extra CLI arguments as a single string


@dataclass
class WorkerConfig:
    batch_size: int = 1    # How many jobs to claim from master at once
    poll_interval: int = 5  # Seconds between poll attempts


@dataclass
class Config:
    slave_id: str = ""
    path_prefix: str = ""
    ffmpeg: FfmpegConfig = field(default_factory=FfmpegConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)

    def __post_init__(self) -> None:
        # Normalise: always end with a slash if non-empty
        if self.path_prefix and not self.path_prefix.endswith("/"):
            self.path_prefix += "/"


def load(config_path: str) -> Config:
    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    paths = data.get("paths", {})
    ffmpeg_data = data.get("ffmpeg", {})
    worker_data = data.get("worker", {})
    scan_data = data.get("scan", {})

    return Config(
        slave_id=data.get("id", ""),
        path_prefix=paths.get("prefix", ""),
        ffmpeg=FfmpegConfig(
            bin=ffmpeg_data.get("bin", "ffmpeg"),
            output_dir=ffmpeg_data.get("output_dir", ""),
            extra_args=ffmpeg_data.get("extra_args", ""),
        ),
        worker=WorkerConfig(
            batch_size=worker_data.get("batch_size", 1),
            poll_interval=worker_data.get("poll_interval", 5),
        ),
        scan=ScanConfig(
            dir=scan_data.get("dir", ""),
            extensions=scan_data.get("extensions", [".mkv", ".mp4", ".avi", ".mov"]),
        ),
    )
