"""
Master entry point.

Configuration priority: config file < environment variables < CLI flags.

Environment variables:
  PACKA_MASTER_BIND        Bind address
  PACKA_MASTER_API_PORT    API port
  PACKA_MASTER_PREFIX      Root path prefix
  PACKA_MASTER_EXTENSIONS  Comma-separated file extensions (e.g. .mkv,.mp4)

Flags:
  --bind       Address to bind the API server (default: localhost; "any" → 0.0.0.0)
  --api-port   Port for the API (default: 9000)
  --config     Path to TOML config file

Usage:
  python -m master.master --config packa.toml
"""

import argparse
import asyncio
import builtins
import os
from datetime import datetime

_orig_print = builtins.print
def _ts_print(*args, **kwargs):
    _orig_print(datetime.now().strftime('%H:%M:%S'), *args, **kwargs)
builtins.print = _ts_print

import tomllib
import uvicorn

from shared.config import Config, _env, _env_int
from shared.log import UVICORN_LOG_CONFIG
from shared.tls import TlsConfig, patch_uvicorn_for_mtls

from . import config_store
from .api import app, set_config, set_config_layers
from .database import SessionLocal
from .settings import MasterSetting  # noqa: F401 — ensure table is registered
from .tls_manager import ensure_ca, ensure_server_cert, generate_token, get_ca_fingerprint, get_token_info


async def _main(bind: str, api_port: int, tls: TlsConfig) -> None:
    patch_uvicorn_for_mtls()
    tls_kwargs = tls.uvicorn_tls_kwargs(require_client_cert=False)
    uvi_config = uvicorn.Config(app, host=bind, port=api_port, log_level="info",
                                log_config=UVICORN_LOG_CONFIG, **tls_kwargs)
    await uvicorn.Server(uvi_config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa master")
    parser.add_argument("--bind", default=None,
                        help='Address to bind the API server ("any" → 0.0.0.0)')
    parser.add_argument("--api-port", type=int, default=None, help="API port")
    parser.add_argument("--advertise-host", default=None,
                        help="Hostname/IP clients use to reach master — included in TLS server cert SANs")
    parser.add_argument("--config", help="Path to TOML config file")
    args = parser.parse_args()

    # Read bind/api_port from file+env+CLI directly (not via config store).
    _file_data: dict = {}
    if args.config:
        try:
            with open(args.config, "rb") as _f:
                _file_data = tomllib.load(_f).get("master", {})
        except (OSError, tomllib.TOMLDecodeError):
            pass
    bind_raw = (
        args.bind if args.bind is not None
        else _env("PACKA_MASTER_BIND", _file_data.get("bind", "localhost"))
    )
    bind = "0.0.0.0" if bind_raw == "any" else bind_raw
    api_port = (
        args.api_port if args.api_port is not None
        else _env_int("PACKA_MASTER_API_PORT", _file_data.get("api_port", 9000))
    )

    # Load config store layers for all other settings.
    cli_values: dict = {}
    file_values = config_store.read_file_values(args.config)
    env_values = config_store.read_env_values()

    # master/api.py creates the DB and tables at import time; safe to open a session.
    db = SessionLocal()
    try:
        if not config_store.is_initialized(db):
            config_store.initialize_from_layers(db, file_values, env_values)
            print(f"[master] initialised master_settings from file+env+defaults")
        moved = config_store.migrate_legacy_keys(db)
        if moved:
            print(f"[master] migrated {moved} legacy setting(s) into config.* namespace")
        db_values = config_store.read_db_values(db)
    finally:
        db.close()

    effective, sources = config_store.compute_effective(file_values, env_values, db_values, cli_values)
    config = Config(bind=bind_raw, api_port=api_port)
    config_store.apply_to_config(effective, config)
    if args.advertise_host is not None:
        config.advertise_host = args.advertise_host
    elif not config.advertise_host:
        config.advertise_host = _env("PACKA_MASTER_ADVERTISE_HOST", _file_data.get("advertise_host", ""))
    _file_tls = _file_data.get("tls", {})
    _extra_sans_env = os.environ.get("PACKA_MASTER_TLS_EXTRA_SANS")
    config.tls_extra_sans = (
        [s.strip() for s in _extra_sans_env.split(",") if s.strip()]
        if _extra_sans_env
        else _file_tls.get("extra_sans", [])
    )

    # --- PKI setup ---
    db2 = SessionLocal()
    try:
        ca_cert, ca_key = ensure_ca(db2)
        import socket as _socket
        advertise = config.advertise_host or (bind if bind != "0.0.0.0" else _socket.gethostname())
        sans = list({advertise, "localhost", *config.tls_extra_sans})
        server_cert, server_key = ensure_server_cert(db2, ca_cert, ca_key, sans=sans)
        if not config.tls.cert_pem:
            config.tls.cert_pem = server_cert
            config.tls.key_pem  = server_key
            config.tls.ca_pem   = ca_cert
        fp = get_ca_fingerprint(db2)
        if fp:
            print(f"[tls] CA fingerprint:   {fp}")
        if not get_token_info(db2):
            generate_token(db2)
            print(f"[tls] bootstrap token ready — retrieve it with: packa bootstrap-token --config <your.toml>")
    finally:
        db2.close()

    set_config(config)
    set_config_layers(args.config, cli_values)

    print(f"[master] bind: {bind}:{api_port}")
    print(f"[master] path_prefix: {config.path_prefix!r}")
    print(f"[master] tls: enabled")
    print(f"[master] config sources: "
          + ", ".join(f"{k}={v}" for k, v in sources.items() if v != "default"))

    asyncio.run(_main(bind=bind, api_port=api_port, tls=config.tls))


if __name__ == "__main__":
    main()
