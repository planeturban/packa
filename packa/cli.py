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

    args = parser.parse_args()

    if args.command == "master":
        from master.master import main as _main
        # Splice args back into sys.argv for the existing argparse in master.master
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
