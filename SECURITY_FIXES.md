# Security fixes for Packa

This document is a work order for an AI coding agent. Each item is a concrete code change with the file paths, the broken behaviour, the desired behaviour, and a verification step. Work top-to-bottom — earlier fixes (1, 2, 3) are prerequisites for the system to be safe outside loopback, and #6 modifies code touched by #1.

Test after each fix. Don't batch.

---

## 1. Master must request client certificates (HIGH)

**Files:** `master/master.py`, `shared/tls.py`, `master/api.py`

**Problem.** `master/master.py:46` calls `tls.uvicorn_tls_kwargs(require_client_cert=False)`. When `ssl_cert_reqs` is omitted from `uvicorn.Config`, uvicorn defaults to `ssl.CERT_NONE` — the TLS handshake never asks the client for a certificate. Consequently `_peer_cn(request)` always returns `None` for remote callers, and every guard on the master (`_require_web_cert`, `_require_worker_cert`) hits the `if cn is None: return  # non-TLS deployment — no cert enforcement` branch. `/tls/token`, `/restart`, `/master/config/*`, `/files/bulk-delete`, `/scan/start`, every `_require_web_cert`-guarded endpoint, is reachable from any TLS client.

**Fix.**

1. In `shared/tls.py`, change `uvicorn_tls_kwargs` so the `require_client_cert=False` path emits `ssl.CERT_OPTIONAL`, not nothing:
   ```python
   if require_client_cert:
       kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED
   else:
       kwargs["ssl_cert_reqs"] = ssl.CERT_OPTIONAL
   ```
   Rationale: `/bootstrap` must remain reachable to clients that don't yet have a cert, so we can't go full `CERT_REQUIRED` on master. `CERT_OPTIONAL` requests the cert and validates it if presented, while still completing the handshake without one.

2. In `master/api.py`, update `_require_web_cert` and `_require_worker_cert` so a missing cert outside loopback is a 403, not an exemption. The current "non-TLS deployment" branch was a workaround for the bug above; it must go.

   New `_require_web_cert`:
   ```python
   def _require_web_cert(request: Request) -> None:
       host = request.client.host if request.client else ""
       if host in ("127.0.0.1", "::1"):
           return
       cn = _peer_cn(request)
       if cn is None:
           raise HTTPException(status_code=403, detail="Client certificate required")
       if cn != "web":
           raise HTTPException(status_code=403, detail="Web certificate required")
   ```

   New `_require_worker_cert`:
   ```python
   def _require_worker_cert(request: Request) -> None:
       host = request.client.host if request.client else ""
       if host in ("127.0.0.1", "::1"):
           return
       cn = _peer_cn(request)
       if cn is None:
           raise HTTPException(status_code=403, detail="Client certificate required")
       if cn == "web":
           raise HTTPException(status_code=403, detail="Worker certificate required")
   ```

