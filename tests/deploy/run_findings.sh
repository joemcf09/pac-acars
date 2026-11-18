#!/usr/bin/env bash
# Regression tests for the seven review findings on PR #3. Each runs in its own
# isolated root/port so they are independent. No systemd, no network.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/common.sh"

ROOTS="$(mktemp -d)"
trap 'stop_app; rm -rf "$ROOTS"' EXIT
UP="$REPO/deploy/update.sh"; RB="$REPO/deploy/rollback.sh"; MIG="$REPO/deploy/migrate_to_releases.sh"

# deploy one good release into the current env; leaves the app running
deploy_good() { local z="$ROOTS/good.$$.zip"; [ -f "$z" ] || mk_pkg "$z"; "$UP" "$z" >/dev/null 2>&1; }

# ---- F1: a failed svc_restart must not abort update.sh under set -e ----------
sect "F1 failed restart falls through to the health gate, not a premature exit"
setup_env "$ROOTS/f1" 5101
mk_pkg "$ROOTS/f1.zip"
# restart that still starts the app but reports non-zero; under the old bug set -e
# would kill update.sh right here, before the health gate
if PAC_SVC_RESTART="$HERE/svc.sh restart; false" "$UP" "$ROOTS/f1.zip" >"$ROOTS/f1.log" 2>&1; then
  ok "deploy completed despite a non-zero restart (no premature set -e exit)"
else bad "deploy aborted on a non-zero restart"; sed 's/^/    /' "$ROOTS/f1.log"; fi
http_200 && ok "site is up after the non-zero restart" || bad "site down"
stop_app

# ---- F2: migration --undo verifies before removing; never deletes only copy ---
sect "F2 migration --undo is non-destructive until the copy-back is verified"
FLAT="$ROOTS/flat"; mkdir -p "$FLAT/data"
tar -C "$REPO" --exclude=./.git --exclude=./.venv --exclude='./acars_client/build' \
  --exclude=./__pycache__ --exclude=./data --exclude=./releases --exclude=./shared \
  --exclude=./current --exclude=./previous -cf - . | tar -C "$FLAT" -xf -
for f in $REF_FILES; do [ -f "$REPO/data/$f" ] && cp "$REPO/data/$f" "$FLAT/data/$f"; done
echo "pilot-sentinel" > "$FLAT/data/PILOT_ONLY.txt"      # a pilot file that must survive
# run migrate with a CLEAN, FLAT-scoped environment (no leakage from earlier tests)
mig() { env -u PAC_SHARED_DATA -u PAC_RELEASES_DIR -u PAC_HEALTH_URL \
          PAC_DEPLOY_ROOT="$FLAT" PAC_VENV_BUILD='mkdir -p "$PAC_RELEASE/.venv"' "$@"; }
mig bash "$MIG" --apply >/dev/null 2>&1
[ -d "$FLAT/shared/data" ] && [ -f "$FLAT/shared/data/PILOT_ONLY.txt" ] && ok "migrate --apply moved pilot data to shared/data" || bad "migrate --apply did not set up shared/data"
# forced-mismatch undo must change nothing
mig env PAC_UNDO_FORCE_MISMATCH=1 bash "$MIG" --undo >"$ROOTS/f2bad.log" 2>&1 \
  && bad "undo succeeded despite a verification mismatch" || ok "undo aborted on a verification mismatch"
[ -f "$FLAT/shared/data/PILOT_ONLY.txt" ] && ok "the only good data copy was NOT deleted on a failed undo" || bad "data was removed on a failed undo"
[ -d "$FLAT/releases" ] && ok "release layout left intact after the aborted undo" || bad "release layout removed on a failed undo"
# clean undo verifies, restores, and keeps a safety copy (never deletes shared)
mig bash "$MIG" --undo >"$ROOTS/f2ok.log" 2>&1 && ok "clean undo succeeded" || { bad "clean undo failed"; sed 's/^/    /' "$ROOTS/f2ok.log"; }
[ -f "$FLAT/data/PILOT_ONLY.txt" ] && ok "pilot data restored to the flat layout (verified)" || bad "pilot data not restored"
ls -d "$FLAT"/shared.undone-* >/dev/null 2>&1 && ok "a safety copy of pilot data was kept (not deleted)" || bad "no safety copy kept"
[ ! -d "$FLAT/releases" ] && ok "release dir removed only after verification" || bad "release dir still present after undo"

