"""PKI utilities — CA and certificate generation using the cryptography library."""
from __future__ import annotations

import contextlib
import datetime
import ipaddress
import os
import ssl
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_CA_DAYS       = 3650   # 10 years
_CERT_DAYS     = 365    # 1 year
_RENEW_DAYS    = 30     # renew node cert when < 30 days remaining
_CA_RENEW_DAYS = 90     # renew CA when < 90 days remaining
_KEY_SIZE      = 2048


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=_KEY_SIZE)


def _key_pem(key) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()


def _cert_pem(cert) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def generate_ca() -> tuple[str, str]:
    """Generate a self-signed CA. Returns (cert_pem, key_pem)."""
    key = _gen_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Packa CA")])
    now = _utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=_CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return _cert_pem(cert), _key_pem(key)


def generate_cert(
    ca_cert_pem: str,
    ca_key_pem: str,
    cn: str,
    sans: list[str] | None = None,
    days: int = _CERT_DAYS,
) -> tuple[str, str]:
    """Sign a new cert with the CA. Returns (cert_pem, key_pem)."""
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode())
    ca_key  = serialization.load_pem_private_key(ca_key_pem.encode(), password=None)
    key     = _gen_key()
    name    = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now     = _utcnow()

    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    if sans:
        san_list = []
        for s in sans:
            try:
                san_list.append(x509.IPAddress(ipaddress.ip_address(s)))
            except ValueError:
                san_list.append(x509.DNSName(s))
        builder = builder.add_extension(x509.SubjectAlternativeName(san_list), critical=False)

    cert = builder.sign(ca_key, hashes.SHA256())
    return _cert_pem(cert), _key_pem(key)


def cert_expiry(cert_pem: str) -> datetime.datetime:
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    return cert.not_valid_after_utc


def needs_renewal(cert_pem: str, threshold_days: int = _RENEW_DAYS) -> bool:
    try:
        return cert_expiry(cert_pem) - _utcnow() < datetime.timedelta(days=threshold_days)
    except Exception:
        return True


def cert_fingerprint(cert_pem: str) -> str:
    """Return SHA-256 fingerprint as colon-separated hex pairs."""
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    fp = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(fp[i:i+2] for i in range(0, len(fp), 2))


@contextlib.contextmanager
def _tmp_cert_files(cert_pem: str, key_pem: str):
    """Context manager that writes cert+key to temp files, yields (cert_path, key_path)."""
    cf = kf = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as f:
            f.write(cert_pem.encode())
            cf = f.name
        os.chmod(cf, 0o600)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as f:
            f.write(key_pem.encode())
            kf = f.name
        os.chmod(kf, 0o600)
        yield cf, kf
    finally:
        for p in (cf, kf):
            if p and os.path.exists(p):
                os.unlink(p)



def make_client_ssl_context(cert_pem: str, key_pem: str, ca_cert_pem: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=ca_cert_pem)
    with _tmp_cert_files(cert_pem, key_pem) as (cp, kp):
        ctx.load_cert_chain(cp, kp)
    return ctx


def write_tls_files(cert_pem: str, key_pem: str, ca_pem: str, prefix: str = "node") -> tuple[str, str, str]:
    """Write PEM data to unpredictable temp files. Returns (cert_path, key_path, ca_path).
    Files persist for the process lifetime and are removed on clean exit."""
    import atexit
    paths = []
    for data in (cert_pem, key_pem, ca_pem):
        fd, path = tempfile.mkstemp(prefix=f"packa_{prefix}_", suffix=".pem")
        try:
            os.write(fd, data.encode())
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
        paths.append(path)
        atexit.register(lambda p=path: os.unlink(p) if os.path.exists(p) else None)
    return paths[0], paths[1], paths[2]
