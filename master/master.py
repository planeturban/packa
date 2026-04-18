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
from datetime import datetime

_orig_print = builtins.print
def _ts_print(*args, **kwargs):
    _orig_print(datetime.now().strftime('%H:%M:%S'), *args, **kwargs)
builtins.print = _ts_print

import uvicorn

from shared.config import load_master
from shared.log import UVICORN_LOG_CONFIG

from .api import app, set_config


async def _main(bind: str, api_port: int) -> None:
    uvi_config = uvicorn.Config(app, host=bind, port=api_port, log_level="info",
                                log_config=UVICORN_LOG_CONFIG)
    await uvicorn.Server(uvi_config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa master")
    parser.add_argument("--bind", default=None,
                        help='Address to bind the API server ("any" → 0.0.0.0)')
    parser.add_argument("--api-port", type=int, default=None, help="API port")
    parser.add_argument("--config", help="Path to TOML config file")
    args = parser.parse_args()

    config = load_master(args.config)
    set_config(config)

    bind_raw = args.bind if args.bind is not None else config.bind
    bind = "0.0.0.0" if bind_raw == "any" else bind_raw
    api_port = args.api_port if args.api_port is not None else config.api_port

    print(f"[master] bind: {bind}:{api_port}")
    print(f"[master] path_prefix: {config.path_prefix!r}")

    asyncio.run(_main(bind=bind, api_port=api_port))


if __name__ == "__main__":
    main()
