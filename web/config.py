import os
import tomllib
from dataclasses import dataclass, field

from shared.config import TlsConfig, _load_tls


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val is not None else default


@dataclass
class WebConfig:
    username: str = "admin"
    password: str = ""
    secret_key: str = ""
    master_host: str = "localhost"
    master_port: int = 9000
    bind: str = "localhost"
    port: int = 8080
    tls: TlsConfig = field(default_factory=TlsConfig)


def load_web(config_path: str | None) -> WebConfig:
    data: dict = {}
    if config_path:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    web = data.get("web", {})
    shared_tls = data.get("tls", {})
    web_tls = web.get("tls", {})

    return WebConfig(
        username=_env("PACKA_WEB_USERNAME", web.get("username", "admin")),
        password=_env("PACKA_WEB_PASSWORD", web.get("password", "")),
        secret_key=_env("PACKA_WEB_SECRET_KEY", web.get("secret_key", "")),
        master_host=_env("PACKA_WEB_MASTER_HOST", web.get("master_host", "localhost")),
        master_port=_env_int("PACKA_WEB_MASTER_PORT", web.get("master_port", 9000)),
        bind=_env("PACKA_WEB_BIND", web.get("bind", "localhost")),
        port=_env_int("PACKA_WEB_PORT", web.get("port", 8080)),
        tls=_load_tls(shared_tls, web_tls),
    )
