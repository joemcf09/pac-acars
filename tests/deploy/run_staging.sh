#!/usr/bin/env bash
# Finding 4: production-equivalent staging test. Unlike run.sh / run_findings.sh
# (which use a fast fake venv and the container python), this exercises:
#   - a REAL virtualenv built from the pinned requirements (pip install)
#   - the migrate_to_releases.sh path (flat -> release layout) end to end
#   - the app run from the release's OWN venv python
#   - validation of the systemd unit
# It needs network (PyPI) and takes a bit longer. No live server is touched.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/common.sh"

ROOTS="$(mktemp -d)"
trap 'stop_app; rm -rf "$ROOTS"' EXIT
UP="$REPO/deploy/update.sh"; RB="$REPO/deploy/rollback.sh"; MIG="$REPO/deploy/migrate_to_releases.sh"
FLAT="$ROOTS/stg"; PORT=5112

# ---- validate the systemd unit --------------------------------------------
sect "S0 systemd unit is valid and release-aware"
UNIT="$REPO/deploy/pac.service"
if command -v systemd-analyze >/dev/null 2>&1; then
  # Validate directive SYNTAX on a path-substituted copy, so the check does not
  # fail merely because the production paths/user do not exist in this sandbox.
  # The real paths and values are checked statically below.
  TMPU="$ROOTS/pac-check.service"   # systemd-analyze requires a .service suffix
  sed -e 's#^WorkingDirectory=.*#WorkingDirectory=/tmp#' \
      -e 's#^ExecStart=.*#ExecStart=/bin/true#' \
      -e 's#^ReadWritePaths=.*#ReadWritePaths=/tmp#' \
      -e 's#^User=.*#User=root#' \
      -e 's#^Environment=PAC_DATA_DIR=.*#Environment=PAC_DATA_DIR=/tmp#' "$UNIT" > "$TMPU"
  systemd-analyze verify "$TMPU" >/dev/null 2>&1 && ok "systemd-analyze verify passed (unit directives valid)" || bad "systemd-analyze verify failed on unit syntax"
else
  ok "systemd-analyze not present; checking the unit statically"
fi
grep -q 'WorkingDirectory=/home/pac/pac-acars/current' "$UNIT" && ok "unit runs from the current release symlink" || bad "unit WorkingDirectory not the current symlink"
grep -q 'ExecStart=/home/pac/pac-acars/current/.venv/bin/python app.py' "$UNIT" && ok "unit runs the release's own venv python" || bad "unit ExecStart not the release venv"
grep -q 'Environment=PAC_DATA_DIR=/home/pac/pac-acars/shared/data' "$UNIT" && ok "unit points PAC_DATA_DIR at shared/data" || bad "unit missing PAC_DATA_DIR"
grep -q 'ReadWritePaths=/home/pac/pac-acars/shared/data' "$UNIT" && ok "unit makes only shared/data writable" || bad "unit ReadWritePaths wrong"
DUNIT="$REPO/deploy/pac-discord.service"
grep -q 'WorkingDirectory=/home/pac/pac-acars/current' "$DUNIT" && ok "discord unit runs from the current release" || bad "discord unit not release-aware"
grep -q 'ExecStart=/home/pac/pac-acars/current/.venv/bin/python discord_bot.py' "$DUNIT" && ok "discord unit uses the release venv (deploys update the bot too)" || bad "discord unit ExecStart not the release venv"

# ---- build a flat install and migrate it with a REAL venv -------------------
sect "S1 migrate a flat install to the release layout (real venv)"
mkdir -p "$FLAT/data"
tar -C "$REPO" --exclude=./.git --exclude=./.venv --exclude='./acars_client/build' \
  --exclude=./__pycache__ --exclude=./data --exclude=./releases --exclude=./shared \
  --exclude=./current --exclude=./previous -cf - . | tar -C "$FLAT" -xf -
