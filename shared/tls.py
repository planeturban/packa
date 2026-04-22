"""TLS configuration and helpers for uvicorn servers and httpx clients."""
from __future__ import annotations

import ssl
from dataclasses import dataclass, field


@dataclass
class TlsConfig:
    disabled: bool = False   # explicit opt-out from auto mTLS
    # File-path overrides (manual / bring-your-own-cert)
    cert: str = ""
    key: str = ""
    ca: str = ""
    # In-memory PEM strings (loaded from DB — take priority over file paths)
    cert_pem: str = field(default="", repr=False)
    key_pem: str  = field(default="", repr=False)
    ca_pem: str   = field(default="", repr=False)

    @property
    def enabled(self) -> bool:
        if self.disabled:
            return False
        return bool(
            (self.cert_pem and self.key_pem and self.ca_pem)
            or (self.cert and self.key and self.ca)
        )

    def server_ssl_context(self) -> ssl.SSLContext:
        from .pki import make_server_ssl_context
        if self.cert_pem:
            return make_server_ssl_context(self.cert_pem, self.key_pem, self.ca_pem)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_verify_locations(cafile=self.ca)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_cert_chain(self.cert, self.key)
        return ctx

    def client_ssl_context(self) -> ssl.SSLContext:
        from .pki import make_client_ssl_context
        if self.cert_pem:
            return make_client_ssl_context(self.cert_pem, self.key_pem, self.ca_pem)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cafile=self.ca)
        ctx.load_cert_chain(self.cert, self.key)
        return ctx

    def uvicorn_tls_kwargs(self) -> dict:
        """Return keyword args to pass to uvicorn.Config for TLS."""
        if not self.enabled:
            return {}
        from .pki import write_tls_files
        if self.cert_pem:
            cp, kp, cap = write_tls_files(self.cert_pem, self.key_pem, self.ca_pem)
        else:
            cp, kp, cap = self.cert, self.key, self.ca
        return {
            "ssl_certfile": cp,
            "ssl_keyfile":  kp,
            "ssl_ca_certs": cap,
        }

    def httpx_kwargs(self) -> dict:
        """Return keyword args for httpx.AsyncClient."""
        if not self.enabled:
            return {}
        return {"verify": self.client_ssl_context()}


def scheme(tls: TlsConfig) -> str:
    return "https" if tls.enabled else "http"
