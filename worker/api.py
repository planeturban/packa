"""
Worker REST API.

  GET    /status                 — worker state + live ffmpeg progress
  POST   /files                  — submit a file record (enqueues for conversion)
  GET    /files[?status=]        — list file records
  GET    /files/{id}             — get a single file record
  DELETE /files/{id}             — delete a file record (terminates ffmpeg if running)
  PATCH  /files/{id}/status      — update a record's status
  POST   /conversion/stop        — terminate the running ffmpeg process
  POST   /conversion/pause       — suspend the running ffmpeg process (SIGSTOP)
  POST   /conversion/resume      — resume a paused process; clears drain flag
  POST   /conversion/drain       — finish current job then stop polling
  POST   /conversion/sleep       — enter sleep mode (no polling, no new jobs)
  POST   /conversion/wake        — leave sleep mode
  GET    /settings               — current encoder
  POST   /settings               — change encoder (also activates unconfigured worker)
"""

import asyncio
import signal

from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import crud
from shared.config import Config
from shared.db import migrate
from shared.version import VERSION as _VERSION
from shared.models import Base, FileStatus
from shared.schemas import FileRecordCreate, FileRecordOut, StatusUpdate

from . import config_store
from .database import engine, get_db
from .poller import poller_loop
from .state import FfmpegProgress, Job, worker_state
from .store import get_setting, set_setting
from .worker import recover, sync_loop, worker_loop

Base.metadata.create_all(bind=engine)
migrate(engine)

_config: Config = Config()
_advertise_host: str = ""
_worker_config_id: str = ""
_config_path: str | None = None
_cli_values: dict = {}


def set_config(config: Config) -> None:
    global _config
    _config = config


def set_config_layers(config_path: str | None, cli_values: dict) -> None:
    global _config_path, _cli_values
    _config_path = config_path
    _cli_values = cli_values


def set_registration_params(advertise_host: str, worker_config_id: str) -> None:
    global _advertise_host, _worker_config_id
    _advertise_host = advertise_host
    _worker_config_id = worker_config_id


async def _try_register(payload: dict, master_base: str, tls_kw: dict) -> dict | None:
    """Attempt one registration POST. Returns parsed JSON on success, None on failure."""
    async with httpx.AsyncClient(timeout=10, **tls_kw) as client:
        r = await client.post(f"{master_base}/workers", json=payload)
        r.raise_for_status()
        return r.json()


async def _register_and_poll() -> None:
    """Retry registration until master is reachable, then keep registration fresh and run the poller."""
    global _worker_config_id
    payload = {"config_id": _worker_config_id, "host": _advertise_host, "api_port": _config.api_port,
               "scheme": "https" if _config.tls.enabled else "http"}

    master_https = f"https://{_config.master_host}:{_config.master_port}"
    if _config.tls.enabled:
        candidates = [(master_https, _config.tls.httpx_kwargs())]
    else:
        # No client cert yet — use HTTPS with TOFU until bootstrap completes
        candidates = [(master_https, {"verify": False})]

    master_base: str = candidates[0][0]
    tls_kw: dict     = candidates[0][1]

    attempt = 0
    while True:
        last_exc: Exception | None = None
        for base, kw in candidates:
            try:
                record = await _try_register(payload, base, kw)
                master_base = base
                tls_kw      = kw
                last_exc    = None
                break
            except Exception as exc:
                last_exc = exc
        if last_exc is None:
            assigned_id = record["config_id"]
            worker_state.worker_id = record["id"]
            worker_state.worker_config_id = assigned_id
            worker_state.master_url = master_base
            if not _worker_config_id:
                set_setting("worker_id", assigned_id)
                payload["config_id"] = assigned_id
                _worker_config_id = assigned_id
                print(f"[worker] assigned id {assigned_id!r} by master")
            print(f"[worker] registered as worker-{record['id']} ({assigned_id!r})")
            break
        attempt += 1
        wait = min(5 * attempt, 30)
        print(f"[worker] registration failed (attempt {attempt}): {last_exc} — retrying in {wait}s")
        await asyncio.sleep(wait)

    async def _reregister_loop() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                async with httpx.AsyncClient(timeout=10, **tls_kw) as client:
                    r = await client.post(f"{master_base}/workers", json=payload)
                    r.raise_for_status()
                    record = r.json()
                worker_state.worker_id = record["id"]
            except Exception as exc:
                print(f"[worker] re-registration failed: {exc}")

    if worker_state.output_dir:
        await asyncio.gather(
            poller_loop(
                master_url=worker_state.master_url,
                worker_config_id=worker_state.worker_config_id,
            ),
            _reregister_loop(),
        )
    else:
        await _reregister_loop()


