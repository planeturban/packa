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
    p_worker = sub.add_parser("worker", help="Run a worker node")
    p_worker.add_argument("--bind", default=None)
    p_worker.add_argument("--api-port", type=int, default=None)
    p_worker.add_argument("--master-host", default=None)
    p_worker.add_argument("--master-port", type=int, default=None)
    p_worker.add_argument("--advertise-host", default=None)
    p_worker.add_argument("--bootstrap-token", default=None)
    p_worker.add_argument("--config", default=None)

    # ── web ───────────────────────────────────────────────────────────────────
    p_web = sub.add_parser("web", help="Run the web dashboard")
    p_web.add_argument("--bind", default=None)
    p_web.add_argument("--port", type=int, default=None)
    p_web.add_argument("--master-host", default=None)
    p_web.add_argument("--master-port", type=int, default=None)
    p_web.add_argument("--config", default=None)

    # ── bootstrap-token ───────────────────────────────────────────────────────
    p_bt = sub.add_parser("bootstrap-token", help="Generate a new TLS bootstrap token")
    p_bt.add_argument("--master-host", default=None, help="Master host (default: localhost)")
    p_bt.add_argument("--master-port", type=int, default=None, help="Master API port (default: 9000)")
    p_bt.add_argument("--config", default=None)

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
        if args.bootstrap_token:
            sys.argv += ["--bootstrap-token", args.bootstrap_token]
        _main()

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
        _main()

    elif args.command == "bootstrap-token":
        _cmd_bootstrap_token(args)


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
