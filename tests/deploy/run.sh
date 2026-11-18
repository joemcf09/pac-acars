#!/usr/bin/env bash
# Baseline end-to-end test of the versioned-release deploy and automatic rollback,
# in an isolated throwaway directory. No systemd, no live server, no network: the
# production scripts run unchanged against a fake service that launches the real
# app on a test port. (See run_findings.sh for the review-finding regressions,
# and run_staging.sh for the production-equivalent staging test.)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/common.sh"

WORK="$(mktemp -d)"
setup_env "$WORK/srv" "${PAC_TEST_PORT:-5094}"
trap 'stop_app; rm -rf "$WORK"' EXIT

UP="$REPO/deploy/update.sh"; RB="$REPO/deploy/rollback.sh"
PKG_A="$WORK/a.zip"; PKG_B="$WORK/b.zip"; PKG_C="$WORK/c.zip"
mk_pkg "$PKG_A"; mk_pkg "$PKG_B"; mk_pkg "$PKG_C" sabotage

sect "T1 first deploy"
if "$UP" "$PKG_A" >"$WORK/t1.log" 2>&1; then
  http_200 && ok "first deploy healthy, /up 200 (release $(cur_stamp))" || bad "/up not 200 after first deploy"
else bad "first deploy exited non-zero"; sed 's/^/    /' "$WORK/t1.log"; fi
STAMP_A="$(cur_stamp)"
python3 "$HERE/datatool.py" seed "$PAC_SHARED_DATA" >/dev/null
python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data seeded and verifiable" || bad "seed/verify failed"

sect "T2 second deploy, data survives"
if "$UP" "$PKG_B" >"$WORK/t2.log" 2>&1; then
  http_200 && ok "second deploy healthy (release $(cur_stamp))" || bad "/up not 200 after second deploy"
  [ "$(cur_stamp)" != "$STAMP_A" ] && ok "current advanced to a new release" || bad "current did not change"
  [ "$(basename "$(readlink -f "$PAC_DEPLOY_ROOT/previous")")" = "$STAMP_A" ] && ok "previous points at the prior release" || bad "previous not set"
  python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "all pilot data intact across deploy" || bad "pilot data changed"
else bad "second deploy exited non-zero"; sed 's/^/    /' "$WORK/t2.log"; fi
STAMP_B="$(cur_stamp)"

sect "T3 additive DB migration tolerated"
python3 "$HERE/datatool.py" add-col "$PAC_SHARED_DATA" hardening_probe >/dev/null
"$HERE/svc.sh" restart; sleep 2
http_200 && ok "app serves /up after an additive column was added" || bad "app unhealthy after additive migration"
python3 "$HERE/datatool.py" read "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "DB still reads (pilots + reservation)" || bad "DB read failed"

sect "T4 broken release is auto-rolled-back"
if "$UP" "$PKG_C" >"$WORK/t4.log" 2>&1; then bad "deploy of a broken release unexpectedly succeeded"
else ok "deploy of a broken release failed (as it should)"; fi
http_200 && ok "site is up after auto-rollback" || bad "site down after auto-rollback"
[ "$(cur_stamp)" = "$STAMP_B" ] && ok "current rolled back to the last good release" || bad "current is $(cur_stamp), expected $STAMP_B"
python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data intact after auto-rollback" || bad "pilot data changed"

sect "T5 dependency-install failure aborts before any switch"
BEFORE="$(cur_stamp)"
if PAC_VENV_BUILD='echo "simulated pip failure" >&2; exit 1' "$UP" "$WORK/a.zip" >"$WORK/t5.log" 2>&1; then
  bad "deploy with failing dependency install unexpectedly succeeded"
else ok "deploy aborted when dependency install failed"; fi
[ "$(cur_stamp)" = "$BEFORE" ] && ok "current unchanged (old release still serving)" || bad "current changed despite dep failure"
http_200 && ok "site still up on the previous release" || bad "site down after aborted deploy"

sect "T6 manual rollback to an explicit earlier release"
if "$RB" "$STAMP_A" >"$WORK/t6.log" 2>&1; then
  [ "$(cur_stamp)" = "$STAMP_A" ] && ok "rolled back to the chosen release $STAMP_A" || bad "current is $(cur_stamp), expected $STAMP_A"
  http_200 && ok "site healthy after manual rollback" || bad "site down after manual rollback"
  python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data intact after manual rollback" || bad "pilot data changed"
else bad "manual rollback exited non-zero"; sed 's/^/    /' "$WORK/t6.log"; fi
"$RB" --list >/dev/null 2>&1 && ok "rollback --list works" || bad "rollback --list failed"

printf '\n==== %d passed, %d failed ====\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
