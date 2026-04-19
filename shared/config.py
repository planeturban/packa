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


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    return float(val) if val is not None else default


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ScanConfig:
    extensions: list[str] = field(
        default_factory=lambda: [".mkv", ".mp4", ".avi", ".mov"]
    )
    min_size: int = 0         # bytes (converted from MB at load time) — 0 = no limit
    max_size: int = 0         # bytes (converted from MB at load time) — 0 = no limit
    checksum_bytes: int = 4194304  # bytes to read from middle of file for content hash (default 4 MB)


@dataclass
class EncoderPreset:
    """FFmpeg arguments for one encoder preset."""
    display_name: str = ""  # human-readable label for the web dashboard dropdown
    video_args: str = ""    # video codec args, placed after -i
    input_args: str = ""    # input options placed before -i (e.g. -hwaccel vaapi)


@dataclass
class FfmpegConfig:
    bin: str = "ffmpeg"
    output_dir: str = ""
    extra_args: str = ""
    presets: dict[str, EncoderPreset] = field(default_factory=dict)
    available_encoders: list[str] = field(
        default_factory=lambda: ["libx265", "nvenc", "vaapi", "videotoolbox"]
    )


def _parse_cancel_thresholds(s: str) -> list[tuple[float, float]]:
    result = []
    for pair in s.split(","):
        pair = pair.strip()
        if ":" in pair:
            p, r = pair.split(":", 1)
            result.append((float(p.strip()), float(r.strip())))
    return sorted(result)


@dataclass
class WorkerConfig:
    batch_size: int = 1
    poll_interval: int = 5
    cancel_thresholds: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class Config:
    bind: str = "localhost"
    api_port: int = 9000
    master_host: str = "localhost"
    master_port: int = 9000
    advertise_host: str = ""
    slave_id: str = ""
    path_prefix: str = ""
    ffmpeg: FfmpegConfig = field(default_factory=FfmpegConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)

    def __post_init__(self) -> None:
        if self.path_prefix and not self.path_prefix.endswith("/"):
            self.path_prefix += "/"


@dataclass
class WebConfig:
    username: str = "admin"
    password: str = ""
    secret_key: str = ""
    master_host: str = "localhost"
    master_port: int = 9000
    bind: str = "localhost"
    port: int = 8080


# ---------------------------------------------------------------------------
# Load functions — priority: config file < env < CLI (applied in main())
# ---------------------------------------------------------------------------

def load_master(config_path: str | None) -> Config:
    data: dict = {}
    if config_path:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    master = data.get("master", {})
    paths = master.get("paths", {})
    scan_data = master.get("scan", {})

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
        scan=ScanConfig(
            extensions=extensions,
            min_size=_env_int("PACKA_MASTER_MIN_SIZE", scan_data.get("min_size", 0)) * 1024 * 1024,
            max_size=_env_int("PACKA_MASTER_MAX_SIZE", scan_data.get("max_size", 0)) * 1024 * 1024,
            checksum_bytes=_env_int("PACKA_MASTER_CHECKSUM_BYTES", scan_data.get("checksum_bytes", 4194304)),
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

    path_prefix = _env(
        "PACKA_SLAVE_PREFIX",
        paths.get("prefix", "") or master_prefix,
    )

    encoder_data: dict = ffmpeg_data.get("encoder", {})

    # Presets are entirely config-driven; only what's in [slave.ffmpeg.encoder.*] is loaded.
    # If nothing is configured, fall back to a bare libx265 preset so the slave can run.
    if encoder_data:
        presets: dict[str, EncoderPreset] = {
            name: EncoderPreset(
                display_name=values.get("display_name", ""),
                video_args=values.get("video_args", ""),
                input_args=values.get("input_args", ""),
            )
            for name, values in encoder_data.items()
        }
    else:
        presets = {"libx265": EncoderPreset(video_args="-c:v libx265")}

    # explicit list > keys from defined encoder sections
    if ffmpeg_data.get("encoders"):
        available_encoders: list[str] = ffmpeg_data["encoders"]
    else:
        available_encoders = list(presets.keys())

    _ct_env = os.environ.get("PACKA_SLAVE_CANCEL_THRESHOLDS")
    if _ct_env:
        _cancel_thresholds = _parse_cancel_thresholds(_ct_env)
    elif "cancel_thresholds" in worker_data:
        _cancel_thresholds = sorted((float(p), float(r)) for p, r in worker_data["cancel_thresholds"])
    else:
        _cancel_thresholds = []

    return Config(
        bind=_env("PACKA_SLAVE_BIND", slave.get("bind", "localhost")),
        api_port=_env_int("PACKA_SLAVE_API_PORT", slave.get("api_port", 8000)),
        master_host=_env("PACKA_SLAVE_MASTER_HOST", slave.get("master_host", "localhost")),
        master_port=_env_int("PACKA_SLAVE_MASTER_PORT", slave.get("master_port", 9000)),
        advertise_host=_env("PACKA_SLAVE_ADVERTISE_HOST", slave.get("advertise_host", "")),
        slave_id=_env("PACKA_SLAVE_ID", slave.get("id", "")),
        path_prefix=path_prefix,
        ffmpeg=FfmpegConfig(
            bin=_env("PACKA_SLAVE_FFMPEG_BIN", ffmpeg_data.get("bin", "ffmpeg")),
            output_dir=_env("PACKA_SLAVE_FFMPEG_OUTPUT_DIR", ffmpeg_data.get("output_dir", "")),
            extra_args=_env("PACKA_SLAVE_FFMPEG_EXTRA_ARGS", ffmpeg_data.get("extra_args", "")),
            presets=presets,
            available_encoders=available_encoders,
        ),
        worker=WorkerConfig(
            batch_size=_env_int("PACKA_SLAVE_BATCH_SIZE", worker_data.get("batch_size", 1)),
            poll_interval=_env_int("PACKA_SLAVE_POLL_INTERVAL", worker_data.get("poll_interval", 5)),
            cancel_thresholds=_cancel_thresholds,
        ),
    )


def load_web(config_path: str | None) -> WebConfig:
    data: dict = {}
    if config_path:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    web = data.get("web", {})

    return WebConfig(
        username=_env("PACKA_WEB_USERNAME", web.get("username", "admin")),
        password=_env("PACKA_WEB_PASSWORD", web.get("password", "")),
        secret_key=_env("PACKA_WEB_SECRET_KEY", web.get("secret_key", "")),
        master_host=_env("PACKA_WEB_MASTER_HOST", web.get("master_host", "localhost")),
        master_port=_env_int("PACKA_WEB_MASTER_PORT", web.get("master_port", 9000)),
        bind=_env("PACKA_WEB_BIND", web.get("bind", "localhost")),
        port=_env_int("PACKA_WEB_PORT", web.get("port", 8080)),
    )
