#!/bin/sh
set -e

ROLE=${PACKA_ROLE:-${1:-master}}
CONFIG=${PACKA_CONFIG:-/data/packa.toml}

case "$ROLE" in
  master)
    exec python3 -m master.master --config "$CONFIG" --bind any
    ;;
  worker)
    exec python3 -m worker.main --config "$CONFIG" --bind any
    ;;
  web)
    exec python3 -m web.main --config "$CONFIG" --bind any
    ;;
  *)
    echo "Unknown role: $ROLE. Must be master, worker, or web." >&2
    exit 1
    ;;
esac
