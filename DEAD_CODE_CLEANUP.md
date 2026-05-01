# Dead code cleanup

This is a follow-up to `SECURITY_FIXES.md` and its addendum. The findings below come from running `vulture` and `pyflakes` over the codebase, then verifying each candidate by hand. False positives (FastAPI route handlers, Pydantic fields, SQLAlchemy event listeners, `noqa`-flagged backward-compat imports) have been excluded.

Apply in the order listed. Each item is independent — if one fails, skip and move on. Run `python -c "import master.api, worker.api, web.app"` after each item to catch import-time breakage early.

---

## 1. Delete `worker/identity.py` (HIGH — broken file)

**File:** `worker/identity.py`

**Problem.** This single-line shim reads:

```python
from .store import get_or_create_worker_id, get_stored_worker_id  # noqa: F401
```

But `get_or_create_worker_id` **does not exist** in `worker/store.py`. Only `get_stored_worker_id` does. Anyone who ever runs `from worker import identity` or `from worker.identity import get_or_create_worker_id` gets `ImportError: cannot import name 'get_or_create_worker_id' from 'worker.store'`. It's latent today because nothing imports the file, but it's a landmine for any future code that reaches for the documented-looking helper.

**Fix.**

```bash
rm worker/identity.py
```

**Verify.**

- `grep -rn "worker.identity\|from worker import identity\|from \.identity" .` returns nothing.
- `python -c "import worker.api"` still succeeds.

---

## 2. Delete dead pass-through modules (LOW)

**Files:** `shared/base.py`, `worker/settings.py`, `web/config.py`

**Problem.** Three single-line modules exist solely to re-export symbols from elsewhere with a `# noqa: F401` comment. None of them are imported anywhere in the codebase. They're leftovers from refactors that moved code to other locations.

- `shared/base.py` → `from .models import Base  # noqa: F401 — kept for backward compatibility`
- `worker/settings.py` → `from .store import get_setting, set_setting  # noqa: F401`
- `web/config.py` → `from shared.config import WebConfig, load_web  # noqa: F401`

**Fix.**

```bash
rm shared/base.py worker/settings.py web/config.py
```

**Verify.**

- `grep -rn "shared\.base\|worker\.settings\|web\.config" .` returns no Python imports of these paths.
- `python -c "import master.api, worker.api, web.app"` succeeds.

---

## 3. Remove dead `_require_localhost_or_mtls` and `_peer_has_cert` (LOW)

**Files:** `master/api.py`, `worker/api.py`

**Problem.** This is fix #6 from the original work order, never applied. After fix #1 shipped, `_require_localhost_or_mtls` is the *only* caller of `_peer_has_cert`, so both go together. The actual access control is now done by `_require_web_cert` and `_require_worker_cert`.

**Fix.**

In `master/api.py`, delete lines 974–1007 (both `_peer_has_cert` and `_require_localhost_or_mtls`). Keep `_peer_cn`, `_require_web_cert`, `_require_worker_cert`.

In `worker/api.py`, delete lines 531–563 (both `_peer_has_cert` and `_require_localhost_or_mtls`). Keep `_peer_cn`, `_require_web_cert`.

**Verify.**

- `grep -rn "_require_localhost_or_mtls\|_peer_has_cert" master/ worker/` returns nothing.
- All endpoints still have their existing guards intact.
- `python -c "import master.api, worker.api"` succeeds.

---

## 4. Remove `renew_client_cert` and its dead infrastructure (LOW)

**Files:** `master/tls_manager.py`, `master/api.py`

**Problem.** `master/tls_manager.py:103-107` defines `renew_client_cert`. It's imported in `master/api.py:50` but never called. The codebase comments around `_RENEW_DAYS = 30` suggest cert renewal was planned but never wired up — workers/web get a fresh cert via re-bootstrap instead.

**Fix.**

1. Delete the function from `master/tls_manager.py:103-107`:
   ```python
   def renew_client_cert(db: Session, cn: str, old_cert_pem: str, sans: list[str] | None = None) -> tuple[str, str, str]:
       """Renew a client cert. Caller must have authenticated via existing mTLS cert."""
       if needs_renewal(old_cert_pem, _RENEW_DAYS):
           print(f"[tls] renewing cert for {cn!r}")
       return issue_client_cert(db, cn, sans=sans)
   ```

