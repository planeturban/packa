"""
Slave entry point.

  Port 8000 (default) — HTTP/JSON API (receives metadata from master)

Configuration priority: config file < environment variables < CLI flags.

Environment variables:
  PACKA_SLAVE_BIND            Bind address
  PACKA_SLAVE_API_PORT        API port
  PACKA_SLAVE_ID              Slave ID (falls back to slave.db if unset)
  PACKA_SLAVE_PREFIX          Path prefix for incoming file paths
  PACKA_SLAVE_MASTER_HOST     Master hostname/IP
  PACKA_SLAVE_MASTER_PORT     Master API port
  PACKA_SLAVE_ADVERTISE_HOST  IP/hostname advertised to master
  PACKA_SLAVE_FFMPEG_BIN      Path to ffmpeg binary
  PACKA_SLAVE_FFMPEG_OUTPUT_DIR  Directory for converted files
  PACKA_SLAVE_FFMPEG_EXTRA_ARGS  Extra ffmpeg arguments
  PACKA_SLAVE_BATCH_SIZE      Jobs to claim per poll
  PACKA_SLAVE_POLL_INTERVAL   Seconds between poll attempts
  PACKA_SLAVE_TLS_CERT        Path to certificate
  PACKA_SLAVE_TLS_KEY         Path to private key
  PACKA_TLS_CA                Path to CA certificate (shared with master/web)

Flags:
  --bind            Address to bind the server ("any" → 0.0.0.0)
  --api-port        Metadata API port
  --master-host     Master hostname/IP
  --master-port     Master API port
  --advertise-host  IP/hostname to advertise to master. Auto-detected if omitted
  --config          Path to TOML config file

Usage:
  python -m slave.main --config packa.toml
  python -m slave.main --master-host 192.168.1.5 --bind any --config packa.toml
"""

import argparse
import asyncio
import builtins
from datetime import datetime
import socket

_orig_print = builtins.print
def _ts_print(*args, **kwargs):
    _orig_print(datetime.now().strftime('%H:%M:%S'), *args, **kwargs)
builtins.print = _ts_print

import uvicorn

from shared.config import load_slave
from shared.tls import UVICORN_LOG_CONFIG, uvicorn_kwargs

from .api import app, set_config, set_registration_params
from .identity import get_or_create_slave_id, get_stored_slave_id
from .settings import set_setting as _persist


def _detect_host() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())


async def _main(
    bind: str,
    api_port: int,
    advertise_host: str | None,
    slave_id: str,
    tls,
) -> None:
    effective_host = advertise_host or _detect_host()
    set_registration_params(effective_host, slave_id)

    uvi_config = uvicorn.Config(app, host=bind, port=api_port, log_level="info",
                                log_config=UVICORN_LOG_CONFIG, **uvicorn_kwargs(tls))
    await uvicorn.Server(uvi_config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa slave")
    parser.add_argument(
        "--bind", default=None,
        help='Address to bind the server ("any" → 0.0.0.0)',
    )
    parser.add_argument(
        "--api-port", type=int, default=None,
        help="Metadata API port",
    )
    parser.add_argument(
        "--master-host", default=None,
        help="Master hostname/IP to register with",
    )
    parser.add_argument(
        "--master-port", type=int, default=None,
        help="Master API port",
    )
    parser.add_argument(
        "--advertise-host", default=None,
        help="IP/hostname to advertise to master (auto-detected if omitted)",
    )
    parser.add_argument(
        "--config",
        help="Path to TOML config file",
    )
    args = parser.parse_args()

    config = load_slave(args.config)

    # CLI overrides config + env
    bind_raw = args.bind if args.bind is not None else config.bind
    bind = "0.0.0.0" if bind_raw == "any" else bind_raw
    api_port = args.api_port if args.api_port is not None else config.api_port
    if args.master_host is not None:
        config.master_host = args.master_host
    if args.master_port is not None:
        config.master_port = args.master_port
    advertise_host = (
        args.advertise_host if args.advertise_host is not None
        else config.advertise_host or None
    )

    set_config(config)

    db_id = get_stored_slave_id()
    is_new = db_id is None  # True only on the very first startup (no slave_id in DB yet)

    if config.slave_id:
        if db_id and db_id != config.slave_id:
            print(f"[slave] id from config: {config.slave_id!r} (db has a different id: {db_id!r})")
        elif db_id:
            print(f"[slave] id from config: {config.slave_id!r} (matches db)")
        slave_id = config.slave_id
    else:
        slave_id = get_or_create_slave_id()
        source = "db" if db_id else "generated"
        print(f"[slave] id {source}: {slave_id!r}")

    # Always persist the resolved slave_id so subsequent restarts are not treated as new.
    _persist("slave_id", slave_id)
    # Mark genuinely new slaves so the lifespan can start them in unconfigured mode.
    if is_new:
        _persist("first_run", "true")

    print(f"[slave] bind: {bind}:{api_port}")
    print(f"[slave] path_prefix: {config.path_prefix!r}")
    print(f"[slave] tls: {'enabled' if config.tls.enabled else 'disabled'}")

    asyncio.run(_main(
        bind=bind,
        api_port=api_port,
        advertise_host=advertise_host,
        slave_id=slave_id,
        tls=config.tls,
    ))


if __name__ == "__main__":
    main()
