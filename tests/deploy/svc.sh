#!/usr/bin/env bash
# A stand-in for `systemctl ... pac`, used only by the deploy/rollback test
# harness. It starts the real app from the $PAC_DEPLOY_ROOT/current release
# against the shared data dir, on a test port, in dev mode (no waitress needed),
# tracking it with a pidfile. This lets the production deploy scripts run
# unchanged against a throwaway install, with no systemd and no network.
#
# Env in: PAC_DEPLOY_ROOT, PAC_SHARED_DATA, PAC_PORT, SVC_PIDFILE, SVC_LOG
set -uo pipefail

ROOT="${PAC_DEPLOY_ROOT:?}"
DATA="${PAC_SHARED_DATA:?}"
PORT="${PAC_PORT:?}"
PIDFILE="${SVC_PIDFILE:?}"
LOG="${SVC_LOG:?}"

running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

stop() {
  if running; then kill "$(cat "$PIDFILE")" 2>/dev/null; fi
  # wait for it to actually exit and free the port
  for _ in $(seq 1 20); do running || break; sleep 0.2; done
  rm -f "$PIDFILE"
}

start() {
  # run from the current release symlink, exactly as the service would
  ( cd "$ROOT/current" && PAC_DATA_DIR="$DATA" PAC_HOST=127.0.0.1 PAC_PORT="$PORT" \
      exec python3 app.py ) >>"$LOG" 2>&1 &
  echo $! > "$PIDFILE"
}

case "${1:-}" in
  start)      start ;;
  stop)       stop ;;
  restart)    stop; start ;;
  is-active)  running && exit 0 || exit 1 ;;
  *) echo "usage: svc.sh {start|stop|restart|is-active}" >&2; exit 2 ;;
esac
