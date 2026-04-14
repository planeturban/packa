import tomllib
from dataclasses import dataclass, field


@dataclass
class TlsConfig:
    cert: str = ""   # path to this node's certificate (PEM)
    key: str = ""    # path to this node's private key (PEM)
    ca: str = ""     # path to the CA certificate used to verify peers (PEM)

    @property
    def enabled(self) -> bool:
        return bool(self.cert and self.key and self.ca)


@dataclass
class ScanConfig:
    # scan directory is always master's path_prefix — no separate setting
    extensions: list[str] = field(
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
    tls: TlsConfig = field(default_factory=TlsConfig)
    ffmpeg: FfmpegConfig = field(default_factory=FfmpegConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)

    def __post_init__(self) -> None:
        # Normalise: always end with a slash if non-empty
        if self.path_prefix and not self.path_prefix.endswith("/"):
            self.path_prefix += "/"


def _load_tls(shared: dict, node: dict) -> TlsConfig:
    """Merge shared [tls] and node-specific [*.tls] sections; node takes precedence."""
    return TlsConfig(
        cert=node.get("cert", shared.get("cert", "")),
        key=node.get("key", shared.get("key", "")),
        ca=node.get("ca", shared.get("ca", "")),
    )


def load_master(config_path: str) -> Config:
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    master = data.get("master", {})
    paths = master.get("paths", {})
    scan_data = master.get("scan", {})
    return Config(
        path_prefix=paths.get("prefix", ""),
        tls=_load_tls(data.get("tls", {}), master.get("tls", {})),
        scan=ScanConfig(
            extensions=scan_data.get("extensions", [".mkv", ".mp4", ".avi", ".mov"]),
        ),
    )


def load_slave(config_path: str) -> Config:
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    master_prefix = data.get("master", {}).get("paths", {}).get("prefix", "")
    slave = data.get("slave", {})
    paths = slave.get("paths", {})
    ffmpeg_data = slave.get("ffmpeg", {})
    worker_data = slave.get("worker", {})
    # Fall back to master's prefix if slave doesn't define its own
    path_prefix = paths.get("prefix", "") or master_prefix
    return Config(
        slave_id=slave.get("id", ""),
        path_prefix=path_prefix,
        tls=_load_tls(data.get("tls", {}), slave.get("tls", {})),
        ffmpeg=FfmpegConfig(
            bin=ffmpeg_data.get("bin", "ffmpeg"),
            output_dir=ffmpeg_data.get("output_dir", ""),
            extra_args=ffmpeg_data.get("extra_args", ""),
        ),
        worker=WorkerConfig(
            batch_size=worker_data.get("batch_size", 1),
            poll_interval=worker_data.get("poll_interval", 5),
        ),
    )