2. Drop `renew_client_cert` from the import block in `master/api.py:48-51`. After the change:
   ```python
   from .tls_manager import (
       consume_token, generate_token, get_ca_fingerprint,
       get_token_info, issue_client_cert,
   )
   ```

3. Drop `_RENEW_DAYS` from the `from shared.pki import` line in `master/tls_manager.py:14` (it's only used inside the deleted function). Keep `_CA_RENEW_DAYS`, `cert_fingerprint`, `generate_ca`, `generate_cert`, `needs_renewal` — those are still used.

4. **Don't** delete `_RENEW_DAYS` from `shared/pki.py` itself — it's still used as the default-arg value for `needs_renewal()` (line 104).

**Verify.**

- `grep -rn "renew_client_cert" master/ worker/ web/ shared/` returns nothing.
- `python -c "import master.api"` succeeds.
- The `/bootstrap` flow still works (run a worker bootstrap end-to-end).

---

## 5. Remove dead round-robin worker selection (LOW)

**Files:** `master/registry.py`

**Problem.** `WorkerRegistry.next_worker()` and `_rebuild_cycle()` and the `_cycle` field implement round-robin job distribution from the old push model. The architecture is now pull-based — workers call `/jobs/claim`, master never picks workers. None of this code is reachable.

**Fix.**

Replace `master/registry.py` with the cleaned-up version. Specifically:

1. Drop `from itertools import cycle` and `from typing import Iterator` (only used by the dead machinery).
2. Drop `field` from `from dataclasses import dataclass, field` — also unused.
3. Drop the `self._cycle` field initialization in `__init__`.
4. Remove every `self._rebuild_cycle()` call from `register()` (lines 41, 49) and `remove()` (line 55).
5. Delete `next_worker()` (lines 74-78) and `_rebuild_cycle()` (lines 80-81).
6. Update the module docstring (line 3) — drop `Round-robin distribution via next_worker().`

After cleanup, `master/registry.py` should read:

```python
"""
In-memory registry of connected workers.
"""

from dataclasses import dataclass

from .petnames import pick


@dataclass
class WorkerInfo:
    id: int
    config_id: str
    host: str
    api_port: int
    scheme: str = "http"

    def __str__(self) -> str:
        return f"worker-{self.id} '{self.config_id}' ({self.scheme}://{self.host}:{self.api_port})"


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[int, WorkerInfo] = {}
        self._next_id: int = 1

    def _used_config_ids(self) -> set[str]:
        return {w.config_id for w in self._workers.values()}

    def register(self, config_id: str, host: str, api_port: int, scheme: str = "http") -> WorkerInfo:
        if config_id:
            existing = next((s for s in self._workers.values() if s.config_id == config_id), None)
            if existing:
                existing.host = host
                existing.api_port = api_port
                existing.scheme = scheme
                return existing
        else:
            config_id = pick(self._used_config_ids())

        worker = WorkerInfo(id=self._next_id, config_id=config_id, host=host, api_port=api_port, scheme=scheme)
        self._workers[self._next_id] = worker
        self._next_id += 1
        return worker

    def remove(self, worker_id: int) -> bool:
        if worker_id in self._workers:
            del self._workers[worker_id]
            return True
        return False

    def remove_by_config_id(self, config_id: str) -> bool:
        existing = self.get_by_config_id(config_id)
        if existing:
            return self.remove(existing.id)
        return False

    def get(self, worker_id: int) -> WorkerInfo | None:
        return self._workers.get(worker_id)

    def get_by_config_id(self, config_id: str) -> WorkerInfo | None:
        return next((s for s in self._workers.values() if s.config_id == config_id), None)

    def all(self) -> list[WorkerInfo]:
        return list(self._workers.values())


registry = WorkerRegistry()
```

**Verify.**

- `grep -rn "next_worker\|_rebuild_cycle\|_cycle" master/ worker/ web/` returns nothing.
- Worker registers, claims jobs, and reports results — full smoke test.
- `python -c "import master.api"` succeeds.

---

## 6. Remove dead server-side SSLContext builder (LOW)

**Files:** `shared/tls.py`, `shared/pki.py`

**Problem.** `TlsConfig.server_ssl_context()` (`shared/tls.py:26-34`) builds an `ssl.SSLContext` for server-side use. It's never called — both master and worker pass cert/key/ca file paths to uvicorn via `uvicorn_tls_kwargs()` instead. The underlying `make_server_ssl_context()` (`shared/pki.py:138-144`) is only called by this dead method, so it's dead by transitivity.

**Fix.**

1. Delete `TlsConfig.server_ssl_context()` from `shared/tls.py:26-34`.
2. Delete `make_server_ssl_context()` from `shared/pki.py:138-144`.

The client-side counterparts (`client_ssl_context`, `make_client_ssl_context`) stay — `httpx_kwargs()` uses them.

**Verify.**

- `grep -rn "server_ssl_context\|make_server_ssl_context" .` returns nothing.
- mTLS still works between master, worker, and web.
- `python -c "import shared.tls, shared.pki"` succeeds.

---

## 7. Remove unused helpers and variables (LOW)

**Files:** `shared/config.py`, `shared/crud.py`, `worker/api.py`

**Problem.** Three small unused items.

**Fix.**

1. **`shared/config.py:21-25`** — delete the `_env_float` function. `_env` and `_env_int` siblings stay (they're used).

2. **`shared/crud.py:301-302`** — delete the `_tier_defaults` local variable. The inline dict literal on lines 311-312 is what's actually used; `_tier_defaults` was leftover from a refactor where the intent was probably `setdefault(tier, _tier_defaults.copy())`. Cleanest fix: just delete those two lines.

3. **`worker/api.py:41`** — drop `FfmpegProgress` from the import. `Job` and `worker_state` from the same line stay. After:
   ```python
   from .state import Job, worker_state
   ```

**Verify.**

- `grep -rn "_env_float\|_tier_defaults\|FfmpegProgress" master/ worker/ web/ shared/` returns only the legitimate definition site of `FfmpegProgress` in `worker/state.py`.
- `python -c "import shared.config, shared.crud, worker.api"` succeeds.
- Stats endpoint still returns sensible data (item 2 changes nothing functionally — the inline literal already does the work).

---

## Bonus: real bug, scope it separately

**File:** `worker/worker.py`

**Problem.** Line 565 calls `os.unlink(output_path)` but `os` is never imported in this file. When the post-conversion integrity check fails (`_output_is_valid` returns False) and `replace_original=true`, the worker hits `NameError: name 'os' is not defined` instead of cleaning up the corrupt output file. The branch is rare (requires both ffmpeg producing a bad output *and* `replace_original` being on), which is why it's gone unnoticed.

**Fix.**

Add `import os` to the import block at the top of `worker/worker.py`. After:

```python
import asyncio
import os
import shlex
import shutil
import time
```

**Verify.**

- `python -c "import worker.worker"` succeeds.
- Manually trigger the path: feed the worker a job that ffmpeg will produce empty/invalid output for, with `replace_original=true`. Confirm worker logs the integrity failure and cleans up the output instead of crashing.

This is a separate commit from the dead-code cleanup. Suggested message: `worker: import os so the integrity-check failure branch doesn't crash`.

---

## Order and commits

Suggested commit sequence:

1. `chore: remove broken worker/identity.py shim` (item 1)
2. `chore: remove dead pass-through modules` (item 2)
3. `chore: remove unused _require_localhost_or_mtls and _peer_has_cert` (item 3)
4. `chore: remove unused renew_client_cert` (item 4)
5. `chore: remove dead round-robin worker selection` (item 5)
6. `chore: remove unused server_ssl_context builder` (item 6)
7. `chore: remove unused helpers and variables` (item 7)
8. `worker: import os so integrity-check cleanup doesn't crash` (bonus)

Run `pyflakes master/ worker/ web/ shared/ packa/` after the last commit. The remaining warnings should be only:

- The four `noqa: F401` import sites in `master/master.py`, `master/database.py`, `worker/database.py`, and `web/app.py` (intentional — register SQLAlchemy tables)
- A handful of `f-string is missing placeholders` in `master/master.py` (cosmetic, not dead code — fix or ignore at your discretion)

Anything else flagged as dead is a regression introduced by this cleanup pass.
