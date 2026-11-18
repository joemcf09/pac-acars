#!/usr/bin/env bash
# End-to-end test of the versioned-release deploy and automatic rollback, run in
# an isolated throwaway directory. No systemd, no live server, no network: the
# production deploy/rollback scripts run unchanged against a fake service that
# launches the real app on a test port.
#
# Covers:
#   T1 first deploy comes up healthy
#   T2 second deploy; pilot data survives the deploy
#   T3 additive DB migration is tolerated (backward-compatible rollback)
#   T4 a release that will not start is auto-rolled-back to the previous one
#   T5 a dependency-install failure aborts BEFORE any switch (old release serving)
#   T6 manual rollback to an explicit earlier release
#   T7 all pilot data (reservation, flight-state, upload, sentinel) intact throughout
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PORT="${PAC_TEST_PORT:-5094}"
WORK="$(mktemp -d)"
ROOT="$WORK/srv"
export PAC_DEPLOY_ROOT="$ROOT"
export PAC_SHARED_DATA="$ROOT/shared/data"
export PAC_RELEASES_DIR="$ROOT/releases"
export PAC_HEALTH_URL="http://127.0.0.1:$PORT/up"
export PAC_HEALTH_TIMEOUT=10
export PAC_KEEP_RELEASES=5
export PAC_SVC_RESTART="$HERE/svc.sh restart"
export PAC_SVC_ISACTIVE="$HERE/svc.sh is-active"
# a fast stand-in for building a venv (the real one is exercised in production;
# T5 drives its failure path deterministically)
export PAC_VENV_BUILD='mkdir -p "$PAC_RELEASE/.venv/bin" && : > "$PAC_RELEASE/.venv/ok"'
# env the fake service reads
export PAC_PORT="$PORT"
export SVC_PIDFILE="$ROOT/pac.pid"
export SVC_LOG="$ROOT/app.log"
export PAC_BACKUP_DIR="$ROOT/backups"

