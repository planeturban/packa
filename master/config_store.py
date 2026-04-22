"""
Layered master config: defaults < file < env < database < CLI.

Values in the database are editable at runtime via the web dashboard.
CLI flags always win and are never persisted.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from shared.config import Config, ScanConfig

from .settings import MasterSetting


@dataclass
class Field:
    key: str                    # API/UI key, e.g. "bind", "scan.extensions"
    env: str                    # env var name
    file_path: tuple[str, ...]  # dotted path into TOML
    typ: str                    # "str" | "int" | "bool" | "list[str]"
    default: Any
    requires_restart: bool = False
    label: str = ""
    help: str = ""


MASTER_FIELDS: list[Field] = [
    Field("path_prefix", "PACKA_MASTER_PREFIX", ("master", "paths", "prefix"),
          "str", "",
          label="Path prefix", help="Root directory for scans. Stripped from paths sent to workers."),
    Field("extensions", "PACKA_MASTER_EXTENSIONS", ("master", "scan", "extensions"),
          "list[str]", [".mkv", ".mp4", ".avi", ".mov"],
          label="Scan extensions", help="File extensions included in scans."),
    Field("min_size_mb", "PACKA_MASTER_MIN_SIZE", ("master", "scan", "min_size"),
          "int", 0,
          label="Min file size (MB)", help="Skip files smaller than this. 0 = no limit."),
    Field("max_size_mb", "PACKA_MASTER_MAX_SIZE", ("master", "scan", "max_size"),
          "int", 0,
          label="Max file size (MB)", help="Skip files larger than this. 0 = no limit."),
    Field("checksum_bytes", "PACKA_MASTER_CHECKSUM_BYTES", ("master", "scan", "checksum_bytes"),
          "int", 4_194_304,
          label="Checksum bytes", help="Bytes read from the middle of each file for duplicate detection."),
    Field("probe_batch_size", "PACKA_MASTER_PROBE_BATCH_SIZE", ("master", "scan", "probe_batch_size"),
          "int", 20,
          label="Probe batch size", help="Files probed concurrently per tick."),
    Field("probe_interval", "PACKA_MASTER_PROBE_INTERVAL", ("master", "scan", "probe_interval"),
          "int", 60,
          label="Probe interval (s)", help="Seconds to sleep when the probe queue is empty."),
    Field("scan_periodic_enabled", "PACKA_MASTER_SCAN_PERIODIC_ENABLED",
          ("master", "scan", "periodic", "enabled"),
          "bool", False,
          label="Periodic scan", help="Automatically re-scan the path prefix on a schedule."),
    Field("scan_interval_seconds", "PACKA_MASTER_SCAN_INTERVAL",
          ("master", "scan", "periodic", "interval"),
          "int", 60,
          label="Periodic scan interval (s)", help="Seconds between periodic scans. Minimum 10."),
]

_FIELDS_BY_KEY = {f.key: f for f in MASTER_FIELDS}

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
    if typ == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        s = str(value).strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
        raise ValueError(f"cannot coerce {value!r} to bool")
    if typ == "str":
        return str(value)
    if typ == "list[str]":
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [v.strip() for v in str(value).split(",") if v.strip()]
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
    for fld in MASTER_FIELDS:
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
    for fld in MASTER_FIELDS:
        raw = os.environ.get(fld.env)
        if raw is None:
            continue
        try:
            out[fld.key] = _coerce(raw, fld.typ)
        except (ValueError, TypeError):
            continue
    return out


def read_db_values(db: Session) -> dict[str, Any]:
    rows = (
        db.query(MasterSetting)
        .filter(MasterSetting.key.like(f"{_DB_KEY_PREFIX}%"))
        .all()
    )
    out: dict[str, Any] = {}
    for row in rows:
        key = row.key[len(_DB_KEY_PREFIX):]
        fld = _FIELDS_BY_KEY.get(key)
        if not fld:
            continue
        out[key] = _decode_from_db(row.value, fld.typ)
    return out


def default_values() -> dict[str, Any]:
    return {f.key: f.default for f in MASTER_FIELDS}


# ---------------------------------------------------------------------------
# Merge / apply
# ---------------------------------------------------------------------------

def compute_effective(
    file_values: dict[str, Any],
    env_values: dict[str, Any],
    db_values: dict[str, Any],
    cli_values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Merge layers; return (effective, sources)."""
    effective: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for fld in MASTER_FIELDS:
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
    """Project the effective key/value dict back onto a Config dataclass."""
    config.path_prefix = values["path_prefix"] or ""
    if config.path_prefix and not config.path_prefix.endswith("/"):
        config.path_prefix += "/"
    if not isinstance(config.scan, ScanConfig):
        config.scan = ScanConfig()
    config.scan.extensions = list(values["extensions"])
    config.scan.min_size = int(values["min_size_mb"]) * 1024 * 1024
    config.scan.max_size = int(values["max_size_mb"]) * 1024 * 1024
    config.scan.checksum_bytes = int(values["checksum_bytes"])
    config.scan.probe_batch_size = int(values["probe_batch_size"])
    config.scan.probe_interval = int(values["probe_interval"])
    config.scan.periodic_enabled = bool(values["scan_periodic_enabled"])
    config.scan.periodic_interval = max(10, int(values["scan_interval_seconds"]))