3. Apply the same change to the identical helpers in `worker/api.py` (lines ~557 and ~548). On worker the impact is smaller (uvicorn already runs `CERT_REQUIRED` so an unauthenticated TLS connection can't reach the handler), but the empty-CN edge case still permits a worker cert to call `/restart` and other web-only endpoints.

4. Update `docs/architecture.md` — the line "Master runs with `CERT_OPTIONAL`" is now actually true after this fix; before it was aspirational.

**Verify.**

- With master running on a non-loopback bind, `curl --cacert ca.pem https://master:9000/tls/token` (no client cert) must return 403.
- Same call with the web client cert returns the token info.
- Same call with a worker cert returns 403.
- `POST /bootstrap` still works without a client cert (it's a public endpoint by design).

---

## 2. Web dashboard must serve HTTPS (HIGH)

**Files:** `web/main.py`, `web/app.py`, `shared/tls.py`, `shared/config.py`, `docs/architecture.md`, `packa.example.toml`

**Problem.** `web/main.py:103-105` constructs `uvicorn.Config(app, host=bind, port=port, ...)` with no `ssl_*` kwargs. The cert/key in `web.db` are only used for *outbound* mTLS to master/workers. So a user who binds web to a non-loopback address (with auth or `--insecure-no-auth`) sends login passwords and session cookies in plaintext HTTP. The session middleware also doesn't set `https_only`.

**Fix.**

1. Add a separate TLS config for the browser-facing listener. The mTLS cert (CN=`web`) is for client auth to master/workers; it should not be reused as the browser-facing server cert because its CA isn't a public CA and the CN is wrong.

   In `shared/config.py`, add to `WebConfig`:
   ```python
   browser_tls_cert: str = ""   # PEM file path, server cert for the browser
   browser_tls_key: str = ""    # PEM file path
   ```
   Wire these through `[web.tls]` in the TOML and `PACKA_WEB_BROWSER_TLS_CERT` / `PACKA_WEB_BROWSER_TLS_KEY` env vars, matching the existing config_store pattern.

2. In `web/main.py`, when `browser_tls_cert` and `browser_tls_key` are set, pass them to uvicorn:
   ```python
   tls_kwargs = {}
   if config.browser_tls_cert and config.browser_tls_key:
       tls_kwargs["ssl_certfile"] = config.browser_tls_cert
       tls_kwargs["ssl_keyfile"]  = config.browser_tls_key
   uvi_config = uvicorn.Config(app, host=bind, port=port, log_level="info",
                               log_config=UVICORN_LOG_CONFIG, **tls_kwargs)
   ```

3. Add a loopback guard in `web/main.py` that mirrors the existing auth/TLS guards: refuse to bind non-loopback when `browser_tls_cert` is unset, unless `--insecure-no-https` is passed. Add `--insecure-no-https` as an argparse flag. Print a `WARNING:` line when the override is used and a `FATAL:` line when it's required and missing.

4. In `web/app.py:33-37`, configure the session middleware with secure defaults:
   ```python
   app.add_middleware(
       SessionMiddleware,
       secret_key=secret_key,
       https_only=True,
       same_site="lax",
       max_age=14 * 24 * 3600,
   )
   ```
   The `https_only=True` is the important bit — it prevents the cookie from being attached to plain-HTTP requests if a user ever hits the dashboard over HTTP (e.g., misconfigured proxy, direct IP access, MITM downgrade). For loopback dev usage where someone runs without browser TLS, allow opting out via a config flag — but default is `https_only=True`.

5. Update `packa.example.toml` and `docs/architecture.md` to document the new `[web.tls]` keys and the new fatal/warn behaviour.

**Verify.**

- `python -m web.main --bind 0.0.0.0` (no certs configured, no override) prints FATAL and exits.
- With certs configured, `curl https://localhost:8080/login` returns the login page; `curl http://localhost:8080/login` either fails or serves a redirect, never the page.
- After login, `Set-Cookie` header on the session contains `HttpOnly` and `Secure`.

---

## 3. Hash login passwords (HIGH)

**Files:** `web/app.py`, `web/main.py`, `requirements.txt`

**Problem.** `auth.password` is stored in `web.db` verbatim and compared with `secrets.compare_digest` in `_logged_in()` and `/login` and `/data/auth`. Anyone with read access to `web.db` (backup, container escape, host-level access, second tenant on the same volume) gets the credential in plaintext.

**Fix.**

1. Add `argon2-cffi` to `requirements.txt`. Argon2id is the right default in 2026; bcrypt is acceptable if argon2 is unavailable, but prefer argon2.

2. In `web/app.py`, add a hashing helper:
   ```python
   from argon2 import PasswordHasher
   from argon2.exceptions import VerifyMismatchError, InvalidHash

   _ph = PasswordHasher()

   def _hash_password(plain: str) -> str:
       return _ph.hash(plain)

   def _verify_password(stored: str, plain: str) -> bool:
       try:
           _ph.verify(stored, plain)
           return True
       except (VerifyMismatchError, InvalidHash):
           return False
   ```

3. Replace every `secrets.compare_digest(password, _config.password or "")` with `_verify_password(_config.password or "", password)`. There are three sites:
   - `_logged_in()` Basic auth path (~line 97)
   - `/login` POST handler (~line 165)
   - `/data/auth` does not need to verify; it only writes.

4. In `/data/auth` (~line 339), hash before storing:
   ```python
   hashed = _hash_password(password) if password else ""
   set_setting("auth.password", hashed)
   _config.password = hashed
   ```

5. Migration. On startup in `web/main.py`, after loading `auth.password` from the store, if it doesn't look like an argon2 hash (doesn't start with `$argon2`), assume it's a legacy plaintext value, hash it, write the hash back, and continue. This keeps existing deployments working through the upgrade.
   ```python
   stored_password = get_setting("auth.password")
   if stored_password and not stored_password.startswith("$argon2"):
       from argon2 import PasswordHasher
       hashed = PasswordHasher().hash(stored_password)
       set_setting("auth.password", hashed)
       stored_password = hashed
       print("[web] migrated plaintext password to argon2 hash")
   ```

6. The username comparison can stay as `secrets.compare_digest` — usernames aren't secrets and don't need hashing.

**Verify.**

- After setting a password via `/data/auth`, `sqlite3 web.db 'select value from web_settings where key="auth.password"'` returns a string starting with `$argon2`.
- Login with the correct password succeeds.
- Login with a wrong password returns 401 with the same timing as a correct one (argon2 verify is constant-time-ish; resistant enough for our threat model).
- An existing deployment with a plaintext password in `web.db` boots, prints the migration line once, and login still works.

---

## 4. Pin master CA on bootstrap (MEDIUM)

**Files:** `worker/api.py`, `web/main.py`, `master/api.py`, `docs/architecture.md`, `packa.example.toml`

**Problem.** `worker/api.py:501` and `web/main.py:73` POST to `https://master/bootstrap` with `verify=False` and no fingerprint check. The architecture doc calls this TOFU but no pinning ever occurs — the next call uses the CA returned in the bundle, which the same MITM controls. An attacker on the worker→master path during bootstrap intercepts the token, returns their own CA + cert, and now MITMs everything.

**Fix.**

1. Require a CA SHA-256 fingerprint at bootstrap time. The master already exposes one at `GET /tls/status`. Operators copy that fingerprint from the master log (already printed) or from `/tls/status` and pass it to the worker/web at bootstrap.

2. In `worker/api.py`, extend `TlsBootstrapRequest` to include `ca_fingerprint: str` (required, non-empty). In the bootstrap handler:
   ```python
   import ssl
   from shared.pki import cert_fingerprint

   # Fetch master's TLS chain WITHOUT verifying, then check the CA fingerprint
   # by fetching /tls/status and comparing to body.ca_fingerprint.
   async with httpx.AsyncClient(timeout=10, verify=False) as client:
       status_r = await client.get(
           f"https://{_config.master_host}:{_config.master_port}/tls/status"
       )
       status_r.raise_for_status()
       presented_fp = (status_r.json() or {}).get("ca_fingerprint", "")
   if not presented_fp:
       raise HTTPException(status_code=502, detail="Master did not return a CA fingerprint")
   if presented_fp.replace(":", "").upper() != body.ca_fingerprint.replace(":", "").upper():
       raise HTTPException(
           status_code=400,
           detail=f"CA fingerprint mismatch (got {presented_fp}, expected {body.ca_fingerprint})",
       )
   # Now safe to send the token.
   ```
   Then proceed with the existing `/bootstrap` POST. The token is only sent after the fingerprint matches.

   This is still TOFU-flavoured — an attacker who is in path *and* knows the expected fingerprint can't help themselves, but the operator must transport the fingerprint out-of-band. That's the actual security boundary.

3. In `web/main.py`, do the same in `_bootstrap_tls`. Add `bootstrap_ca_fingerprint` to `WebConfig` and `PACKA_WEB_BOOTSTRAP_CA_FINGERPRINT` env var. Refuse to bootstrap if the fingerprint is missing — log a clear FATAL telling the operator how to obtain it (`docker compose logs master | grep "CA fingerprint"` or `curl -k https://master:9000/tls/status`).

4. Master prints the CA fingerprint on startup. It already prints the bootstrap token; add the fingerprint right next to it in `master/master.py:112`:
   ```python
   from .tls_manager import get_ca_fingerprint
   fp = get_ca_fingerprint(db2)
   print(f"[tls] CA fingerprint: {fp}")
   ```

5. Update `docs/architecture.md` security section to document the new flow and remove the misleading "TOFU" wording.

**Verify.**

- Worker bootstrap with no fingerprint → 400.
- Worker bootstrap with a wrong fingerprint → 400, no token leaked (the token isn't sent until after the fingerprint match).
- Worker bootstrap with the correct fingerprint → succeeds, restart, normal mTLS afterwards.
- Same three cases for web.

---

## 5. Worker must validate master-supplied paths (MEDIUM)

**Files:** `worker/poller.py`

**Problem.** `worker/poller.py:61` does `full_path = path_prefix + job_data["file_path"]` with no traversal check. A compromised or malicious master can send `file_path = "../../../etc/something"` and the worker will operate on a file outside its configured prefix. With `replace_original=true` and a target file ffmpeg can read as video, this is a write primitive. Most paths die at "ffmpeg can't transcode that", but defence-in-depth matters here — the worker should not assume the master is benign.

**Fix.**

In `worker/poller.py:60-73`, after constructing `full_path`, resolve it and verify containment:

```python
from pathlib import Path

for job_data in jobs:
    raw_relative = job_data["file_path"]
    full_path_str = path_prefix + raw_relative if path_prefix else raw_relative
    if path_prefix:
        try:
            resolved = Path(full_path_str).resolve()
            prefix_resolved = Path(path_prefix).resolve()
            resolved.relative_to(prefix_resolved)
        except (ValueError, OSError):
            print(f"[poller] rejecting job {job_data.get('id')} — path escapes prefix: {raw_relative!r}")
            continue
        full_path = str(resolved)
    else:
        full_path = full_path_str
    # ... existing record creation ...
```

Notes:
- Use `.resolve()` to follow symlinks and normalize `..`. The check is meaningless without it.
- Skip the job rather than error it — we don't want to give a malicious master a side channel via worker DB state. Just log and move on.
- When `path_prefix` is empty (single-host deployment), no check is possible; that's fine because in that mode master and worker are the same trust domain.

**Verify.**

- Add a unit test or quick manual check: feed the poller a job_data with `file_path = "../../etc/passwd"` and `path_prefix = "/mnt/files/"`. The job is logged and skipped, no record is created.
- A normal job with `file_path = "shows/ep1.mkv"` proceeds as before.

---

## 6. Remove dead code and tighten guards (LOW)

**Files:** `master/api.py`, `worker/api.py`

**Problem.** `_require_localhost_or_mtls` is defined on both master (line ~996) and worker (line ~548) and never called. Dead code in a security-sensitive area is confusing and tempting for future "let me reuse this" mistakes.

**Fix.**

Delete both definitions. If you find later you need a third guard tier, add it back when you have a concrete use site.

**Verify.**

- `grep -rn "_require_localhost_or_mtls" master/ worker/` returns nothing after the change.
- All tests still pass; nothing imports the symbol.

---

## 7. Pin Docker base image by digest (LOW)

**Files:** `Dockerfile`

**Problem.** I didn't fully audit the Dockerfile, but the README mentions the image is based on `linuxserver/ffmpeg`. If the `FROM` line uses a floating tag (`latest`, `version`, etc.), every build pulls whatever's current and inherits whatever vulnerabilities are current.

**Fix.**

1. Open `Dockerfile`. If the `FROM` line uses a floating tag, replace with a digest pin:
   ```dockerfile
   FROM linuxserver/ffmpeg@sha256:<digest>
   ```
   Get the current digest with `docker pull linuxserver/ffmpeg:<tag> && docker inspect linuxserver/ffmpeg:<tag> --format='{{index .RepoDigests 0}}'`.

2. Add a comment above the `FROM` noting when the digest was last refreshed and how to refresh it. This makes the maintenance burden explicit instead of invisible.

**Verify.**

- `docker build .` succeeds.
- The built image has the same ffmpeg version as before the change.

---

## Out of scope for this pass

These came up but I didn't want to scope-creep the work order:

- CSRF tokens on state-changing `/data/*` endpoints. `SameSite=Lax` covers most cases. Add real CSRF (double-submit token or origin check) if the dashboard ever ends up behind a shared cookie domain.
- Rate limiting on `/login` and `/bootstrap`. Single-user dashboard makes this lower priority; revisit if multi-user auth is added.
- Audit log for `/restart`, `/master/config/*` writes, bootstrap events. Useful for post-incident, not security-critical.
- The `app.add_middleware` call inside `set_config()` is structurally wrong (Starlette warns when middleware is added after app start). Refactor `web/app.py` so middleware is added at module top level using a config object that's populated before app construction, or use a factory pattern. Not security-critical, just a smell.

---

## Suggested commit sequence

One commit per fix, in this order:

1. `security: master requests client certs and guards reject empty-CN`
2. `security: web serves HTTPS to the browser, secure session cookies`
3. `security: hash login passwords with argon2 + migrate plaintext`
4. `security: pin master CA fingerprint at bootstrap`
5. `security: worker rejects job paths that escape the configured prefix`
6. `chore: remove unused _require_localhost_or_mtls helpers`
7. `build: pin linuxserver/ffmpeg base image by digest`

After all seven, update `README.md` and `docs/architecture.md` to reflect the new security posture, and tag a release. Existing deployments need a one-time manual step for #4 (operator must obtain the CA fingerprint and supply it to workers/web on next bootstrap) — call this out in release notes.
