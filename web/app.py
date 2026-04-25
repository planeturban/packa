"""
Web frontend — FastAPI app.

Routes:
  GET  /        — dashboard (login required only when username+password are configured)
  GET  /login   — login form (redirects to / when auth is disabled)
  POST /login   — authenticate
  POST /logout  — clear session
"""

import asyncio
import os
import secrets
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from shared.config import WebConfig
from shared.tls import scheme

from .client import fetch_dashboard
from .store import set_setting

_config: WebConfig = WebConfig()
_VERSION = os.environ.get("PACKA_VERSION", "dev")
_COMMIT  = os.environ.get("PACKA_COMMIT", "local")[:7]


def set_config(config: WebConfig) -> None:
    global _config
    _config = config
    secret_key = config.secret_key or secrets.token_hex(32)
    app.add_middleware(SessionMiddleware, secret_key=secret_key)


app = FastAPI(title="Packa Web")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_templates.env.globals["commit"] = _COMMIT


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

def _fmt_eta(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m:02d}m"


def _fmt_bytes(b: int | None) -> str:
    if b is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


_templates.env.filters["eta"] = _fmt_eta
_templates.env.filters["filesize"] = _fmt_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_enabled() -> bool:
    return bool(_config.username and _config.password)


def _logged_in(request: Request) -> bool:
    if not _auth_enabled():
        return True
    if request.session.get("user"):
        return True
    # Basic auth (for Authentik proxy and similar)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic ") and _config.username and _config.password:
        import base64
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            username, _, password = decoded.partition(":")
            if (username == _config.username
                    and secrets.compare_digest(password, _config.password)):
                return True
        except Exception:
            pass
    return False


def _master_url() -> str:
    return f"{scheme(_config.tls)}://{_config.master_host}:{_config.master_port}"


def _worker_url(host: str, api_port: int, worker_scheme: str | None = None) -> str:
    return f"{worker_scheme or scheme(_config.tls)}://{host}:{api_port}"


def _httpx_kw() -> dict:
    """TLS kwargs for httpx.AsyncClient when connecting to master/workers."""
    return _config.tls.httpx_kwargs()


def _redirect_login():
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login")
def login_page(request: Request):
    if not _auth_enabled() or _logged_in(request):
        return RedirectResponse("/", status_code=303)
    return _templates.TemplateResponse(
        request, "login.html",
        {"needs_bootstrap": not _config.tls.enabled},
    )


@app.post("/login")
async def login(request: Request, username: str = Form(), password: str = Form()):
    if not _auth_enabled():
        return RedirectResponse("/", status_code=303)
    if username == _config.username and password == _config.password:
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)
    return _templates.TemplateResponse(
        request, "login.html",
        {"error": "Invalid username or password"},
        status_code=401,
    )


@app.post("/logout")
def logout(request: Request):
    if not _auth_enabled():
        return RedirectResponse("/", status_code=303)
    request.session.clear()
    return _redirect_login()


@app.get("/setup/bootstrap")
def setup_bootstrap_page(request: Request):
    if _config.tls.enabled:
        return RedirectResponse("/", status_code=303)
    return _templates.TemplateResponse(request, "login.html", {"needs_bootstrap": True})


@app.post("/setup/bootstrap")
async def setup_bootstrap(request: Request, token: str = Form()):
    if _config.tls.enabled:
        return RedirectResponse("/login", status_code=303)
    r = None
    master_host = _config.master_host
    master_port = _config.master_port
    for s, verify in (("https", False), ("http", True)):
        try:
            r = httpx.post(
                f"{s}://{master_host}:{master_port}/bootstrap",
                json={"token": token, "cn": "web"},
                verify=verify,
                timeout=10,
            )
            r.raise_for_status()
            break
        except Exception:
            r = None
    if r is None:
        return _templates.TemplateResponse(
            request, "login.html",
            {"needs_bootstrap": True,
             "bootstrap_error": "Could not reach master — check the token and master address."},
        )
    try:
        bundle = r.json()
        set_setting("tls.cert", bundle["cert_pem"])
        set_setting("tls.key",  bundle["key_pem"])
        set_setting("tls.ca",   bundle["ca_pem"])
        _config.tls.cert_pem = bundle["cert_pem"]
        _config.tls.key_pem  = bundle["key_pem"]
        _config.tls.ca_pem   = bundle["ca_pem"]
    except Exception as exc:
        return _templates.TemplateResponse(
            request, "login.html",
            {"needs_bootstrap": True, "bootstrap_error": f"Bootstrap failed: {exc}"},
        )
    _schedule_restart()
    return _templates.TemplateResponse(request, "login.html", {"bootstrap_restarting": True})


