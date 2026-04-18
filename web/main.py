"""
Web frontend entry point.

Configuration priority: config file < environment variables < CLI flags.

Environment variables:
  PACKA_WEB_BIND         Bind address
  PACKA_WEB_PORT         Port
  PACKA_WEB_USERNAME     Login username
  PACKA_WEB_PASSWORD     Login password
  PACKA_WEB_SECRET_KEY   Session signing secret
  PACKA_WEB_MASTER_HOST  Master hostname/IP
  PACKA_WEB_MASTER_PORT  Master API port

Flags:
  --bind         Address to bind ("any" → 0.0.0.0)
  --port         Port
  --master-host  Master hostname/IP
  --master-port  Master API port
  --config       Path to TOML config file

Usage:
  python -m web.main --config packa.toml
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

from shared.config import WebConfig, load_web
from shared.tls import UVICORN_LOG_CONFIG

from .app import app, set_config


async def _main(bind: str, port: int) -> None:
    uvi_config = uvicorn.Config(app, host=bind, port=port, log_level="info",
                                log_config=UVICORN_LOG_CONFIG)
    await uvicorn.Server(uvi_config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa web frontend")
    parser.add_argument("--bind", default=None, help='Address to bind ("any" → 0.0.0.0)')
    parser.add_argument("--port", type=int, default=None, help="Port")
    parser.add_argument("--master-host", default=None, help="Master hostname/IP")
    parser.add_argument("--master-port", type=int, default=None, help="Master API port")
    parser.add_argument("--config", help="Path to TOML config file")
    args = parser.parse_args()

    config = load_web(args.config)

    if args.bind is not None:
        config.bind = args.bind
    if args.port is not None:
        config.port = args.port
    if args.master_host is not None:
        config.master_host = args.master_host
    if args.master_port is not None:
        config.master_port = args.master_port

    bind = "0.0.0.0" if config.bind == "any" else config.bind

    set_config(config)

    print(f"[web] bind: {bind}:{config.port}")
    print(f"[web] master: {config.master_host}:{config.master_port}")

    asyncio.run(_main(bind=bind, port=config.port))


if __name__ == "__main__":
    main()
