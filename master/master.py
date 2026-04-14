"""
Master entry point.

  Port 9000 (default) — REST API for slave registration and metadata transfer.

Flags:
  --bind       Address to bind the API server (default: 0.0.0.0)
  --api-port   Port for the API (default: 9000)
  --config     Path to JSON config file

Config file format (JSON):
  {
    "path_prefix": "/mnt/data/"
  }

Usage:
  python -m master.master --config /etc/packa/master.json
  python -m master.master --bind 0.0.0.0 --api-port 9000
"""

import argparse
import asyncio

import uvicorn

from shared.config import Config, load as load_config

from .api import app, set_config


async def _main(bind: str, api_port: int) -> None:
    config = uvicorn.Config(app, host=bind, port=api_port, log_level="info")
    await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa master")
    parser.add_argument(
        "--bind", default="0.0.0.0",
        help="Address to bind the API server (default: 0.0.0.0)",
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

    config = load_config(args.config) if args.config else Config()
    set_config(config)
    print(f"[master] path_prefix: {config.path_prefix!r}")

    asyncio.run(_main(bind=args.bind, api_port=args.api_port))


if __name__ == "__main__":
    main()
