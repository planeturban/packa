import os
import tomllib
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Environment variable helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val is not None else default


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

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
    min_size: int = 0   # bytes — files smaller than this are skipped (0 = no limit)
    max_size: int = 0   # bytes — files larger than this are skipped (0 = no limit)


@dataclass
class FfmpegConfig:
    bin: str = "ffmpeg"
    output_dir: str = ""        # Directory where ffmpeg writes the output file
    extra_args: str = ""        # Extra CLI arguments as a single string
    video_encoder: str = "libx265"  # Encoder for non-HEVC files, e.g. "hevc_videotoolbox"


@dataclass
class WorkerConfig:
    batch_size: int = 1    # How many jobs to claim from master at once
    poll_interval: int = 5  # Seconds between poll attempts


@dataclass
class Config:
    # Operational (all nodes)
    bind: str = "localhost"
    api_port: int = 9000
    # Slave-specific operational
    master_host: str = "localhost"
    master_port: int = 9000
    advertise_host: str = ""
    # Business logic
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


# ---------------------------------------------------------------------------
# TLS merge helper (shared by load functions and web/config.py)
# ---------------------------------------------------------------------------

def _load_tls(shared: dict, node: dict) -> TlsConfig:
    """Merge shared [tls] and node-specific [*.tls] sections; node takes precedence."""
    return TlsConfig(
        cert=node.get("cert", shared.get("cert", "")),
        key=node.get("key", shared.get("key", "")),
        ca=node.get("ca", shared.get("ca", "")),
    )


# ---------------------------------------------------------------------------
# Load functions — priority: config file < env < (CLI applied in main())
# ---------------------------------------------------------------------------

def load_master(config_path: str | None) -> Config:
    data: dict = {}
    if config_path:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    master = data.get("master", {})
    paths = master.get("paths", {})
    scan_data = master.get("scan", {})
    shared_tls = data.get("tls", {})
    master_tls = master.get("tls", {})

    ext_env = os.environ.get("PACKA_MASTER_EXTENSIONS")
    extensions = (
        [e.strip() for e in ext_env.split(",")]
        if ext_env
        else scan_data.get("extensions", [".mkv", ".mp4", ".avi", ".mov"])
    )

    return Config(
        bind=_env("PACKA_MASTER_BIND", master.get("bind", "localhost")),
        api_port=_env_int("PACKA_MASTER_API_PORT", master.get("api_port", 9000)),
        path_prefix=_env("PACKA_MASTER_PREFIX", paths.get("prefix", "")),
        tls=TlsConfig(
            cert=_env("PACKA_MASTER_TLS_CERT", master_tls.get("cert", shared_tls.get("cert", ""))),
            key=_env("PACKA_MASTER_TLS_KEY", master_tls.get("key", shared_tls.get("key", ""))),
            ca=_env("PACKA_TLS_CA", master_tls.get("ca", shared_tls.get("ca", ""))),
        ),
        scan=ScanConfig(
            extensions=extensions,
            min_size=_env_int("PACKA_MASTER_MIN_SIZE", scan_data.get("min_size", 0)),
            max_size=_env_int("PACKA_MASTER_MAX_SIZE", scan_data.get("max_size", 0)),
        ),
    )


def load_slave(config_path: str | None) -> Config:
    data: dict = {}
    if config_path:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    master_prefix = data.get("master", {}).get("paths", {}).get("prefix", "")
    slave = data.get("slave", {})
    paths = slave.get("paths", {})
    ffmpeg_data = slave.get("ffmpeg", {})
    worker_data = slave.get("worker", {})
    shared_tls = data.get("tls", {})
    slave_tls = slave.get("tls", {})

    # Slave prefix falls back to master's if not set
    path_prefix = _env(
        "PACKA_SLAVE_PREFIX",
        paths.get("prefix", "") or master_prefix,
    )

    return Config(
        bind=_env("PACKA_SLAVE_BIND", slave.get("bind", "localhost")),
        api_port=_env_int("PACKA_SLAVE_API_PORT", slave.get("api_port", 8000)),
        master_host=_env("PACKA_SLAVE_MASTER_HOST", slave.get("master_host", "localhost")),
        master_port=_env_int("PACKA_SLAVE_MASTER_PORT", slave.get("master_port", 9000)),
        advertise_host=_env("PACKA_SLAVE_ADVERTISE_HOST", slave.get("advertise_host", "")),
        slave_id=_env("PACKA_SLAVE_ID", slave.get("id", "")),
        path_prefix=path_prefix,
        tls=TlsConfig(
            cert=_env("PACKA_SLAVE_TLS_CERT", slave_tls.get("cert", shared_tls.get("cert", ""))),
            key=_env("PACKA_SLAVE_TLS_KEY", slave_tls.get("key", shared_tls.get("key", ""))),
            ca=_env("PACKA_TLS_CA", slave_tls.get("ca", shared_tls.get("ca", ""))),
        ),
        ffmpeg=FfmpegConfig(
            bin=_env("PACKA_SLAVE_FFMPEG_BIN", ffmpeg_data.get("bin", "ffmpeg")),
            output_dir=_env("PACKA_SLAVE_FFMPEG_OUTPUT_DIR", ffmpeg_data.get("output_dir", "")),
            extra_args=_env("PACKA_SLAVE_FFMPEG_EXTRA_ARGS", ffmpeg_data.get("extra_args", "")),
            video_encoder=_env("PACKA_SLAVE_FFMPEG_VIDEO_ENCODER", ffmpeg_data.get("video_encoder", "libx265")),
        ),
        worker=WorkerConfig(
            batch_size=_env_int("PACKA_SLAVE_BATCH_SIZE", worker_data.get("batch_size", 1)),
            poll_interval=_env_int("PACKA_SLAVE_POLL_INTERVAL", worker_data.get("poll_interval", 5)),
        ),
    )