def _schedule_restart() -> None:
    import os as _os, sys as _sys, threading as _threading
    main_spec = getattr(_sys.modules.get('__main__'), '__spec__', None)
    if main_spec and main_spec.name:
        cmd = [_sys.executable, '-m', main_spec.name] + _sys.argv[1:]
    else:
        cmd = [_sys.executable] + _sys.argv
    def _do():
        __import__('time').sleep(0.2)
        _os.execv(_sys.executable, cmd)
    _threading.Thread(target=_do, daemon=True).start()


# ---------------------------------------------------------------------------
# Action routes — proxy commands to master / workers
# ---------------------------------------------------------------------------

async def _worker_action(request: Request, host: str, api_port: int, endpoint: str) -> RedirectResponse:
    if not _logged_in(request):
        return _redirect_login()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            await client.post(f"{_worker_url(host, api_port)}/{endpoint}")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/scan/start")
async def action_scan_start(request: Request):
    if not _logged_in(request):
        return _redirect_login()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            await client.post(f"{_master_url()}/scan/start")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/scan/stop")
async def action_scan_stop(request: Request):
    if not _logged_in(request):
        return _redirect_login()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            await client.post(f"{_master_url()}/scan/stop")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/worker/stop")
async def action_worker_stop(request: Request, host: str = Form(), api_port: int = Form()):
    return await _worker_action(request, host, api_port, "conversion/stop")


@app.post("/actions/worker/pause")
async def action_worker_pause(request: Request, host: str = Form(), api_port: int = Form()):
    return await _worker_action(request, host, api_port, "conversion/pause")


@app.post("/actions/worker/resume")
async def action_worker_resume(request: Request, host: str = Form(), api_port: int = Form()):
    return await _worker_action(request, host, api_port, "conversion/resume")


@app.post("/actions/worker/drain")
async def action_worker_drain(request: Request, host: str = Form(), api_port: int = Form()):
    return await _worker_action(request, host, api_port, "conversion/drain")


@app.post("/actions/worker/sleep")
async def action_worker_sleep(request: Request, host: str = Form(), api_port: int = Form()):
    return await _worker_action(request, host, api_port, "conversion/sleep")


@app.post("/actions/worker/wake")
async def action_worker_wake(request: Request, host: str = Form(), api_port: int = Form()):
    return await _worker_action(request, host, api_port, "conversion/wake")


# ---------------------------------------------------------------------------
# Data endpoints (JSON)
# ---------------------------------------------------------------------------

def _auth_status() -> dict:
    return {
        "enabled": bool(_config.username and _config.password),
        "username": _config.username or "",
    }