for f in $REF_FILES; do [ -f "$REPO/data/$f" ] && cp "$REPO/data/$f" "$FLAT/data/$f"; done
echo "pilot-sentinel" > "$FLAT/data/PILOT_ONLY.txt"
# real venv: do NOT set PAC_VENV_BUILD
env -u PAC_VENV_BUILD -u PAC_SHARED_DATA -u PAC_RELEASES_DIR PAC_DEPLOY_ROOT="$FLAT" \
  bash "$MIG" --apply >"$ROOTS/mig.log" 2>&1 && ok "migrate --apply completed" || { bad "migrate --apply failed"; sed 's/^/    /' "$ROOTS/mig.log"; }
REL="$(readlink -f "$FLAT/current")"
[ -x "$REL/.venv/bin/python" ] && ok "release has a real venv" || bad "no real venv in the release"
"$REL/.venv/bin/python" -c "import flask, waitress" 2>/dev/null && ok "release venv has the pinned deps installed" || bad "release venv missing deps"
[ -f "$FLAT/shared/data/PILOT_ONLY.txt" ] && ok "pilot data moved to shared/data" || bad "pilot data not in shared/data"

# ---- run and deploy against the migrated layout, real venv python -----------
sect "S2 deploy + rollback on the migrated layout, run from the release venv"
export PAC_DEPLOY_ROOT="$FLAT" PAC_SHARED_DATA="$FLAT/shared/data" PAC_RELEASES_DIR="$FLAT/releases"
export PAC_HEALTH_URL="http://127.0.0.1:$PORT/up" PAC_HEALTH_TIMEOUT=45 PAC_KEEP_RELEASES=5
export PAC_SVC_RESTART="$HERE/svc.sh restart" PAC_SVC_STOP="$HERE/svc.sh stop" PAC_SVC_ISACTIVE="$HERE/svc.sh is-active"
export PAC_SVC_DISCORD_RESTART=""
export PAC_PORT="$PORT" SVC_PIDFILE="$FLAT/pac.pid" SVC_LOG="$FLAT/app.log" PAC_BACKUP_DIR="$FLAT/backups"
export PAC_SVC_PYTHON="$FLAT/current/.venv/bin/python"   # production-equivalent: the release's own venv
unset PAC_VENV_BUILD                                      # real venv builds on deploy too

"$HERE/svc.sh" restart; sleep 1
MIGRATED="$(cur_stamp)"
http_200 && ok "migrated release serves /up under its own venv python" || bad "migrated release not healthy"
python3 "$HERE/datatool.py" seed "$PAC_SHARED_DATA" >/dev/null
# a real deploy (builds a real venv, flips, health-gates)
mk_pkg "$ROOTS/stg2.zip"
if "$UP" "$ROOTS/stg2.zip" >"$ROOTS/dep.log" 2>&1; then
  http_200 && ok "real-venv deploy came up healthy" || bad "deploy not healthy"
  [ "$(cur_stamp)" != "$MIGRATED" ] && ok "current advanced" || bad "current did not advance"
  python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data intact across real deploy" || bad "pilot data changed"
else bad "real-venv deploy failed"; sed 's/^/    /' "$ROOTS/dep.log"; fi
# rollback to the migrated release
if "$RB" "$MIGRATED" >"$ROOTS/rb.log" 2>&1; then
  [ "$(cur_stamp)" = "$MIGRATED" ] && ok "rolled back to the migrated release" || bad "rollback target wrong"
  http_200 && ok "rolled-back release healthy under its venv" || bad "rolled-back release not healthy"
  python3 "$HERE/datatool.py" verify "$PAC_SHARED_DATA" >/dev/null 2>&1 && ok "pilot data intact across rollback" || bad "pilot data changed on rollback"
else bad "rollback failed"; sed 's/^/    /' "$ROOTS/rb.log"; fi
stop_app

printf '\n==== %d passed, %d failed ====\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
