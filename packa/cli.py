import sys
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="packa",
        description="Distributed video transcoding system",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── master ────────────────────────────────────────────────────────────────
    p_master = sub.add_parser("master", help="Run the master node")
    p_master.add_argument("--bind", default=None)
    p_master.add_argument("--api-port", type=int, default=None)
    p_master.add_argument("--config", default=None)

    # ── worker ────────────────────────────────────────────────────────────────
    p_worker = sub.add_parser("worker", help="Run or control a worker node")
    p_worker.add_argument(
        "action",
        nargs="?",
        choices=["start", "info", "stop", "pause", "drain", "wake"],
        default="start",
        metavar="ACTION",
        help="start (default) | info | stop | pause | drain | wake",
    )
    p_worker.add_argument("--bind", default=None)
    p_worker.add_argument("--api-port", type=int, default=None)
    p_worker.add_argument("--master-host", default=None)
    p_worker.add_argument("--master-port", type=int, default=None)
    p_worker.add_argument("--advertise-host", default=None)
    p_worker.add_argument("--insecure-no-tls", action="store_true")
    p_worker.add_argument("--config", default=None)
    p_worker.add_argument(
        "--host",
        default=None,
        help="Worker host for control commands (default: from config or localhost)",
    )
    p_worker.add_argument(
        "--port",
        type=int,
        default=None,
        help="Worker port for control commands (default: from config or 8000)",
    )

    # ── web ───────────────────────────────────────────────────────────────────
    p_web = sub.add_parser("web", help="Run the web dashboard")
    p_web.add_argument("--bind", default=None)
    p_web.add_argument("--port", type=int, default=None)
    p_web.add_argument("--master-host", default=None)
    p_web.add_argument("--master-port", type=int, default=None)
    p_web.add_argument("--insecure-no-auth", action="store_true")
    p_web.add_argument("--config", default=None)

    # ── bootstrap-token ───────────────────────────────────────────────────────
    p_bt = sub.add_parser("bootstrap-token", help="Generate a new TLS bootstrap token")
    p_bt.add_argument("--master-host", default=None, help="Master host (default: localhost)")
    p_bt.add_argument("--master-port", type=int, default=None, help="Master API port (default: 9000)")
    p_bt.add_argument("--config", default=None)

    # ── clearcertificates ─────────────────────────────────────────────────────
    p_cc = sub.add_parser("clearcertificates", help="Clear bootstrapped TLS certificates from a node's database")
    p_cc.add_argument("--worker", action="store_true", help="Target the worker node (worker.db)")
    p_cc.add_argument("--master", action="store_true", help="Target the master node (master.db)")
    p_cc.add_argument("--web", action="store_true", help="Target the web node (web.db)")
    p_cc.add_argument(
        "--db",
        default=None,
        help="Explicit path to the SQLite database file",
    )

    args = parser.parse_args()

    if args.command == "master":
        from master.master import main as _main
        sys.argv = [sys.argv[0]]
        if args.config:
            sys.argv += ["--config", args.config]
        if args.bind:
            sys.argv += ["--bind", args.bind]
        if args.api_port:
            sys.argv += ["--api-port", str(args.api_port)]
        _main()

    elif args.command == "worker":
        if args.action in (None, "start"):
            from worker.main import main as _main
            sys.argv = [sys.argv[0]]
            if args.config:
                sys.argv += ["--config", args.config]
            if args.bind:
                sys.argv += ["--bind", args.bind]
            if args.api_port:
                sys.argv += ["--api-port", str(args.api_port)]
            if args.master_host:
                sys.argv += ["--master-host", args.master_host]
            if args.master_port:
                sys.argv += ["--master-port", str(args.master_port)]
            if args.advertise_host:
                sys.argv += ["--advertise-host", args.advertise_host]
            if args.insecure_no_tls:
                sys.argv += ["--insecure-no-tls"]
            _main()
        else:
            _cmd_worker_control(args)

    elif args.command == "web":
        from web.main import main as _main
        sys.argv = [sys.argv[0]]
        if args.config:
            sys.argv += ["--config", args.config]
        if args.bind:
            sys.argv += ["--bind", args.bind]
        if args.port:
            sys.argv += ["--port", str(args.port)]
        if args.master_host:
            sys.argv += ["--master-host", args.master_host]
        if args.master_port:
            sys.argv += ["--master-port", str(args.master_port)]
        if args.insecure_no_auth:
            sys.argv += ["--insecure-no-auth"]
        _main()

    elif args.command == "bootstrap-token":
        _cmd_bootstrap_token(args)

    elif args.command == "clearcertificates":
        _cmd_clearcertificates(args)