# ---- F3: backup failures are blocking; archives are integrity-checked --------
sect "F3 backup failures block the deploy; archives are verified"
setup_env "$ROOTS/f3" 5103
deploy_good; python3 "$HERE/datatool.py" seed "$PAC_SHARED_DATA" >/dev/null
# a second deploy now has existing pilot data to back up and verify
"$UP" "$ROOTS/good.$$.zip" >/dev/null 2>&1
BK="$(ls -t "$PAC_BACKUP_DIR"/pac-*.tar.gz 2>/dev/null | head -1)"
[ -n "$BK" ] && gzip -t "$BK" 2>/dev/null && tar -tzf "$BK" >/dev/null 2>&1 && ok "a verified backup archive was produced on deploy" || bad "no valid backup archive produced"
BEFORE="$(cur_stamp)"
# make the backup fail (its output dir cannot be created: a file is in the way)
: > "$ROOTS/f3/blocker"
if PAC_BACKUP_DIR="$ROOTS/f3/blocker/sub" "$UP" "$ROOTS/good.$$.zip" >"$ROOTS/f3.log" 2>&1; then
  bad "deploy proceeded despite a failed backup"
else ok "deploy aborted when the backup failed"; fi
[ "$(cur_stamp)" = "$BEFORE" ] && ok "current unchanged after the aborted (backup-failed) deploy" || bad "current changed despite backup failure"
http_200 && ok "site still up after the aborted deploy" || bad "site down"
stop_app

# ---- F5: safe recovery on a failed FIRST deploy (no previous release) --------
sect "F5 first-deploy failure leaves nothing broken wired up, and recovers"
setup_env "$ROOTS/f5" 5105
mk_pkg "$ROOTS/f5bad.zip" sabotage
if "$UP" "$ROOTS/f5bad.zip" >"$ROOTS/f5.log" 2>&1; then bad "a broken first deploy reported success"
else ok "broken first deploy failed (as it should)"; fi
has_current && bad "a broken release was left wired up as current" || ok "current left unset (nothing broken is wired up)"
"$HERE/svc.sh" is-active && bad "service left running a broken release" || ok "service stopped after the failed first deploy"
# recovery: a good deploy now starts clean
mk_pkg "$ROOTS/f5good.zip"
if "$UP" "$ROOTS/f5good.zip" >"$ROOTS/f5b.log" 2>&1; then
  http_200 && has_current && ok "a subsequent good deploy recovers the site" || bad "recovery deploy did not come up"
else bad "recovery deploy failed"; sed 's/^/    /' "$ROOTS/f5b.log"; fi
stop_app

# ---- F6: manual rollback is transactional -----------------------------------
sect "F6 manual rollback restores the working release if the target is bad"
setup_env "$ROOTS/f6" 5106
mk_pkg "$ROOTS/f6a.zip"; mk_pkg "$ROOTS/f6b.zip"
"$UP" "$ROOTS/f6a.zip" >/dev/null 2>&1; GOOD_A="$(cur_stamp)"
"$UP" "$ROOTS/f6b.zip" >/dev/null 2>&1; GOOD_B="$(cur_stamp)"
# craft a broken release in place (copy current, sabotage its app.py)
BROKEN="$PAC_RELEASES_DIR/19990101-000000"
cp -a "$(readlink -f "$PAC_DEPLOY_ROOT/current")" "$BROKEN"
{ printf 'import sys; sys.exit(3)\n'; cat "$BROKEN/app.py"; } > "$BROKEN/app.py.tmp"; mv "$BROKEN/app.py.tmp" "$BROKEN/app.py"
if "$RB" 19990101-000000 >"$ROOTS/f6.log" 2>&1; then bad "rollback to a broken target reported success"
else ok "rollback to a broken target failed (as it should)"; fi
[ "$(cur_stamp)" = "$GOOD_B" ] && ok "the working release was automatically restored" || bad "current is $(cur_stamp), expected $GOOD_B"
http_200 && ok "site healthy after the transactional restore" || bad "site down after a failed rollback"
stop_app

# ---- F7: deploy.py SSH command cannot mask a failed update -------------------
sect "F7 the remote command returns the update's exit code, not the cleanup's"
P7="$ROOTS/f7"; mkdir -p "$P7/current/deploy" "$P7/releases"; : > "$P7/current/deploy/x.sh"
gen() { python3 -c "import sys; sys.path.insert(0,'$REPO/tools'); import deploy; print(deploy.remote_update_script(update_sh=sys.argv[1], zip_remote=sys.argv[2], pac_dir=sys.argv[3]))" "$1" "$2" "$P7"; }
# a failing update must make the whole command fail, even though rm/chown succeed
printf '#!/usr/bin/env bash\nexit 7\n' > "$P7/upfail.sh"; chmod +x "$P7/upfail.sh"
: > "$P7/zip"
bash -c "$(gen "$P7/upfail.sh" "$P7/zip")" >/dev/null 2>&1 && rc=0 || rc=$?
[ "$rc" -ne 0 ] && ok "a failed update makes the remote command fail (not masked by cleanup)" || bad "failed update was masked as success (rc=$rc)"
# a succeeding update returns success
printf '#!/usr/bin/env bash\nexit 0\n' > "$P7/upok.sh"; chmod +x "$P7/upok.sh"; : > "$P7/zip"
bash -c "$(gen "$P7/upok.sh" "$P7/zip")" >/dev/null 2>&1 && ok "a successful update returns success" || bad "successful update reported failure"

printf '\n==== %d passed, %d failed ====\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