def _reapply_config() -> None:
    """Recompute effective config from all layers and update _config and worker_state."""
    file_values = config_store.read_file_values(_config_path)
    env_values = config_store.read_env_values()
    db_values = config_store.read_db_values()
    effective, _ = config_store.compute_effective(file_values, env_values, db_values, _cli_values)
    config_store.apply_to_config(effective, _config)
    worker_state.ffmpeg_bin = _config.ffmpeg.bin
    worker_state.output_dir = _config.ffmpeg.output_dir
    worker_state.extra_args = _config.ffmpeg.extra_args
    worker_state.poll_interval = _config.worker.poll_interval
    worker_state.batch_size = _config.worker.batch_size
    worker_state.stall_timeout = _config.worker.stall_timeout
    worker_state.cancel_thresholds = _config.worker.cancel_thresholds
    worker_state.path_prefix = _config.path_prefix


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    worker_state.tls = _config.tls
    worker_state.presets = _config.ffmpeg.presets
    worker_state.available_encoders = _config.ffmpeg.available_encoders
    worker_state.replace_original = get_setting("replace_original") == "true"
    worker_state.cancel_thresholds = _config.worker.cancel_thresholds
    worker_state.error_threshold = _config.worker.error_threshold
    worker_state.stall_timeout = _config.worker.stall_timeout
    worker_state.ffmpeg_bin = _config.ffmpeg.bin
    worker_state.output_dir = _config.ffmpeg.output_dir
    worker_state.extra_args = _config.ffmpeg.extra_args
    worker_state.poll_interval = _config.worker.poll_interval
    worker_state.batch_size = _config.worker.batch_size
    worker_state.path_prefix = _config.path_prefix

    _default_encoder = worker_state.available_encoders[0] if worker_state.available_encoders else "libx265"

    if get_setting("ready"):
        worker_state.encoder = get_setting("encoder") or _default_encoder
    elif get_setting("first_run"):
        worker_state.encoder = _default_encoder
        if len(worker_state.available_encoders) == 1:
            set_setting("encoder", _default_encoder)
            set_setting("ready", "true")
            set_setting("first_run", "false")
            print(f"[worker] single encoder ({_default_encoder!r}) — auto-activating")
        else:
            worker_state.sleeping = True
            worker_state.unconfigured = True
            print("[worker] no stored configuration — starting in unconfigured state")
    else:
        worker_state.encoder = _default_encoder

    if worker_state.output_dir:
        recover()
        tasks.append(asyncio.create_task(worker_loop()))
    tasks.append(asyncio.create_task(sync_loop()))
    tasks.append(asyncio.create_task(_register_and_poll()))
    yield
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Packa Worker API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProgressOut(BaseModel):
    percent: float | None
    speed: float | None
    fps: float | None
    out_time: str | None
    eta_seconds: int | None
    bitrate: str | None
    source_size_bytes: int | None
    current_size_bytes: int | None
    projected_size_bytes: int | None
    stalled: bool = False


class WorkerStatus(BaseModel):
    state: str
    record_id: int | None
    queued: int
    progress: ProgressOut | None
    paused: bool
    drain: bool
    sleeping: bool
    disk_full: bool
    unconfigured: bool
    encoder: str
    available_encoders: list[str]
    encoder_labels: dict[str, str]
    current_file: str | None
    current_cmd: str | None
    batch_size: int
    replace_original: bool
    tls_enabled: bool = False
    petname: str = ""
    version: str = "dev"
    consecutive_errors: int = 0
    sleep_reason: str | None = None


class EncoderUpdate(BaseModel):
    encoder: str
    replace_original: bool | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/status", response_model=WorkerStatus)
