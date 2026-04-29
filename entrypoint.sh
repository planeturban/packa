#!/bin/sh
set -e

ROLE=${PACKA_ROLE:-${1:-master}}
CONFIG=${PACKA_CONFIG:-/data/packa.toml}
export PYTHONPATH=/app
cd /data

# When running as root (standalone Docker), drop to PUID/PGID before starting.
# When already non-root (k8s runAsUser, or explicit `docker run --user`), skip.
if [ "$(id -u)" = "0" ]; then
    PUID=${PUID:-1000}
    PGID=${PGID:-1000}
    if [ "${PUID}" != "0" ]; then
        groupadd -f -g "${PGID}" packa
        useradd -u "${PUID}" -g "${PGID}" -s /bin/sh -M -N packa 2>/dev/null || true
        chown packa:packa /data 2>/dev/null || true
        [ -d /output ] && chown packa:packa /output 2>/dev/null || true
        exec gosu packa "$0"
    fi
fi

case "$ROLE" in
  master)
    exec packa master --config "$CONFIG" --bind any ${PACKA_EXTRA_ARGS:-}
    ;;
  worker)
    exec packa worker --config "$CONFIG" --bind any ${PACKA_EXTRA_ARGS:-}
    ;;
  web)
    exec packa web --config "$CONFIG" --bind any ${PACKA_EXTRA_ARGS:-}
    ;;
  *)
    echo "Unknown role: $ROLE. Must be master, worker, or web." >&2
    exit 1
    ;;
esac
