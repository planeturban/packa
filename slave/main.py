"""
Slave entry point.

  Port 8000 (default) — HTTP/JSON API (receives metadata from master)

Flags:
  --bind            Address to bind the server (default: localhost; "any" → 0.0.0.0)
  --api-port        Metadata API port (default: 8000)
  --master-host     Master hostname/IP (default: localhost)
  --master-port     Master API port (default: 9000)
  --advertise-host  IP/hostname to advertise to master. Auto-detected if omitted
  --config          Path to TOML config file

Usage:
  python -m slave.main --config packa.toml
  python -m slave.main --master-host 192.168.1.5 --bind any --config packa.toml
"""

import argparse
import asyncio
import socket

import httpx
import uvicorn

from shared.config import Config, load_slave

from .api import app, set_config
from .state import worker_state


def _detect_host() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())


def _register_with_master(
    master_host: str,
    master_port: int,
    config_id: str,
    advertise_host: str,
    api_port: int,
) -> dict:
    url = f"http://{master_host}:{master_port}/slaves"
    payload = {"config_id": config_id, "host": advertise_host, "api_port": api_port, "file_port": 0}
    with httpx.Client(timeout=10) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def _main(
    bind: str,
    api_port: int,
    master_host: str,
    master_port: int,
    advertise_host: str | None,
    slave_id: str,
) -> None:
    effective_host = advertise_host or _detect_host()
    print(f"[slave] registering with master at {master_host}:{master_port}")
    try:
        record = _register_with_master(master_host, master_port, slave_id, effective_host, api_port)
        worker_state.slave_id = record["id"]
        worker_state.slave_config_id = slave_id
        worker_state.master_url = f"http://{master_host}:{master_port}"
        print(f"[slave] registered as slave-{record['id']}")
    except Exception as exc:
        print(f"[slave] warning: could not register with master: {exc}")
        print("[slave] starting in standalone mode")

    config = uvicorn.Config(app, host=bind, port=api_port, log_level="info")
    await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Packa slave")
    parser.add_argument(
        "--bind", default="localhost",
        help='Address to bind the server (default: localhost; use "any" for 0.0.0.0)',
    )
    parser.add_argument(
        "--api-port", type=int, default=8000,
        help="Metadata API port (default: 8000)",
    )
    parser.add_argument(
        "--master-host", default="localhost",
        help="Master hostname/IP to register with (default: localhost)",
    )
    parser.add_argument(
        "--master-port", type=int, default=9000,
        help="Master API port (default: 9000)",
    )
    parser.add_argument(
        "--advertise-host",
        help="IP/hostname to advertise to master (auto-detected if omitted)",
    )
    parser.add_argument(
        "--config",
        help="Path to JSON config file",
    )
    args = parser.parse_args()
    bind = "0.0.0.0" if args.bind == "any" else args.bind

    config = load_slave(args.config) if args.config else Config()
    set_config(config)
    print(f"[slave] id: {config.slave_id!r}")
    print(f"[slave] path_prefix: {config.path_prefix!r}")

    asyncio.run(_main(
        bind=bind,
        api_port=args.api_port,
        master_host=args.master_host,
        master_port=args.master_port,
        advertise_host=args.advertise_host,
        slave_id=config.slave_id,
    ))


if __name__ == "__main__":
    main()
