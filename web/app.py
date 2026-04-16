"""
Web frontend — FastAPI app.

Routes:
  GET  /        — dashboard (requires login)
  GET  /login   — login form
  POST /login   — authenticate
  POST /logout  — clear session
"""

from pathlib import Path

import asyncio

import httpx
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from shared.tls import httpx_kwargs, scheme

from .client import fetch_dashboard
from .config import WebConfig

_config: WebConfig = WebConfig()


def set_config(config: WebConfig) -> None:
    global _config
    _config = config
    if not config.secret_key:
        raise ValueError("[web] secret_key must be set in config")
    app.add_middleware(SessionMiddleware, secret_key=config.secret_key, https_only=config.tls.enabled)


app = FastAPI(title="Packa Web")

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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
# Auth helper
# ---------------------------------------------------------------------------

def _logged_in(request: Request) -> bool:
    return bool(request.session.get("user"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/login")
def login_page(request: Request):
    if _logged_in(request):
        return RedirectResponse("/", status_code=303)
    return _templates.TemplateResponse(request, "login.html")


@app.post("/login")
async def login(request: Request, username: str = Form(), password: str = Form()):
    if username == _config.username and password == _config.password:
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)
    return _templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid username or password"},
        status_code=401,
    )


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------------------
# Action routes — proxy commands to master / slaves
# ---------------------------------------------------------------------------

def _master_url() -> str:
    return f"{scheme(_config.tls)}://{_config.master_host}:{_config.master_port}"


def _slave_url(host: str, api_port: int) -> str:
    return f"{scheme(_config.tls)}://{host}:{api_port}"


@app.post("/actions/scan/settings")
async def action_scan_settings(
    request: Request,
    interval: int = Form(),
    enabled: str = Form(default=""),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(
                f"{_master_url()}/scan/settings",
                json={"interval": interval, "enabled": enabled == "on"},
            )
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/scan/start")
async def action_scan_start(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_master_url()}/scan/start")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/scan/stop")
async def action_scan_stop(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_master_url()}/scan/stop")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/slave/stop")
async def action_slave_stop(
    request: Request,
    host: str = Form(),
    api_port: int = Form(),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_slave_url(host, api_port)}/conversion/stop")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/slave/pause")
async def action_slave_pause(
    request: Request,
    host: str = Form(),
    api_port: int = Form(),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_slave_url(host, api_port)}/conversion/pause")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/slave/resume")
async def action_slave_resume(
    request: Request,
    host: str = Form(),
    api_port: int = Form(),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_slave_url(host, api_port)}/conversion/resume")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/slave/drain")
async def action_slave_drain(
    request: Request,
    host: str = Form(),
    api_port: int = Form(),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_slave_url(host, api_port)}/conversion/drain")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/slave/sleep")
async def action_slave_sleep(
    request: Request,
    host: str = Form(),
    api_port: int = Form(),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_slave_url(host, api_port)}/conversion/sleep")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.post("/actions/slave/wake")
async def action_slave_wake(
    request: Request,
    host: str = Form(),
    api_port: int = Form(),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        try:
            await client.post(f"{_slave_url(host, api_port)}/conversion/wake")
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.get("/data/dashboard")
async def data_dashboard(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    master_url = f"{scheme(_config.tls)}://{_config.master_host}:{_config.master_port}"
    data = await fetch_dashboard(master_url, _config.tls)
    return JSONResponse(data)


@app.get("/data/files")
async def data_files(request: Request, status: str | None = Query(default=None)):  # noqa: E501
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    url = f"{_master_url()}/files"
    if status:
        url += f"?status={status}"
    async with httpx.AsyncClient(timeout=10, **httpx_kwargs(_config.tls)) as client:
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
    async with httpx.AsyncClient(timeout=10, **httpx_kwargs(_config.tls)) as client:
        await asyncio.gather(
            *[client.delete(f"{_master_url()}/files/{i}") for i in ids],
            return_exceptions=True,
        )
    return JSONResponse({"ok": True})


@app.post("/data/files/pending")
async def data_files_pending(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    async with httpx.AsyncClient(timeout=10, **httpx_kwargs(_config.tls)) as client:
        # Fetch slave registry so we can cascade to the right slave
        try:
            slaves_r = await client.get(f"{_master_url()}/slaves")
            slaves_map = {s["config_id"]: s for s in slaves_r.json()}
        except Exception:
            slaves_map = {}

        # Patch master; collect responses to find slave assignments
        master_results = await asyncio.gather(
            *[client.patch(f"{_master_url()}/files/{i}/status", json={"status": "pending"}) for i in ids],
            return_exceptions=True,
        )

        # Cascade to slave for each record that has one
        slave_patches = []
        for i, result in zip(ids, master_results):
            if isinstance(result, Exception):
                continue
            try:
                rec = result.json()
                slave_cfg = rec.get("slave_id")
                if slave_cfg and slave_cfg in slaves_map:
                    s = slaves_map[slave_cfg]
                    slave_patches.append(
                        client.patch(
                            f"{_slave_url(s['host'], s['api_port'])}/files/{i}/status",
                            json={"status": "pending"},
                        )
                    )
            except Exception:
                pass
        if slave_patches:
            await asyncio.gather(*slave_patches, return_exceptions=True)

    return JSONResponse({"ok": True})


@app.post("/data/slave/delete")
async def data_slave_delete(request: Request, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    base = _slave_url(host, port)
    async with httpx.AsyncClient(timeout=10, **httpx_kwargs(_config.tls)) as client:
        # Delete from slave and master in parallel
        await asyncio.gather(
            *[client.delete(f"{base}/files/{i}") for i in ids],
            *[client.delete(f"{_master_url()}/files/{i}") for i in ids],
            return_exceptions=True,
        )
    return JSONResponse({"ok": True})


@app.post("/data/slave/pending")
async def data_slave_pending(request: Request, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids: list[int] = body.get("ids", [])
    base = _slave_url(host, port)
    async with httpx.AsyncClient(timeout=10, **httpx_kwargs(_config.tls)) as client:
        await asyncio.gather(
            *[client.patch(f"{base}/files/{i}/status", json={"status": "pending"}) for i in ids],
            *[client.patch(f"{_master_url()}/files/{i}/status", json={"status": "pending"}) for i in ids],
            return_exceptions=True,
        )
    return JSONResponse({"ok": True})


@app.get("/data/slave")
async def data_slave(request: Request, host: str = Query(), port: int = Query()):
    if not _logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    base = _slave_url(host, port)
    async with httpx.AsyncClient(timeout=5, **httpx_kwargs(_config.tls)) as client:
        results = await asyncio.gather(
            client.get(f"{base}/status"),
            client.get(f"{base}/files"),
            return_exceptions=True,
        )
    st = results[0].json() if not isinstance(results[0], Exception) else None
    files = results[1].json() if not isinstance(results[1], Exception) else []
    return JSONResponse({"status": st, "files": files})


@app.get("/")
async def dashboard(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    master_url = f"{scheme(_config.tls)}://{_config.master_host}:{_config.master_port}"
    data = await fetch_dashboard(master_url, _config.tls)
    return _templates.TemplateResponse(request, "dashboard.html", {"data": data})
