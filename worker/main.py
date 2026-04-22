"""
Worker entry point.

Configuration priority: config file < environment variables < CLI flags.

Environment variables:
  PACKA_WORKER_BIND            Bind address
  PACKA_WORKER_API_PORT        API port
  PACKA_WORKER_ID              Worker ID (falls back to worker.db if unset)
  PACKA_WORKER_PREFIX          Path prefix for incoming file paths
  PACKA_WORKER_MASTER_HOST     Master hostname/IP
  PACKA_WORKER_MASTER_PORT     Master API port
  PACKA_WORKER_ADVERTISE_HOST  IP/hostname advertised to master
  PACKA_WORKER_FFMPEG_BIN      Path to ffmpeg binary
  PACKA_WORKER_FFMPEG_OUTPUT_DIR  Directory for converted files
  PACKA_WORKER_FFMPEG_EXTRA_ARGS  Extra ffmpeg arguments
  PACKA_WORKER_BATCH_SIZE      Jobs to claim per poll
  PACKA_WORKER_POLL_INTERVAL   Seconds between poll attempts

Flags:
  --bind            Address to bind the server ("any" → 0.0.0.0)
  --api-port        Metadata API port
  --master-host     Master hostname/IP
  --master-port     Master API port
  --advertise-host  IP/hostname to advertise to master (auto-detected if omitted)
  --config          Path to TOML config file

Usage:
  python -m worker.main --config packa.toml
"""

import argparse
import asyncio
import builtins
import socket
from datetime import datetime

_orig_print = builtins.print
def _ts_print(*args, **kwargs):
    _orig_print(datetime.now().strftime('%H:%M:%S'), *args, **kwargs)
builtins.print = _ts_print

import uvicorn

from shared.config import load_worker
from shared.log import UVICORN_LOG_CONFIG

from . import config_store
from .api import app, set_config, set_config_layers, set_registration_params
from .store import get_stored_worker_id, set_setting


def _detect_host() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())


async def _main(bind: str, api_port: int, advertise_host: str | None, worker_id: str) -> None:
    if advertise_host:
        effective_host = advertise_host
    elif bind == "0.0.0.0":
        effective_host = _detect_host()
    else:
        effective_host = bind
    set_registration_params(effective_host, worker_id)
    uvi_config = uvicorn.Config(app, host=bind, port=api_port, log_level="info",
                                log_config=UVICORN_LOG_CONFIG)
    await uvicorn.Server(uvi_config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa worker")
    parser.add_argument("--bind", default=None,
                        help='Address to bind the server ("any" → 0.0.0.0)')
    parser.add_argument("--api-port", type=int, default=None, help="Metadata API port")
    parser.add_argument("--master-host", default=None, help="Master hostname/IP")
    parser.add_argument("--master-port", type=int, default=None, help="Master API port")
    parser.add_argument("--advertise-host", default=None,
                        help="IP/hostname to advertise to master (auto-detected if omitted)")
    parser.add_argument("--config", help="Path to TOML config file")
    args = parser.parse_args()

    config = load_worker(args.config)

    # CLI overrides for config_store layer tracking (network identity fields excluded)
    cli_values: dict = {}
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

    # Seed/load worker config store (DB layer)
    file_values = config_store.read_file_values(args.config)
    env_values = config_store.read_env_values()
    if not config_store.is_initialized():
        config_store.initialize_from_layers(file_values, env_values)
        print("[worker] config store initialized")
    db_values = config_store.read_db_values()
    effective, _ = config_store.compute_effective(file_values, env_values, db_values, cli_values)
    config_store.apply_to_config(effective, config)

    set_config(config)
    set_config_layers(args.config, cli_values)

    db_id = get_stored_worker_id()
    is_new = db_id is None

    if config.worker_id:
        if db_id and db_id != config.worker_id:
            print(f"[worker] id from config: {config.worker_id!r} (db has a different id: {db_id!r})")
        elif db_id:
            print(f"[worker] id from config: {config.worker_id!r} (matches db)")
        worker_id = config.worker_id
        set_setting("worker_id", worker_id)
    elif db_id:
        worker_id = db_id
        print(f"[worker] id from db: {worker_id!r}")
    else:
        worker_id = ""
        print("[worker] no id configured — will be assigned by master on registration")

    if is_new:
        set_setting("first_run", "true")

    print(f"[worker] bind: {bind}:{api_port}")
    print(f"[worker] path_prefix: {config.path_prefix!r}")

    asyncio.run(_main(
        bind=bind,
        api_port=api_port,
        advertise_host=advertise_host,
        worker_id=worker_id,
    ))


if __name__ == "__main__":
    main()
