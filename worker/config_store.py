"""
Layered worker config: defaults < file < env < database < CLI.

Values in the database are editable at runtime via the web dashboard.
CLI flags always win and are never persisted.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from typing import Any

from shared.config import Config, _parse_cancel_thresholds

from .store import delete_setting, get_setting, get_settings_with_prefix, set_setting


@dataclass
class Field:
    key: str                    # API/UI key
    env: str                    # environment variable name
    file_path: tuple[str, ...]  # path into TOML document
    typ: str                    # "str" | "int" | "list[str]"
    default: Any
    requires_restart: bool = False
    label: str = ""
    help: str = ""


WORKER_FIELDS: list[Field] = [
    Field("path_prefix", "PACKA_WORKER_PREFIX", ("worker", "paths", "prefix"),
          "str", "",
          label="Path prefix", help="Prepended to file paths received from master. Takes effect on the next poll cycle."),
    Field("output_dir", "PACKA_WORKER_FFMPEG_OUTPUT_DIR", ("worker", "ffmpeg", "output_dir"),
          "str", "",
          label="Output directory", help="Directory where converted files are written."),
    Field("ffmpeg_bin", "PACKA_WORKER_FFMPEG_BIN", ("worker", "ffmpeg", "bin"),
          "str", "ffmpeg",
          label="FFmpeg binary", help="Path to the ffmpeg executable."),
    Field("extra_args", "PACKA_WORKER_FFMPEG_EXTRA_ARGS", ("worker", "ffmpeg", "extra_args"),
          "str", "",
          label="Extra ffmpeg args", help="Additional arguments appended to every ffmpeg command."),
    Field("poll_interval", "PACKA_WORKER_POLL_INTERVAL", ("worker", "worker", "poll_interval"),
          "int", 5,
          label="Poll interval (s)", help="Seconds to wait between polls when the job queue is empty."),
    Field("batch_size", "PACKA_WORKER_BATCH_SIZE", ("worker", "worker", "batch_size"),
          "int", 1,
          label="Batch size", help="Number of jobs to claim per poll cycle."),
    Field("stall_timeout", "PACKA_WORKER_STALL_TIMEOUT", ("worker", "worker", "stall_timeout"),
          "int", 120,
          label="Stall timeout (s)", help="Seconds without ffmpeg progress before the job is cancelled. 0 disables the watchdog."),
    Field("cancel_thresholds", "PACKA_WORKER_CANCEL_THRESHOLDS", ("worker", "worker", "cancel_thresholds"),
          "thresholds", [],
          label="Cancel thresholds", help="Cancel early if projected output exceeds source × ratio at the given progress %. Format: [[pct, ratio], ...] e.g. [[20.0, 1.15], [40.0, 1.05], [60.0, 1.0]]"),
]

_FIELDS_BY_KEY = {f.key: f for f in WORKER_FIELDS}
_DB_KEY_PREFIX = "config."
_INIT_MARKER = "config_initialized"


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

def _coerce(value: Any, typ: str) -> Any:
    if value is None:
        return None
    if typ == "int":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        return int(str(value).strip())
    if typ == "str":
        return str(value)
    if typ == "list[str]":
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [v.strip() for v in str(value).split(",") if v.strip()]
    if typ == "thresholds":
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    result.append([float(item[0]), float(item[1])])
            return result
        s = str(value).strip() if value is not None else ""
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return _coerce("thresholds", parsed)
        except (ValueError, json.JSONDecodeError):
            pass
        # env-var format: "20:1.15,40:1.05"
        return _coerce("thresholds", _parse_cancel_thresholds(s))
    raise ValueError(f"unsupported type {typ!r}")


def _encode_for_db(value: Any) -> str:
    return json.dumps(value)


def _decode_from_db(raw: str, typ: str) -> Any:
    try:
        return _coerce(json.loads(raw), typ)
    except (ValueError, TypeError):
        return _coerce(raw, typ)


# ---------------------------------------------------------------------------
# Layer readers
# ---------------------------------------------------------------------------

def read_file_values(config_path: str | None) -> dict[str, Any]:
    if not config_path:
        return {}
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out: dict[str, Any] = {}
    for fld in WORKER_FIELDS:
        node: Any = data
        for part in fld.file_path:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is not None:
            try:
                out[fld.key] = _coerce(node, fld.typ)
            except (ValueError, TypeError):
                continue
    return out


def read_env_values() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fld in WORKER_FIELDS:
        raw = os.environ.get(fld.env)
        if raw is None:
            continue
        try:
            out[fld.key] = _coerce(raw, fld.typ)
        except (ValueError, TypeError):
            continue
    return out


def read_db_values() -> dict[str, Any]:
    rows = get_settings_with_prefix(_DB_KEY_PREFIX)
    out: dict[str, Any] = {}
    for db_key, raw in rows.items():
        key = db_key[len(_DB_KEY_PREFIX):]
        fld = _FIELDS_BY_KEY.get(key)
        if not fld:
            continue
        out[key] = _decode_from_db(raw, fld.typ)
    return out


def default_values() -> dict[str, Any]:
    return {f.key: f.default for f in WORKER_FIELDS}


# ---------------------------------------------------------------------------
# Merge / apply
# ---------------------------------------------------------------------------

def compute_effective(
    file_values: dict[str, Any],
    env_values: dict[str, Any],
    db_values: dict[str, Any],
    cli_values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    effective: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for fld in WORKER_FIELDS:
        value = fld.default
        source = "default"
        if fld.key in file_values:
            value, source = file_values[fld.key], "file"
        if fld.key in env_values:
            value, source = env_values[fld.key], "env"
        if fld.key in db_values:
            value, source = db_values[fld.key], "db"
        if fld.key in cli_values:
            value, source = cli_values[fld.key], "cli"
        effective[fld.key] = value
        sources[fld.key] = source
    return effective, sources


def apply_to_config(values: dict[str, Any], config: Config) -> None:
    """Project effective values back onto a Config object."""
    config.path_prefix = values["path_prefix"] or ""
    if config.path_prefix and not config.path_prefix.endswith("/"):
        config.path_prefix += "/"
    config.ffmpeg.output_dir = values["output_dir"]
    config.ffmpeg.bin = values["ffmpeg_bin"]
    config.ffmpeg.extra_args = values["extra_args"]
    config.worker.poll_interval = max(1, int(values["poll_interval"]))
    config.worker.batch_size = max(1, int(values["batch_size"]))
    config.worker.stall_timeout = max(0, int(values["stall_timeout"]))
    raw_ct = values.get("cancel_thresholds") or []
    config.worker.cancel_thresholds = sorted((float(p), float(r)) for p, r in raw_ct)


# ---------------------------------------------------------------------------
# DB ops
# ---------------------------------------------------------------------------

def set_db_value(key: str, value: Any) -> None:
    fld = _FIELDS_BY_KEY[key]
    coerced = _coerce(value, fld.typ)
    set_setting(f"{_DB_KEY_PREFIX}{key}", _encode_for_db(coerced))


def delete_db_value(key: str) -> bool:
    return delete_setting(f"{_DB_KEY_PREFIX}{key}")


def is_initialized() -> bool:
    return get_setting(_INIT_MARKER) == "true"


def mark_initialized() -> None:
    set_setting(_INIT_MARKER, "true")


def initialize_from_layers(
    file_values: dict[str, Any],
    env_values: dict[str, Any],
) -> None:
    """On first run, seed DB with file+env+default values (not CLI)."""
    for fld in WORKER_FIELDS:
        if fld.key in env_values:
            value = env_values[fld.key]
        elif fld.key in file_values:
            value = file_values[fld.key]
        else:
            value = fld.default
        set_db_value(fld.key, value)
    mark_initialized()


def fields_for_api() -> list[dict[str, Any]]:
    return [
        {
            "key": f.key,
            "type": f.typ,
            "default": f.default,
            "requires_restart": f.requires_restart,
            "label": f.label,
            "help": f.help,
        }
        for f in WORKER_FIELDS
    ]


def field(key: str) -> Field | None:
    return _FIELDS_BY_KEY.get(key)