@app.get("/data/dashboard")
async def data_dashboard(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await fetch_dashboard(_master_url(), _httpx_kw())
    data["auth"] = _auth_status()
    return JSONResponse(data)


@app.post("/data/auth")
async def data_auth_save(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    if username and not password:
        return JSONResponse({"error": "Password is required when setting a username"}, status_code=400)
    if password and not username:
        return JSONResponse({"error": "Username is required when setting a password"}, status_code=400)
    set_setting("auth.username", username)
    set_setting("auth.password", password)
    _config.username = username
    _config.password = password
    return JSONResponse({"ok": True, "enabled": bool(username and password)})


@app.get("/data/files")
async def data_files(request: Request, status: str | None = Query(default=None)):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    url = f"{_master_url()}/files"
    if status:
        url += f"?status={status}"
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/files/delete")
async def data_files_delete(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    if not ids:
        return JSONResponse({"ok": True})
    async with httpx.AsyncClient(timeout=60, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/files/bulk-delete", json={"ids": ids})
            r.raise_for_status()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"ok": True})


@app.post("/data/files/pending")
async def data_files_pending(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            workers_r = await client.get(f"{_master_url()}/workers")
            workers_map = {s["config_id"]: s for s in workers_r.json()}
        except Exception:
            workers_map = {}

        master_results = await asyncio.gather(
            *[client.patch(f"{_master_url()}/files/{i}/status", json={"status": "pending"}) for i in ids],
            return_exceptions=True,
        )

        worker_patches = []
        for i, result in zip(ids, master_results):
            if isinstance(result, Exception):
                continue
            try:
                rec = result.json()
                worker_cfg = rec.get("worker_id")
                if worker_cfg and worker_cfg in workers_map:
                    s = workers_map[worker_cfg]
                    worker_patches.append(
                        client.patch(
                            f"{_worker_url(s['host'], s['api_port'])}/files/{i}/status",
                            json={"status": "pending"},
                        )
                    )
            except Exception:
                pass
        if worker_patches:
            await asyncio.gather(*worker_patches, return_exceptions=True)

    return JSONResponse({"ok": True})


@app.post("/data/worker/delete")
async def data_worker_delete(request: Request, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    base = _worker_url(host, port)
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        await asyncio.gather(
            *[client.delete(f"{base}/files/{i}") for i in ids],
            *[client.delete(f"{_master_url()}/files/{i}") for i in ids],
            return_exceptions=True,
        )
    return JSONResponse({"ok": True})


@app.post("/data/files/cancel")
async def data_files_cancel(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            workers_r = await client.get(f"{_master_url()}/workers")
            workers_map = {s["config_id"]: s for s in workers_r.json()}
        except Exception:
            workers_map = {}

        master_results = await asyncio.gather(
            *[client.patch(f"{_master_url()}/files/{i}/status", json={"status": "cancelled"}) for i in ids],
            return_exceptions=True,
        )

        worker_patches = []
        for i, result in zip(ids, master_results):
            if isinstance(result, Exception):
                continue
            try:
                rec = result.json()
                worker_cfg = rec.get("worker_id")
                if worker_cfg and worker_cfg in workers_map:
                    s = workers_map[worker_cfg]
                    worker_patches.append(
                        client.patch(
                            f"{_worker_url(s['host'], s['api_port'])}/files/{i}/status",
                            json={"status": "cancelled"},
                        )
                    )
            except Exception:
                pass
        if worker_patches:
            await asyncio.gather(*worker_patches, return_exceptions=True)

    return JSONResponse({"ok": True})


@app.post("/data/files/force-encode")
async def data_files_force_encode(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    skip_size_check: bool = bool(body.get("skip_size_check", False))
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        await asyncio.gather(
            *[client.patch(
                f"{_master_url()}/files/{i}/status",
                json={"status": "pending", "force_encode": skip_size_check},
            ) for i in ids],
            return_exceptions=True,
        )
    return JSONResponse({"ok": True})


@app.post("/data/worker/pending")
async def data_worker_pending(request: Request, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    base = _worker_url(host, port)
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        await asyncio.gather(
            *[client.patch(f"{base}/files/{i}/status", json={"status": "pending"}) for i in ids],
            *[client.patch(f"{_master_url()}/files/{i}/status", json={"status": "pending"}) for i in ids],
            return_exceptions=True,
        )
    return JSONResponse({"ok": True})


@app.post("/data/worker/cancel")
async def data_worker_cancel(request: Request, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    base = _worker_url(host, port)
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        await asyncio.gather(
            *[client.patch(f"{base}/files/{i}/status", json={"status": "cancelled"}) for i in ids],
            *[client.patch(f"{_master_url()}/files/{i}/status", json={"status": "cancelled"}) for i in ids],
            return_exceptions=True,
        )
    return JSONResponse({"ok": True})


@app.post("/data/files/assign")
async def data_files_assign(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    worker_config_id: str = body.get("worker_config_id", "")
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            workers_r = await client.get(f"{_master_url()}/workers")
            worker_info = next((s for s in workers_r.json() if s["config_id"] == worker_config_id), None)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        if not worker_info:
            return JSONResponse({"error": "worker not found"}, status_code=404)
        try:
            r = await client.post(f"{_master_url()}/jobs/assign",
                                  json={"ids": ids, "worker_id": worker_config_id})
            r.raise_for_status()
            jobs = r.json()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        if jobs:
            try:
                await client.post(
                    f"{_worker_url(worker_info['host'], worker_info['api_port'])}/jobs/push",
                    json=jobs,
                )
            except Exception:
                pass
    return JSONResponse({"ok": True, "assigned": len(jobs)})


@app.get("/data/files/duplicate-pairs")
async def data_duplicate_pairs(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            r = await client.get(f"{_master_url()}/files/duplicate-pairs")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/scan/start")
async def data_scan_start(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/scan/start")
            r.raise_for_status()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"ok": True})


@app.post("/data/scan/stop")
async def data_scan_stop(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/scan/stop")
            r.raise_for_status()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"ok": True})


@app.post("/data/transfer")
async def data_transfer(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/transfer", json={"file_path": body["file_path"]})
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/workers/register")
async def data_workers_register(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/workers", json=body)
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.delete("/data/workers/{worker_id}")
async def data_workers_deregister(request: Request, worker_id: str):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.delete(f"{_master_url()}/workers/{worker_id}")
            r.raise_for_status()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"ok": True})


@app.post("/data/worker/action")
async def data_worker_action(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    host = body.get("host")
    port = body.get("port")
    action = body.get("action")
    if action not in ("pause", "resume", "stop", "drain", "sleep", "wake"):
        return JSONResponse({"error": "invalid action"}, status_code=400)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_worker_url(host, port)}/conversion/{action}")
            r.raise_for_status()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"ok": True})


@app.post("/restart")
def web_restart(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    _schedule_restart()
    return JSONResponse({"ok": True})


@app.post("/data/master/restart")
async def data_master_restart(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/restart")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/worker/tls/onboard")
async def data_worker_tls_onboard(request: Request):
    """Generate a bootstrap token and send it to a worker that has no TLS yet, then restart it."""
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    host = body.get("host")
    port = body.get("port")
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        # Ensure a valid token exists
        token_r = await client.get(f"{_master_url()}/tls/token")
        token_info = token_r.json() if token_r.is_success else {}
        if not token_info.get("token"):
            gen_r = await client.post(f"{_master_url()}/tls/token")
            gen_r.raise_for_status()
            token_info = gen_r.json()
        token = token_info["token"]
    # Worker has no TLS yet — talk to it over HTTP directly
    worker_base = f"http://{host}:{port}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{worker_base}/tls/bootstrap", json={"token": token})
            r.raise_for_status()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"ok": True})


@app.post("/data/worker/restart")
async def data_worker_restart(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    host = body.get("host")
    port = body.get("port")
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_worker_url(host, port)}/restart")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.patch("/data/master/config/{key}")
async def data_master_config_set(request: Request, key: str):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.patch(f"{_master_url()}/master/config/{key}", json=body)
            r.raise_for_status()
            return JSONResponse(r.json())
        except httpx.HTTPStatusError as exc:
            return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.delete("/data/master/config/{key}")
async def data_master_config_clear(request: Request, key: str):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.delete(f"{_master_url()}/master/config/{key}")
            r.raise_for_status()
            return JSONResponse(r.json())
        except httpx.HTTPStatusError as exc:
            return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/master/config/{key}/restore")
async def data_master_config_restore(request: Request, key: str):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/master/config/{key}/restore", json=body)
            r.raise_for_status()
            return JSONResponse(r.json())
        except httpx.HTTPStatusError as exc:
            return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.patch("/data/worker/config/{key}")
async def data_worker_config_set(request: Request, key: str, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.patch(f"{_worker_url(host, port)}/config/{key}", json=body)
            r.raise_for_status()
            return JSONResponse(r.json())
        except httpx.HTTPStatusError as exc:
            return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.delete("/data/worker/config/{key}")
async def data_worker_config_clear(request: Request, key: str, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.delete(f"{_worker_url(host, port)}/config/{key}")
            r.raise_for_status()
            return JSONResponse(r.json())
        except httpx.HTTPStatusError as exc:
            return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/worker/config/{key}/restore")
async def data_worker_config_restore(request: Request, key: str, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_worker_url(host, port)}/config/{key}/restore", json=body)
            r.raise_for_status()
            return JSONResponse(r.json())
        except httpx.HTTPStatusError as exc:
            return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/data/tls/token")
async def data_tls_token(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.get(f"{_master_url()}/tls/token")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/tls/token")
async def data_tls_token_create(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_master_url()}/tls/token")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/data/tls/status")
async def data_tls_status(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.get(f"{_master_url()}/tls/status")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/data/stats")
async def data_stats(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            r = await client.get(f"{_master_url()}/stats")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/data/stats/worker")
async def data_stats_worker(request: Request, worker_id: str = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    async with httpx.AsyncClient(timeout=10, **_httpx_kw()) as client:
        try:
            r = await client.get(f"{_master_url()}/stats/worker/{worker_id}")
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/data/worker/encoder")
async def data_worker_encoder(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    host = body.get("host")
    port = body.get("port")
    encoder = body.get("encoder")
    payload: dict = {"encoder": encoder}
    if body.get("replace_original") is not None:
        payload["replace_original"] = bool(body["replace_original"])
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        try:
            r = await client.post(f"{_worker_url(host, port)}/settings", json=payload)
            r.raise_for_status()
            return JSONResponse(r.json())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/data/worker")
async def data_worker(request: Request, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    base = _worker_url(host, port)
    async with httpx.AsyncClient(timeout=5, **_httpx_kw()) as client:
        results = await asyncio.gather(
            client.get(f"{base}/status"),
            client.get(f"{base}/files"),
            return_exceptions=True,
        )
    st = results[0].json() if not isinstance(results[0], Exception) else None
    files = results[1].json() if not isinstance(results[1], Exception) else []
    return JSONResponse({"status": st, "files": files})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/")
async def dashboard(request: Request):
    if not _logged_in(request):
        return _redirect_login()
    data = await fetch_dashboard(_master_url(), _httpx_kw())
    return _templates.TemplateResponse(
        request, "dashboard.html",
        {"data": data, "auth_enabled": _auth_enabled(), "version": _VERSION, "commit": _COMMIT},
    )
