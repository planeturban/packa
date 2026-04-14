"""
TLS helpers shared by master and slave.
"""

import ssl

from .config import TlsConfig


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