def _cmd_worker_control(args) -> None:
    import httpx
    from shared.config import load_worker

    config_path = args.config or None
    try:
        config = load_worker(config_path)
    except FileNotFoundError:
        config = None

    host = args.host or (config.bind if config else "localhost")
    if host in ("0.0.0.0", "any", ""):
        host = "localhost"
    port = args.port or (config.api_port if config else 8000)
    base = f"http://{host}:{port}"

    action = args.action

    try:
        if action == "info":
            r = httpx.get(f"{base}/status", timeout=5)
            r.raise_for_status()
            d = r.json()
            state = d.get("state", "unknown")
            if d.get("sleeping"):
                state = "sleeping"
            elif d.get("drain"):
                state = "draining"
            elif d.get("paused"):
                state = "paused"
            queued = d.get("queued", 0)
            record_id = d.get("record_id")
            encoder = d.get("encoder", "")
            petname = d.get("petname", "")
            version = d.get("version", "dev")
            errors = d.get("consecutive_errors", 0)

            label = petname or f"worker@{host}:{port}"
            print(f"{label}  v{version}")
            print(f"  state:   {state}")
            if record_id is not None:
                print(f"  job:     #{record_id}")
            print(f"  queued:  {queued}")
            print(f"  encoder: {encoder}")
            if errors:
                print(f"  errors:  {errors} consecutive")
            prog = d.get("progress")
            if prog and prog.get("percent") is not None:
                pct = prog["percent"]
                fps = prog.get("fps") or ""
                speed = prog.get("speed") or ""
                parts = [f"{pct:.1f}%"]
                if fps:
                    parts.append(f"{fps} fps")
                if speed:
                    parts.append(f"{speed}x")
                print(f"  progress: {', '.join(parts)}")

        elif action == "stop":
            r = httpx.post(f"{base}/conversion/stop", timeout=5)
            r.raise_for_status()
            print("stopped")

        elif action == "pause":
            r = httpx.post(f"{base}/conversion/pause", timeout=5)
            r.raise_for_status()
            print("paused")

        elif action == "drain":
            r = httpx.post(f"{base}/conversion/drain", timeout=5)
            r.raise_for_status()
            print("draining")

        elif action == "wake":
            r = httpx.post(f"{base}/conversion/wake", timeout=5)
            r.raise_for_status()
            print("awake")

    except httpx.ConnectError:
        print(f"error: could not connect to worker at {host}:{port}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"error: {e.response.status_code} {e.response.text}", file=sys.stderr)
        sys.exit(1)


def _cmd_clearcertificates(args) -> None:
    import sqlite3
    from pathlib import Path

    # Determine target node
    flag_count = sum([args.worker, args.master, args.web])
    if flag_count > 1:
        print("error: specify only one of --worker, --master, --web", file=sys.stderr)
        sys.exit(1)

    if args.db:
        _clear_certs_from_db(Path(args.db), node="custom")
        return

    db_map = {
        "worker": Path("worker.db"),
        "master": Path("master.db"),
        "web": Path("web.db"),
    }

    if flag_count == 1:
        if args.worker:
            node = "worker"
        elif args.master:
            node = "master"
        else:
            node = "web"
        db_path = db_map[node]
        if not db_path.exists():
            print(f"error: {db_path} not found", file=sys.stderr)
            sys.exit(1)
    else:
        # Auto-detect
        found = [(n, p) for n, p in db_map.items() if p.exists()]
        if not found:
            print("error: no node databases found in current directory (worker.db / master.db / web.db)", file=sys.stderr)
            sys.exit(1)
        if len(found) > 1:
            names = " / ".join(f"--{n}" for n, _ in found)
            print(f"error: multiple node databases found — specify {names}", file=sys.stderr)
            sys.exit(1)
        node, db_path = found[0]

    resp = input(f"Clear TLS certificates from {db_path} ({node})? [y/N] ").strip().lower()
    if resp != "y":
        print("aborted")
        return

    _clear_certs_from_db(db_path, node)


def _clear_certs_from_db(db_path, node: str) -> None:
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        if node == "master":
            cur.execute("DELETE FROM master_settings WHERE key LIKE 'tls.%'")
            table = "master_settings"
        elif node == "web":
            cur.execute("DELETE FROM web_settings WHERE key IN ('tls.cert', 'tls.key', 'tls.ca')")
            table = "web_settings"
        else:
            cur.execute("DELETE FROM worker_settings WHERE key IN ('tls.cert', 'tls.key', 'tls.ca')")
            table = "worker_settings"
        count = cur.rowcount
        conn.commit()
        print(f"cleared {count} TLS entr{'y' if count == 1 else 'ies'} from {table}")
    finally:
        conn.close()


def _cmd_bootstrap_token(args) -> None:
    import httpx
    from shared.config import load_master

    config = load_master(args.config)
    host = args.master_host or "localhost"
    port = args.master_port or config.api_port

    url = f"http://{host}:{port}/tls/token"
    try:
        r = httpx.post(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        print(data.get("token", ""))
        expires = data.get("expires_at", "")
        if expires:
            print(f"expires: {expires}", file=sys.stderr)
    except httpx.ConnectError:
        print(f"error: could not connect to master at {host}:{port}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"error: {e.response.status_code} {e.response.text}", file=sys.stderr)
        sys.exit(1)
