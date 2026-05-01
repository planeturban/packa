"""
Web frontend entry point.

Configuration priority: config file < environment variables < CLI flags.

Environment variables:
  PACKA_WEB_BIND              Bind address
  PACKA_WEB_PORT              Port
  PACKA_WEB_USERNAME          Login username
  PACKA_WEB_PASSWORD          Login password
  PACKA_WEB_SECRET_KEY        Session signing secret
  PACKA_WEB_MASTER_HOST       Master hostname/IP
  PACKA_WEB_MASTER_PORT       Master API port
  PACKA_WEB_BOOTSTRAP_TOKEN   One-time token to obtain a TLS cert from master

Flags:
  --bind             Address to bind ("any" → 0.0.0.0)
  --port             Port
  --master-host      Master hostname/IP
  --master-port      Master API port
  --bootstrap-token  One-time token to obtain a TLS cert from master on first run
  --config           Path to TOML config file

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

import secrets

import httpx
import uvicorn

from shared.config import WebConfig, load_web
from shared.log import UVICORN_LOG_CONFIG

from .app import app, set_config
from .store import get_setting, set_setting


def _bootstrap_tls(config: WebConfig) -> None:
    """Load stored TLS certs or fetch from master using bootstrap_token."""
    cert_pem = get_setting("tls.cert")
    key_pem  = get_setting("tls.key")
    ca_pem   = get_setting("tls.ca")

    if cert_pem and key_pem and ca_pem:
        config.tls.cert_pem = cert_pem
        config.tls.key_pem  = key_pem
        config.tls.ca_pem   = ca_pem
        print("[web] TLS certs loaded from store")
        return

    if not config.bootstrap_token:
        return

    # Retry up to 5 times to handle transient startup timing issues.
    r = None
    for attempt in range(5):
        if attempt:
            import time as _time
            _time.sleep(3)
        try:
            r = httpx.post(
                f"https://{config.master_host}:{config.master_port}/bootstrap",
                json={"token": config.bootstrap_token, "cn": "web"},
                verify=False,  # TOFU — master cert not yet trusted
                timeout=10,
            )
            r.raise_for_status()
            break
        except Exception:
            r = None
    if r is None:
        print("[web] TLS bootstrap failed: could not reach master")
        return
    try:
        bundle = r.json()
        cert_pem = bundle["cert_pem"]
        key_pem  = bundle["key_pem"]
        ca_pem   = bundle["ca_pem"]
        set_setting("tls.cert", cert_pem)
        set_setting("tls.key",  key_pem)
        set_setting("tls.ca",   ca_pem)
        config.tls.cert_pem = cert_pem
        config.tls.key_pem  = key_pem
        config.tls.ca_pem   = ca_pem
        print("[web] TLS bootstrap successful")
    except Exception as exc:
        print(f"[web] TLS bootstrap failed: {exc}")


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
    parser.add_argument("--bootstrap-token", default=None,
                        help="One-time token to obtain a TLS cert from master on first run")
    parser.add_argument("--insecure-no-auth", action="store_true",
                        help="Allow binding to a non-loopback address without credentials (unsafe)")
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
    if args.bootstrap_token is not None:
        config.bootstrap_token = args.bootstrap_token

    bind = "0.0.0.0" if config.bind == "any" else config.bind

    _bootstrap_tls(config)

    # Load stored credentials (set via UI); override config/env values if present.
    stored_username = get_setting("auth.username")
    stored_password = get_setting("auth.password")
    if stored_username is not None:
        config.username = stored_username
    if stored_password is not None:
        if stored_password and not stored_password.startswith("$argon2"):
            from argon2 import PasswordHasher
            hashed = PasswordHasher().hash(stored_password)
            set_setting("auth.password", hashed)
            stored_password = hashed
            print("[web] migrated plaintext password to argon2 hash")
        config.password = stored_password

    # Persist secret_key so sessions survive restarts; env/config override takes priority.
    if not config.secret_key:
        stored_key = get_setting("secret_key")
        if stored_key:
            config.secret_key = stored_key
        else:
            config.secret_key = secrets.token_hex(32)
            set_setting("secret_key", config.secret_key)
            print("[web] generated new secret_key")

    set_config(config)

    print(f"[web] bind: {bind}:{config.port}")
    print(f"[web] master: {config.master_host}:{config.master_port}")
    print(f"[web] tls: {'bootstrapped' if config.tls.enabled else 'pending bootstrap'}")

    _loopback = {"127.0.0.1", "::1", "localhost"}
    if not (config.username and config.password) and bind not in _loopback:
        if args.insecure_no_auth:
            print("[web] WARNING: authentication is disabled on a non-loopback address — unsafe, use only for testing")
        else:
            print("[web] FATAL: refusing to bind to a non-loopback address without credentials. "
                  "Set [web].username and [web].password, or pass --insecure-no-auth to override.")
            import sys; sys.exit(1)
    elif not (config.username and config.password):
        print("[web] WARNING: authentication is disabled — the dashboard is accessible without login")

    asyncio.run(_main(bind=bind, port=config.port))


if __name__ == "__main__":
    main()