def get_status(request: Request):
    _require_web_cert(request)
    p = worker_state.progress
    return WorkerStatus(
        state="processing" if worker_state.active else "idle",
        record_id=worker_state.record_id,
        queued=worker_state.queued,
        paused=worker_state.paused,
        drain=worker_state.drain,
        sleeping=worker_state.sleeping,
        disk_full=worker_state.disk_full,
        unconfigured=worker_state.unconfigured,
        encoder=worker_state.encoder,
        available_encoders=worker_state.available_encoders,
        encoder_labels={k: (f"{v.display_name} ({k})" if v.display_name else k) for k, v in worker_state.presets.items()},
        current_file=worker_state.current_file or None,
        current_cmd=worker_state.current_cmd or None,
        batch_size=worker_state.batch_size,
        replace_original=worker_state.replace_original,
        tls_enabled=_config.tls.enabled,
        petname=worker_state.petname,
        version=_VERSION,
        consecutive_errors=worker_state.consecutive_errors,
        sleep_reason=worker_state.sleep_reason,
        progress=ProgressOut(
            percent=p.percent,
            speed=p.speed,
            fps=p.fps,
            out_time=p.out_time,
            eta_seconds=p.eta_seconds,
            bitrate=p.bitrate,
            source_size_bytes=p.source_size_bytes,
            current_size_bytes=p.current_size_bytes,
            projected_size_bytes=p.projected_size_bytes,
            stalled=p.stalled,
        ) if p else None,
    )


@app.post("/files", response_model=FileRecordOut, status_code=201)
def submit_file(record: FileRecordCreate, request: Request, db: Session = Depends(get_db)):
    _require_web_cert(request)
    if _config.path_prefix:
        record = record.model_copy(update={"file_path": _config.path_prefix + record.file_path})
    db_record = crud.create_file_record(db, record)
    if _config.ffmpeg.output_dir:
        worker_state.enqueue(Job(record_id=db_record.id, file_path=db_record.file_path))
        print(f"[api] record {db_record.id} queued (queue size: {worker_state.queued})")
    return db_record


@app.get("/files", response_model=list[FileRecordOut])
def list_files(request: Request, status: FileStatus | None = None, db: Session = Depends(get_db)):
    _require_web_cert(request)
    return crud.get_all_records(db, status=status)


@app.get("/files/{record_id}", response_model=FileRecordOut)
def get_file(record_id: int, request: Request, db: Session = Depends(get_db)):
    _require_web_cert(request)
    record = crud.get_file_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.delete("/files/{record_id}", status_code=204)
def delete_file(record_id: int, db: Session = Depends(get_db)):
    if (worker_state.active
            and worker_state.record_id == record_id
            and worker_state.proc is not None):
        if worker_state.paused:
            worker_state.proc.send_signal(signal.SIGCONT)
        worker_state.cancel_reason = "user"
        worker_state.proc.terminate()
        worker_state.drain = False
    else:
        worker_state.cancel_queued(record_id)
    if not crud.delete_file_record(db, record_id):
        raise HTTPException(status_code=404, detail="Record not found")


@app.patch("/files/{record_id}/status", response_model=FileRecordOut)
def update_status(record_id: int, body: StatusUpdate, request: Request, db: Session = Depends(get_db)):
    _require_web_cert(request)
    record = crud.update_status(db, record_id, body.status)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.post("/jobs/push", status_code=202)
def push_jobs(jobs: list[FileRecordCreate], request: Request, db: Session = Depends(get_db)):
    _require_web_cert(request)
    queued = 0
    for job in jobs:
        full_path = (_config.path_prefix + job.file_path) if _config.path_prefix else job.file_path
        record = None
        try:
            record = crud.create_file_record(db, job.model_copy(update={"file_path": full_path, "worker_id": _worker_config_id}))
        except IntegrityError:
            db.rollback()
            record = crud.get_file_record(db, job.id)
            if record:
                record.status = FileStatus.PENDING
                record.pid = None
                record.started_at = None
                record.finished_at = None
                record.cancel_reason = None
                db.commit()
        if record and _config.ffmpeg.output_dir:
            worker_state.enqueue(Job(record_id=record.id, file_path=record.file_path))
            queued += 1
    print(f"[api] pushed {queued} job(s) to queue")
    return {"queued": queued}


