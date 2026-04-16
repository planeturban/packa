"""
Web frontend entry point.

  Port 8080 (default) — browser-facing HTTP(S)

Configuration priority: config file < environment variables < CLI flags.

Environment variables:
  PACKA_WEB_BIND         Bind address
  PACKA_WEB_PORT         Port
  PACKA_WEB_USERNAME     Login username
  PACKA_WEB_PASSWORD     Login password
  PACKA_WEB_SECRET_KEY   Session signing secret
  PACKA_WEB_MASTER_HOST  Master hostname/IP
  PACKA_WEB_MASTER_PORT  Master API port
  PACKA_WEB_TLS_CERT     Path to certificate
  PACKA_WEB_TLS_KEY      Path to private key
  PACKA_TLS_CA           Path to CA certificate (shared with master/slave)

Flags:
  --bind         Address to bind ("any" → 0.0.0.0)
  --port         Port
  --master-host  Master hostname/IP
  --master-port  Master API port
  --config       Path to TOML config file

Usage:
  python -m web.main --config packa.toml
  python -m web.main --master-host 192.168.1.5 --bind any --config packa.toml
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

from shared.tls import UVICORN_LOG_CONFIG, uvicorn_server_kwargs

from .app import app, set_config
from .config import WebConfig, load_web


async def _main(bind: str, port: int, config: WebConfig) -> None:
    uvi_config = uvicorn.Config(
        app,
        host=bind,
        port=port,
        log_level="info",
        log_config=UVICORN_LOG_CONFIG,
        **uvicorn_server_kwargs(config.tls),
    )
    await uvicorn.Server(uvi_config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa web frontend")
    parser.add_argument(
        "--bind", default=None,
        help='Address to bind ("any" → 0.0.0.0)',
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port",
    )
    parser.add_argument(
        "--master-host", default=None,
        help="Master hostname/IP",
    )
    parser.add_argument(
        "--master-port", type=int, default=None,
        help="Master API port",
    )
    parser.add_argument(
        "--config",
        help="Path to TOML config file",
    )
    args = parser.parse_args()

    config = load_web(args.config)

    # CLI overrides config + env
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
    print(f"[web] tls (backend): {'enabled' if config.tls.enabled else 'disabled'}")
    print(f"[web] tls (browser): {'enabled' if config.tls.cert and config.tls.key else 'disabled'}")

    asyncio.run(_main(bind=bind, port=config.port, config=config))


if __name__ == "__main__":
    main()
