"""
TLS management for master: CA lifecycle, cert issuance, bootstrap tokens.

All state is persisted in master_settings under tls.* keys.
"""
from __future__ import annotations

import datetime
import secrets

from sqlalchemy.orm import Session

from shared.pki import (
    _CA_RENEW_DAYS,
    cert_fingerprint, generate_ca, generate_cert, needs_renewal,
)

from .settings import MasterSetting

_KEY_CA_CERT    = "tls.ca_cert"
_KEY_CA_KEY     = "tls.ca_key"
_KEY_CERT       = "tls.server_cert"
_KEY_KEY        = "tls.server_key"
_KEY_TOKEN      = "tls.bootstrap_token"
_KEY_TOKEN_EXP  = "tls.bootstrap_token_expires"

TOKEN_TTL_MINUTES = 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(db: Session, key: str) -> str | None:
    row = db.query(MasterSetting).filter_by(key=key).first()
    return row.value if row else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(MasterSetting).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.add(MasterSetting(key=key, value=value))
    db.commit()


# ---------------------------------------------------------------------------
# CA and server cert
# ---------------------------------------------------------------------------

def ensure_ca(db: Session) -> tuple[str, str]:
    """Ensure CA exists and is not expiring soon. Returns (ca_cert_pem, ca_key_pem)."""
    ca_cert = _get(db, _KEY_CA_CERT)
    ca_key  = _get(db, _KEY_CA_KEY)
    if ca_cert and ca_key and not needs_renewal(ca_cert, _CA_RENEW_DAYS):
        return ca_cert, ca_key
    print("[tls] generating CA")
    ca_cert, ca_key = generate_ca()
    _set(db, _KEY_CA_CERT, ca_cert)
    _set(db, _KEY_CA_KEY,  ca_key)
    return ca_cert, ca_key


def ensure_server_cert(
    db: Session,
    ca_cert_pem: str,
    ca_key_pem: str,
    sans: list[str] | None = None,
) -> tuple[str, str]:
    """Ensure server cert exists and is valid. Returns (cert_pem, key_pem)."""
    cert = _get(db, _KEY_CERT)
    key  = _get(db, _KEY_KEY)
    if cert and key and not needs_renewal(cert):
        return cert, key
    print("[tls] generating server certificate")
    cert, key = generate_cert(ca_cert_pem, ca_key_pem, "master", sans=sans, purpose="server")
    _set(db, _KEY_CERT, cert)
    _set(db, _KEY_KEY,  key)
    return cert, key


def get_ca_cert(db: Session) -> str | None:
    return _get(db, _KEY_CA_CERT)


def get_ca_fingerprint(db: Session) -> str | None:
    ca = get_ca_cert(db)
    return cert_fingerprint(ca) if ca else None


# ---------------------------------------------------------------------------
# Client cert issuance and renewal
# ---------------------------------------------------------------------------

def issue_client_cert(db: Session, cn: str, sans: list[str] | None = None) -> tuple[str, str, str]:
    """Issue a client cert signed by the CA. Returns (cert_pem, key_pem, ca_cert_pem)."""
    ca_cert_pem, ca_key_pem = ensure_ca(db)
    # Workers act as both TLS server (accepting connections from web) and client
    # (connecting to master). Web is client-only to master/workers.
    purpose = "both" if cn == "worker" else "client"
    cert_pem, key_pem = generate_cert(ca_cert_pem, ca_key_pem, cn, sans=sans, purpose=purpose)
    return cert_pem, key_pem, ca_cert_pem



# ---------------------------------------------------------------------------
# Bootstrap tokens
# ---------------------------------------------------------------------------

def generate_token(db: Session) -> str:
    """Generate a fresh one-use bootstrap token (10-minute TTL)."""
    token   = secrets.token_urlsafe(24)
    expires = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=TOKEN_TTL_MINUTES)
    ).isoformat()
    _set(db, _KEY_TOKEN,     token)
    _set(db, _KEY_TOKEN_EXP, expires)
    return token


def get_token_info(db: Session) -> dict | None:
    """Return {token, expires_at} if a valid token exists, else None."""
    token   = _get(db, _KEY_TOKEN)
    expires = _get(db, _KEY_TOKEN_EXP)
    if not token or not expires:
        return None
    exp_dt = datetime.datetime.fromisoformat(expires)
    if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
        return None
    return {"token": token, "expires_at": expires}


def consume_token(db: Session, token: str) -> bool:
    """Validate and consume the token (single-use). Returns True if valid."""
    info = get_token_info(db)
    if not info:
        return False
    if not secrets.compare_digest(info["token"], token):
        return False
    # Invalidate immediately so the token cannot be reused
    db.query(MasterSetting).filter(
        MasterSetting.key.in_([_KEY_TOKEN, _KEY_TOKEN_EXP])
    ).delete(synchronize_session=False)
    db.commit()
    return True
