"""TLS configuration and helpers for uvicorn servers and httpx clients."""
from __future__ import annotations

import ssl
from dataclasses import dataclass, field


@dataclass
class TlsConfig:
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
        return bool(
            (self.cert_pem and self.key_pem and self.ca_pem)
            or (self.cert and self.key and self.ca)
        )

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

    def uvicorn_tls_kwargs(self, require_client_cert: bool = True) -> dict:
        """Return keyword args to pass to uvicorn.Config for TLS.

        require_client_cert=False is used by master, which must stay reachable
        during bootstrap before nodes have obtained their client certificates.
        Workers use the default True so only CA-signed clients can connect.
        """
        if not self.enabled:
            return {}
        from .pki import write_tls_files
        if self.cert_pem:
            cp, kp, cap = write_tls_files(self.cert_pem, self.key_pem, self.ca_pem)
        else:
            cp, kp, cap = self.cert, self.key, self.ca
        kwargs = {
            "ssl_certfile": cp,
            "ssl_keyfile":  kp,
            "ssl_ca_certs": cap,
        }
        if require_client_cert:
            kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED
        else:
            kwargs["ssl_cert_reqs"] = ssl.CERT_OPTIONAL
        return kwargs

    def httpx_kwargs(self) -> dict:
        """Return keyword args for httpx.AsyncClient."""
        if not self.enabled:
            return {}
        return {"verify": self.client_ssl_context()}