@app.post("/conversion/stop")
def stop_conversion(request: Request):
    _require_web_cert(request)
    if not worker_state.active or worker_state.proc is None:
        raise HTTPException(status_code=409, detail="No conversion running")
    if worker_state.paused:
        worker_state.proc.send_signal(signal.SIGCONT)
    worker_state.cancel_reason = "user"
    worker_state.proc.terminate()
    worker_state.drain = False


@app.post("/conversion/pause")
def pause_conversion(request: Request):
    _require_web_cert(request)
    if not worker_state.active or worker_state.proc is None:
        raise HTTPException(status_code=409, detail="No conversion running")
    if worker_state.paused:
        raise HTTPException(status_code=409, detail="Already paused")
    worker_state.proc.send_signal(signal.SIGSTOP)
    worker_state.paused = True


@app.post("/conversion/resume")
def resume_conversion(request: Request):
    _require_web_cert(request)
    if worker_state.paused:
        if worker_state.proc is not None:
            worker_state.proc.send_signal(signal.SIGCONT)
        worker_state.paused = False
    worker_state.drain = False


@app.post("/conversion/drain")
def drain_conversion(request: Request):
    _require_web_cert(request)
    worker_state.drain = True


@app.post("/conversion/sleep")
def sleep_conversion(request: Request):
    _require_web_cert(request)
    worker_state.sleeping = True
    worker_state.drain = False


@app.post("/conversion/wake")
def wake_conversion(request: Request):
    _require_web_cert(request)
    worker_state.sleeping = False
    worker_state.drain = False
    worker_state.disk_full = False
    worker_state.consecutive_errors = 0
    worker_state.sleep_reason = None


# ---------------------------------------------------------------------------
# Encoder settings
# ---------------------------------------------------------------------------

@app.get("/settings")
def get_settings(request: Request):
    _require_web_cert(request)
    return {"encoder": worker_state.encoder, "batch_size": worker_state.batch_size, "replace_original": worker_state.replace_original}


@app.post("/settings")
def update_settings(body: EncoderUpdate, request: Request):
    _require_web_cert(request)
    if body.encoder not in worker_state.presets:
        raise HTTPException(
            status_code=400,
            detail=f"encoder must be one of: {', '.join(sorted(worker_state.presets))}",
        )
    worker_state.encoder = body.encoder
    set_setting("encoder", body.encoder)
    set_setting("ready", "true")
    set_setting("first_run", "false")
    if body.replace_original is not None:
        worker_state.replace_original = body.replace_original
        set_setting("replace_original", "true" if body.replace_original else "false")
    if worker_state.unconfigured:
        worker_state.unconfigured = False
        print(f"[worker] activated with encoder={body.encoder!r} — sleeping until woken")
    else:
        print(f"[worker] encoder changed to {body.encoder!r}")
    return {"encoder": worker_state.encoder}


# ---------------------------------------------------------------------------
# Config (layered: default < file < env < db < cli)
# ---------------------------------------------------------------------------

class ConfigValueUpdate(BaseModel):
    value: object


class ConfigRestore(BaseModel):
    source: str  # "file" | "env" | "default"


class TlsBootstrapRequest(BaseModel):
    token: str


@app.post("/tls/bootstrap")
async def tls_bootstrap(body: TlsBootstrapRequest, request: Request):
    _require_web_cert(request)
    """Fetch a TLS cert bundle from master using a bootstrap token. Restart required after."""
    if get_setting("tls.cert") and get_setting("tls.key") and get_setting("tls.ca"):
        raise HTTPException(
            status_code=409,
            detail="Worker is already bootstrapped. Remove stored TLS settings and restart to re-bootstrap.",
        )
    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            r = await client.post(
                f"https://{_config.master_host}:{_config.master_port}/bootstrap",
                json={"token": body.token, "cn": _worker_config_id or "worker",
                      "sans": [s for s in [_advertise_host] if s]},
            )
            r.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach master for TLS bootstrap: {exc}")
    bundle = r.json()
    set_setting("tls.cert", bundle["cert_pem"])
    set_setting("tls.key",  bundle["key_pem"])
    set_setting("tls.ca",   bundle["ca_pem"])
    _config.tls.cert_pem = bundle["cert_pem"]
    _config.tls.key_pem  = bundle["key_pem"]
    _config.tls.ca_pem   = bundle["ca_pem"]
    worker_state.tls = _config.tls
    print("[worker] TLS onboarded — restarting")
    _schedule_restart()
    return {"ok": True}


