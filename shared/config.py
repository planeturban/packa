import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FfmpegConfig:
    bin: str = "ffmpeg"
    output_dir: str = ""  # Directory where ffmpeg writes the output file
    extra_args: str = ""  # Extra CLI arguments as a single string


@dataclass
class Config:
    slave_id: str = ""
    path_prefix: str = ""
    ffmpeg: FfmpegConfig = field(default_factory=FfmpegConfig)

    def __post_init__(self) -> None:
        # Normalise: always end with a slash if non-empty
        if self.path_prefix and not self.path_prefix.endswith("/"):
            self.path_prefix += "/"


def load(config_path: str) -> Config:
    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    paths = data.get("paths", {})
    ffmpeg_data = data.get("ffmpeg", {})

    return Config(
        slave_id=data.get("id", ""),
        path_prefix=paths.get("prefix", ""),
        ffmpeg=FfmpegConfig(
            bin=ffmpeg_data.get("bin", "ffmpeg"),
            output_dir=ffmpeg_data.get("output_dir", ""),
            extra_args=ffmpeg_data.get("extra_args", ""),
        ),
    )
