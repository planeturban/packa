"""
Master entry point.

  Port 9000 (default) — REST API for slave registration and job distribution.

Flags:
  --bind       Address to bind the API server (default: localhost; "any" → 0.0.0.0)
  --api-port   Port for the API (default: 9000)
  --config     Path to TOML config file

Usage:
  python -m master.master --config packa.toml
  python -m master.master --bind any --config packa.toml
"""

import argparse
import asyncio

import uvicorn

from shared.config import Config, load_master
from shared.tls import uvicorn_kwargs

from .api import app, set_config


async def _main(bind: str, api_port: int, config: Config) -> None:
    uvi_config = uvicorn.Config(app, host=bind, port=api_port, log_level="info",
                                **uvicorn_kwargs(config.tls))
    await uvicorn.Server(uvi_config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa master")
    parser.add_argument(
        "--bind", default="localhost",
        help='Address to bind the API server (default: localhost; use "any" for 0.0.0.0)',
    )
    parser.add_argument(
        "--api-port", type=int, default=9000,
        help="API port (default: 9000)",
    )
    parser.add_argument(
        "--config",
        help="Path to JSON config file",
    )
    args = parser.parse_args()
    bind = "0.0.0.0" if args.bind == "any" else args.bind

    config = load_master(args.config) if args.config else Config()
    set_config(config)
    print(f"[master] path_prefix: {config.path_prefix!r}")
    print(f"[master] tls: {'enabled' if config.tls.enabled else 'disabled'}")

    asyncio.run(_main(bind=bind, api_port=args.api_port, config=config))


if __name__ == "__main__":
    main()
