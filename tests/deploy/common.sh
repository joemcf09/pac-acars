#!/usr/bin/env bash
# Shared helpers for the deploy/rollback test runners (run.sh, run_findings.sh).
# Sourced, not executed.
DTD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$DTD/../.." && pwd)"
REF_FILES="airports.json conflict_zones_shapes.json fleet.json missions.json partners.json routes.json runways.json"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
bad()  { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
sect() { printf '\n== %s ==\n' "$*"; }

# mk_pkg <out.zip> [sabotage] -- a deployable package: top-level pac-acars/ with
# code + reference data. "sabotage" makes the release fail at startup.
mk_pkg() {
  local out="$1" mode="${2:-}" stage; stage="$(mktemp -d)"
  mkdir -p "$stage/pac-acars"
  tar -C "$REPO" --exclude=./.git --exclude=./.venv --exclude='./acars_client/build' \
    --exclude=./__pycache__ --exclude=./data --exclude=./releases --exclude=./shared \
    --exclude=./current --exclude=./previous -cf - . | tar -C "$stage/pac-acars" -xf -
  mkdir -p "$stage/pac-acars/data"
  local f; for f in $REF_FILES; do [ -f "$REPO/data/$f" ] && cp "$REPO/data/$f" "$stage/pac-acars/data/$f"; done
  if [ "$mode" = "sabotage" ]; then
    local app="$stage/pac-acars/app.py"
    { printf 'import sys; sys.exit(3)  # deliberately broken release for the test\n'; cat "$app"; } > "$app.tmp"
    mv "$app.tmp" "$app"
  fi
  ( cd "$stage" && zip -qr "$out" pac-acars ); rm -rf "$stage"
}

cur_stamp() { basename "$(readlink -f "$PAC_DEPLOY_ROOT/current" 2>/dev/null)" 2>/dev/null; }
has_current() { [ -L "$PAC_DEPLOY_ROOT/current" ]; }
http_200()  { [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PAC_PORT/up" 2>/dev/null)" = "200" ]; }

# setup_env <root> <port> -- export everything the deploy scripts and svc.sh need
setup_env() {
  export PAC_DEPLOY_ROOT="$1" PAC_SHARED_DATA="$1/shared/data" PAC_RELEASES_DIR="$1/releases"
  export PAC_HEALTH_URL="http://127.0.0.1:$2/up" PAC_HEALTH_TIMEOUT="${PAC_HEALTH_TIMEOUT:-10}" PAC_KEEP_RELEASES=5
  export PAC_SVC_RESTART="$DTD/svc.sh restart" PAC_SVC_STOP="$DTD/svc.sh stop" PAC_SVC_ISACTIVE="$DTD/svc.sh is-active"
  export PAC_SVC_DISCORD_RESTART=""
  export PAC_VENV_BUILD='mkdir -p "$PAC_RELEASE/.venv/bin" && : > "$PAC_RELEASE/.venv/ok"'
  export PAC_PORT="$2" SVC_PIDFILE="$1/pac.pid" SVC_LOG="$1/app.log" PAC_BACKUP_DIR="$1/backups"
  mkdir -p "$PAC_RELEASES_DIR" "$PAC_SHARED_DATA"
}

stop_app() { "$DTD/svc.sh" stop 2>/dev/null; }
