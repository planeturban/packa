# Security fixes — addendum

This is a follow-up to `SECURITY_FIXES.md`. Fix #1 (master requests client certs, guards reject empty-CN) shipped correctly per the work order, but it broke the new-worker bootstrap flow. This addendum patches that.

The desired worker onboarding flow:

1. Master starts → generates CA + bootstrap token → prints token to log.
2. Web starts → operator pastes the token → web bootstraps, gets a `cn=web` cert.
3. **Worker starts on a remote host with no cert** → tries to register via `POST /workers` with no client cert.
4. Worker appears in the dashboard as registered-but-not-onboarded.
5. Operator clicks "onboard worker" in the dashboard → web generates a fresh bootstrap token and POSTs it to the worker's `/tls/bootstrap` over plain HTTP.
6. Worker calls master's `/bootstrap` with the token, gets a cert, restarts, joins as a full mTLS member.

Fix #1 broke step 3: `POST /workers` is guarded by `_require_worker_cert`, which now 403s when the caller has no cert. The worker can never appear in the dashboard, so step 5 can't happen.

---

## 1a. Allow unauthenticated registration on POST /workers (HIGH — regression fix)

**Files:** `master/api.py`

**Problem.** After fix #1, a freshly-deployed worker on a remote host can't register itself with the master because it has no cert yet. That cert is exactly what onboarding is supposed to provide, but onboarding can't start until the worker is visible in the dashboard, which requires registration. Loopback workers are unaffected (loopback bypass), but multi-host deployments are stuck.

**Why this is safe to loosen.** Registration only writes `(host, port, scheme, config_id)` into the master's worker registry. It does not grant the registering party any ability to claim jobs, read files, or modify state. `/jobs/claim` and `/files/{id}/result` still require a real worker cert via `_require_worker_cert`, and onboarding still requires the operator to explicitly click "onboard" in the dashboard *and* the worker to present a valid one-time bootstrap token to master's `/bootstrap`. An attacker who registers fake workers can clutter the dashboard but cannot cause work to be done or data to leave.

**Fix.**

In `master/api.py`, change the guard on `POST /workers` from `_require_worker_cert` to a no-op. The endpoint must remain reachable to clients without a cert.

Concretely, line 491–496 currently reads:

```python
@app.post("/workers", response_model=WorkerOut, status_code=201)
def register_worker(body: WorkerRegister, request: Request):
    _require_worker_cert(request)
    worker = registry.register(body.config_id, body.host, body.api_port, body.scheme)
    print(f"[master] registered: {worker}")
    return worker
```

Change to:

```python
@app.post("/workers", response_model=WorkerOut, status_code=201)
def register_worker(body: WorkerRegister, request: Request):
    # Intentionally unauthenticated. Registration is just an announcement and
    # confers no privilege — claiming jobs and reporting results still require
    # _require_worker_cert. This must stay open so a fresh worker with no cert
    # can appear in the dashboard before the operator clicks "onboard".
    worker = registry.register(body.config_id, body.host, body.api_port, body.scheme)
    print(f"[master] registered: {worker}")
    return worker
```

The comment is important — it documents intent so a future maintainer (human or agent) doesn't "tighten" this back and re-break the flow.

**Verify.**

- A worker process on a remote host with no cert and `verify=False` can `POST /workers` and gets 201.
- The same worker still cannot `POST /jobs/claim` or `PATCH /files/{id}/result` without a cert (those still 403). Quick check: `curl -k -X POST https://master:9000/jobs/claim -d '{"worker_id":"x","count":1}'` → 403.
- After onboarding, the worker re-registers with its cert and the registry entry is updated, not duplicated.
- Existing endpoints `_require_worker_cert` still guards (`/jobs/claim`, `/files/{id}/result`) continue to reject unauthenticated callers.

---

## 1b. Worker registration loop survives 401/403 from master (LOW — defensive)

**Files:** `worker/api.py`

**Problem.** The worker's `_register_and_poll` loop retries on any exception, including HTTP errors from master. With fix #1 in place but #1a not yet applied, the worker would retry-403 forever and flood logs. Even after #1a, future tightening could re-introduce this. A worker that can't register should fail loudly and stop, not spin.

**Fix.**

In `worker/api.py:_register_and_poll` (~line 96–123), distinguish "transient network failure" from "master rejected my registration." On a 4xx response, log clearly and either back off hard or exit. A 5xx or connection error keeps retrying as today.

```python
import httpx as _httpx

attempt = 0
while True:
    last_exc: Exception | None = None
    fatal = False
    for base, kw in candidates:
        try:
            record = await _try_register(payload, base, kw)
            master_base = base
            tls_kw      = kw
            last_exc    = None
            break
        except _httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500:
                print(f"[worker] master rejected registration: {exc.response.status_code} {exc.response.text}")
                fatal = True
                last_exc = exc
                break
            last_exc = exc
        except Exception as exc:
            last_exc = exc
    if last_exc is None:
        # ... existing success path unchanged ...
        break
    if fatal:
        # Back off hard — operator intervention required.
        wait = 60
    else:
        attempt += 1
        wait = min(5 * attempt, 30)
    print(f"[worker] registration failed (attempt {attempt}): {last_exc} — retrying in {wait}s")
    await asyncio.sleep(wait)
```

The 60-second back-off on 4xx (instead of exiting) keeps the worker process alive so the operator can fix the master config and have the worker recover automatically. Not critical, but cheap.

**Verify.**

- With master returning 403 on `/workers`, the worker logs the rejection clearly and retries every 60s instead of every 5s.
- With master unreachable (connection refused), the worker keeps the existing exponential-ish back-off (5s, 10s, 15s, … capped at 30s).

---

## 1c. Documentation update (LOW)

**Files:** `docs/architecture.md`, `README.md`

**Fix.**

In `docs/architecture.md`, in the Security section, document the registration exception. Replace the bullet that reads:

> Master and worker APIs have no per-request application-layer authentication beyond mTLS — do not expose them to untrusted networks.

with:

> Master and worker APIs have no per-request application-layer authentication beyond mTLS — do not expose them to untrusted networks. The single exception is `POST /workers` on master, which is intentionally unauthenticated so a fresh worker with no cert can announce itself to the dashboard before onboarding. Registration confers no privilege; claiming jobs and reporting results still require a CA-signed worker cert.

Add a short subsection describing the onboarding flow end-to-end (master starts → web onboards → worker registers unauthenticated → operator clicks onboard → worker bootstraps cert → mTLS from then on), so the trust story is explicit.

**Verify.** Eyeball the diff. No code test.

---

## Order

Apply 1a first (unblocks the flow), then 1b (defensive), then 1c (docs). One commit each.

Suggested commit messages:

1. `security: allow unauthenticated POST /workers so new workers can self-register`
2. `worker: distinguish 4xx from transient errors in registration retry`
3. `docs: document the registration exception in the trust model`

After this addendum, fix #1 from the original work order is complete and the new-worker bootstrap flow works end-to-end. Resume from fix #2 (web HTTPS) in the original work order.