REF_FILES="airports.json conflict_zones_shapes.json fleet.json missions.json partners.json routes.json runways.json"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
bad()  { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
head() { printf '\n== %s ==\n' "$*"; }

cleanup() { "$HERE/svc.sh" stop 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

# Build a deployable package (top-level pac-acars/ with code + reference data).
# $1 = output zip, $2 = optional "sabotage" to make the release fail to start.
mk_pkg() {
  local out="$1" mode="${2:-}" stage="$WORK/stage"
  rm -rf "$stage"; mkdir -p "$stage/pac-acars"
  tar -C "$REPO" \
    --exclude=./.git --exclude=./.venv --exclude='./acars_client/build' \
    --exclude=./__pycache__ --exclude=./data --exclude=./releases \
    --exclude=./shared --exclude=./current --exclude=./previous \
    -cf - . | tar -C "$stage/pac-acars" -xf -
  mkdir -p "$stage/pac-acars/data"
  for f in $REF_FILES; do
    [ -f "$REPO/data/$f" ] && cp "$REPO/data/$f" "$stage/pac-acars/data/$f"
  done
  if [ "$mode" = "sabotage" ]; then
    # fail at startup (before the server ever binds), the way a bad import or a
    # config error would, so the health gate sees an unhealthy release
    local app="$stage/pac-acars/app.py"
    { printf 'import sys; sys.exit(3)  # deliberately broken release for the rollback test\n'; cat "$app"; } > "$app.tmp"
    mv "$app.tmp" "$app"
  fi
  ( cd "$stage" && zip -qr "$out" pac-acars )
}

cur_stamp() { basename "$(readlink -f "$ROOT/current")"; }
http_200()  { [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/up" 2>/dev/null)" = "200" ]; }

mkdir -p "$ROOT/releases" "$PAC_SHARED_DATA"
PKG_A="$WORK/a.zip"; PKG_B="$WORK/b.zip"; PKG_C="$WORK/c.zip"; PKG_D="$WORK/d.zip"
mk_pkg "$PKG_A"; mk_pkg "$PKG_B"; mk_pkg "$PKG_C" sabotage; mk_pkg "$PKG_D"

# ---- T1: first deploy -------------------------------------------------------
head "T1 first deploy"
if "$HERE/../../deploy/update.sh" "$PKG_A" >"$WORK/t1.log" 2>&1; then
  http_200 && ok "first deploy healthy, /up 200 (release $(cur_stamp))" || bad "/up not 200 after first deploy"
else
  bad "first deploy exited non-zero"; sed 's/^/    /' "$WORK/t1.log"
fi
STAMP_A="$(cur_stamp)"

# seed pilot data now that the DB exists, then baseline-verify
python3 "$HERE/datatool.py" seed "$PAC_SHARED_DATA" >/dev/null
python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data seeded and verifiable" || bad "seed/verify failed"

# ---- T2: second deploy, data survives --------------------------------------
head "T2 second deploy, data survives"
if "$HERE/../../deploy/update.sh" "$PKG_B" >"$WORK/t2.log" 2>&1; then
  http_200 && ok "second deploy healthy (release $(cur_stamp))" || bad "/up not 200 after second deploy"
  [ "$(cur_stamp)" != "$STAMP_A" ] && ok "current advanced to a new release" || bad "current did not change"
  [ "$(basename "$(readlink -f "$ROOT/previous")")" = "$STAMP_A" ] && ok "previous points at the prior release" || bad "previous not set to prior release"
  python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "all pilot data intact across deploy" || bad "pilot data changed across deploy"
else
  bad "second deploy exited non-zero"; sed 's/^/    /' "$WORK/t2.log"
fi
STAMP_B="$(cur_stamp)"

# ---- T3: additive migration tolerated --------------------------------------
head "T3 additive DB migration tolerated"
python3 "$HERE/datatool.py" add-col "$PAC_SHARED_DATA" hardening_probe >/dev/null
"$HERE/svc.sh" restart; sleep 2
if http_200; then ok "app serves /up after an additive column was added"; else bad "app unhealthy after additive migration"; fi
python3 "$HERE/datatool.py" read "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "DB still reads (pilots + reservation)" || bad "DB read failed after migration"

# ---- T4: broken release auto-rollback --------------------------------------
head "T4 broken release is auto-rolled-back"
if "$HERE/../../deploy/update.sh" "$PKG_C" >"$WORK/t4.log" 2>&1; then
  bad "deploy of a broken release unexpectedly succeeded"
else
  ok "deploy of a broken release failed (as it should)"
fi
http_200 && ok "site is up after auto-rollback" || bad "site down after auto-rollback"
[ "$(cur_stamp)" = "$STAMP_B" ] && ok "current rolled back to the last good release" || bad "current is $(cur_stamp), expected $STAMP_B"
python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data intact after auto-rollback" || bad "pilot data changed during failed deploy"

# ---- T5: dependency-install failure aborts before switch --------------------
head "T5 dependency-install failure aborts before any switch"
BEFORE="$(cur_stamp)"
if PAC_VENV_BUILD='echo "simulated pip failure" >&2; exit 1' \
    "$HERE/../../deploy/update.sh" "$PKG_D" >"$WORK/t5.log" 2>&1; then
  bad "deploy with failing dependency install unexpectedly succeeded"
else
  ok "deploy aborted when dependency install failed"
fi
[ "$(cur_stamp)" = "$BEFORE" ] && ok "current unchanged (old release still serving)" || bad "current changed despite dep failure"
http_200 && ok "site still up on the previous release" || bad "site down after aborted deploy"

# ---- T6: manual rollback to an explicit release ----------------------------
head "T6 manual rollback to an explicit earlier release"
if "$HERE/../../deploy/rollback.sh" "$STAMP_A" >"$WORK/t6.log" 2>&1; then
  [ "$(cur_stamp)" = "$STAMP_A" ] && ok "rolled back to the chosen release $STAMP_A" || bad "current is $(cur_stamp), expected $STAMP_A"
  http_200 && ok "site healthy after manual rollback" || bad "site down after manual rollback"
  python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data intact after manual rollback" || bad "pilot data changed during manual rollback"
else
  bad "manual rollback exited non-zero"; sed 's/^/    /' "$WORK/t6.log"
fi
"$HERE/../../deploy/rollback.sh" --list >/dev/null 2>&1 && ok "rollback --list works" || bad "rollback --list failed"

# ---- summary ---------------------------------------------------------------
printf '\n==== %d passed, %d failed ====\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