def _peer_has_cert(request: Request) -> bool:
    """Return True if the request arrived with a CA-signed client certificate."""
    try:
        ssl_obj = request.scope["extensions"]["tls"]["ssl_object"]
        return ssl_obj is not None and ssl_obj.getpeercert() is not None
    except (KeyError, TypeError, AttributeError):
        return False


def _peer_cn(request: Request) -> str | None:
    """Return the CN from the peer's client cert, or None if absent or no TLS."""
    try:
        ssl_obj = request.scope["extensions"]["tls"]["ssl_object"]
        cert = ssl_obj.getpeercert() if ssl_obj else None
        if not cert:
            return None
        for rdn in cert.get("subject", ()):
            for key, val in rdn:
                if key == "commonName":
                    return val
    except (KeyError, TypeError, AttributeError):
        pass
    return None


def _require_localhost_or_mtls(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1"):
        return
    if _peer_has_cert(request):
        return
    raise HTTPException(status_code=403, detail="Requires mTLS or localhost")


def _require_web_cert(request: Request) -> None:
    """Require CN=web client cert. Loopback and non-TLS connections are exempt."""
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1"):
        return
    cn = _peer_cn(request)
    if cn is None:
        return  # non-TLS deployment — no cert enforcement
    if cn != "web":
        raise HTTPException(status_code=403, detail="Web certificate required")


@app.post("/restart")
def restart_worker(request: Request):
    _require_web_cert(request)
    _schedule_restart()
    return {"ok": True}


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


@app.get("/config")
def get_worker_config(request: Request):
    _require_web_cert(request)
    file_values = config_store.read_file_values(_config_path)
    env_values = config_store.read_env_values()
    db_values = config_store.read_db_values()
    effective, sources = config_store.compute_effective(
        file_values, env_values, db_values, _cli_values,
    )
    return {
        "fields": config_store.fields_for_api(),
        "values": effective,
        "sources": sources,
        "file": file_values,
        "env": env_values,
        "db": db_values,
        "cli": _cli_values,
        "config_file": _config_path,
    }


@app.patch("/config/{key}")
def update_worker_config(key: str, body: ConfigValueUpdate, request: Request):
    _require_web_cert(request)
    fld = config_store.field(key)
    if fld is None:
        raise HTTPException(status_code=404, detail=f"Unknown key {key!r}")
    try:
        config_store.set_db_value(key, body.value)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid value for {key!r}: {exc}")
    _reapply_config()
    print(f"[worker] config {key!r} set via DB (requires_restart={fld.requires_restart})")
    return {"ok": True, "requires_restart": fld.requires_restart}


@app.delete("/config/{key}")
def clear_worker_config(key: str, request: Request):
    _require_web_cert(request)
    fld = config_store.field(key)
    if fld is None:
        raise HTTPException(status_code=404, detail=f"Unknown key {key!r}")
    removed = config_store.delete_db_value(key)
    _reapply_config()
    print(f"[worker] config {key!r} DB override {'cleared' if removed else 'was already unset'}")
    return {"ok": True, "cleared": removed, "requires_restart": fld.requires_restart}


@app.post("/config/{key}/restore")
def restore_worker_config(key: str, body: ConfigRestore, request: Request):
    _require_web_cert(request)
    fld = config_store.field(key)
    if fld is None:
        raise HTTPException(status_code=404, detail=f"Unknown key {key!r}")
    source = body.source
    if source == "file":
        vals = config_store.read_file_values(_config_path)
    elif source == "env":
        vals = config_store.read_env_values()
    elif source == "default":
        vals = config_store.default_values()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown source {source!r}")
    if key not in vals:
        raise HTTPException(status_code=404, detail=f"No value for {key!r} in {source}")
    config_store.set_db_value(key, vals[key])
    _reapply_config()
    print(f"[worker] config {key!r} restored from {source}")
    return {"ok": True, "value": vals[key], "requires_restart": fld.requires_restart}