# ---------------------------------------------------------------------------
# DB ops
# ---------------------------------------------------------------------------

def set_db_value(db: Session, key: str, value: Any) -> None:
    fld = _FIELDS_BY_KEY[key]
    coerced = _coerce(value, fld.typ)
    db_key = f"{_DB_KEY_PREFIX}{key}"
    row = db.query(MasterSetting).filter(MasterSetting.key == db_key).first()
    encoded = _encode_for_db(coerced)
    if row:
        row.value = encoded
    else:
        db.add(MasterSetting(key=db_key, value=encoded))
    db.commit()


def delete_db_value(db: Session, key: str) -> bool:
    db_key = f"{_DB_KEY_PREFIX}{key}"
    row = db.query(MasterSetting).filter(MasterSetting.key == db_key).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def is_initialized(db: Session) -> bool:
    row = db.query(MasterSetting).filter(MasterSetting.key == _INIT_MARKER).first()
    return row is not None and row.value == "true"


def mark_initialized(db: Session) -> None:
    row = db.query(MasterSetting).filter(MasterSetting.key == _INIT_MARKER).first()
    if row:
        row.value = "true"
    else:
        db.add(MasterSetting(key=_INIT_MARKER, value="true"))
    db.commit()


def initialize_from_layers(
    db: Session,
    file_values: dict[str, Any],
    env_values: dict[str, Any],
) -> None:
    """On first run, seed DB with file+env+default values (not CLI)."""
    for fld in MASTER_FIELDS:
        if fld.key in env_values:
            value = env_values[fld.key]
        elif fld.key in file_values:
            value = file_values[fld.key]
        else:
            value = fld.default
        set_db_value(db, fld.key, value)
    mark_initialized(db)


# Legacy key → new config key. Old rows were stored under the bare key
# before periodic scan settings were folded into the layered config.
_LEGACY_KEYS: dict[str, str] = {
    "scan_interval_seconds": "scan_interval_seconds",
    "scan_periodic_enabled": "scan_periodic_enabled",
}


def migrate_legacy_keys(db: Session) -> int:
    """Copy legacy bare-key rows into the new config.* namespace. Idempotent."""
    moved = 0
    for legacy, new_key in _LEGACY_KEYS.items():
        row = db.query(MasterSetting).filter(MasterSetting.key == legacy).first()
        if not row:
            continue
        fld = _FIELDS_BY_KEY.get(new_key)
        if fld is None:
            continue
        new_db_key = f"{_DB_KEY_PREFIX}{new_key}"
        existing = db.query(MasterSetting).filter(MasterSetting.key == new_db_key).first()
        if not existing:
            try:
                coerced = _coerce(row.value, fld.typ)
            except (ValueError, TypeError):
                db.delete(row)
                continue
            db.add(MasterSetting(key=new_db_key, value=_encode_for_db(coerced)))
            moved += 1
        db.delete(row)
    if moved:
        db.commit()
    return moved


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
        for f in MASTER_FIELDS
    ]


def field(key: str) -> Field | None:
    return _FIELDS_BY_KEY.get(key)
