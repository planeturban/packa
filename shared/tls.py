"""
TLS helpers shared by master and slave.
"""

import ssl

from .config import TlsConfig

# Uvicorn log config that prepends HH:MM:SS to every log line.
UVICORN_LOG_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s %(levelprefix)s %(message)s",
            "datefmt": "%H:%M:%S",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn":        {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error":  {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["access"],  "level": "INFO", "propagate": False},
    },
}


def scheme(tls: TlsConfig) -> str:
    return "https" if tls.enabled else "http"


def httpx_kwargs(tls: TlsConfig) -> dict:
    """Return kwargs to pass to httpx.Client / AsyncClient for mTLS, or {} for plain HTTP."""
    if tls.enabled:
        return {"verify": tls.ca, "cert": (tls.cert, tls.key)}
    return {}


def uvicorn_kwargs(tls: TlsConfig) -> dict:
    """Return kwargs to pass to uvicorn.Config to enable TLS + mandatory client cert."""
    if not tls.enabled:
        return {}
    return {
        "ssl_certfile": tls.cert,
        "ssl_keyfile": tls.key,
        "ssl_ca_certs": tls.ca,
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }


def uvicorn_server_kwargs(tls: TlsConfig) -> dict:
    """Like uvicorn_kwargs but without ssl_cert_reqs — for browser-facing servers."""
    if not tls.enabled:
        return {}
    return {
        "ssl_certfile": tls.cert,
        "ssl_keyfile": tls.key,
        "ssl_ca_certs": tls.ca,
    }
