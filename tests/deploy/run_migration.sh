#!/usr/bin/env bash
# Regression tests for the migration-script fixes:
#   M1 releases exclude bulk pilot data but keep the reference JSON
#   M2 pilot-data copy is verified by checksum for completeness (a dropped file aborts)
#   M3 locally-modified reference files are preserved (and backed up), never silently lost
#   M4 a disk-space preflight blocks a migration that would not fit
#   M5 both service units use the release dir and shared-data config
# Isolated; no systemd, no network (fast fake venv).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/common.sh"
MIG="$REPO/deploy/migrate_to_releases.sh"
ROOTS="$(mktemp -d)"; trap 'rm -rf "$ROOTS"' EXIT

# build a realistic flat install at $1 (code + reference JSON + bulk pilot data)
build_flat() {
  local d="$1"; mkdir -p "$d/data/gallery" "$d/data/flights"
  tar -C "$REPO" --exclude=./.git --exclude=./.venv --exclude='./acars_client/build' \
    --exclude=./__pycache__ --exclude=./data --exclude=./releases --exclude=./shared \
    --exclude=./current --exclude=./previous -cf - . | tar -C "$d" -xf -
  local f; for f in $REF_FILES; do [ -f "$REPO/data/$f" ] && cp "$REPO/data/$f" "$d/data/$f"; done
  head -c 2097152 /dev/zero > "$d/data/bigpilot.bin"      # 2 MiB stand-in for bulk pilot data
  printf 'logbook'  > "$d/data/logbook.db"
  printf 'settings' > "$d/data/settings.json"
  printf 'upload'   > "$d/data/gallery/keep.txt"
  printf 'flight'   > "$d/data/flights/PAC0001.pkl"
}
# run migrate with a clean, flat-scoped env (fast venv, plenty of simulated disk unless overridden)
mig() { env -u PAC_SHARED_DATA -u PAC_RELEASES_DIR -u PAC_HEALTH_URL \
          PAC_DEPLOY_ROOT="$1" PAC_VENV_BUILD='mkdir -p "$PAC_RELEASE/.venv"' \
          PAC_DISK_AVAIL_KB="${MIG_AVAIL:-99999999}" "${@:2}"; }
relstamp() { basename "$(readlink -f "$1/current")"; }

# ---- M1 ---------------------------------------------------------------------
sect "M1 releases exclude bulk pilot data, keep reference JSON"
F1="$ROOTS/m1"; build_flat "$F1"
mig "$F1" bash "$MIG" --apply >"$ROOTS/m1.log" 2>&1 || { bad "migrate --apply failed"; sed 's/^/    /' "$ROOTS/m1.log"; }
REL="$F1/releases/$(relstamp "$F1")"
[ -f "$REL/data/missions.json" ] && ok "release ships reference JSON (missions.json)" || bad "release missing reference JSON"
[ ! -f "$REL/data/bigpilot.bin" ] && [ ! -f "$REL/data/logbook.db" ] && [ ! -d "$REL/data/gallery" ] && ok "release does NOT contain bulk pilot data" || bad "bulk pilot data leaked into the release"
[ -f "$F1/shared/data/bigpilot.bin" ] && [ -f "$F1/shared/data/logbook.db" ] && [ -f "$F1/shared/data/gallery/keep.txt" ] && [ -f "$F1/shared/data/flights/PAC0001.pkl" ] && ok "all pilot data is in shared/data" || bad "pilot data missing from shared/data"
[ ! -f "$F1/shared/data/missions.json" ] && ok "reference JSON is not duplicated into shared/data" || bad "reference JSON leaked into shared/data"

# ---- M2 ---------------------------------------------------------------------
sect "M2 pilot-data copy is checksum-verified for completeness"
F2="$ROOTS/m2"; build_flat "$F2"
# simulate a dropped file during the copy; the completeness check must abort
if PAC_MIGRATE_SKIP_FILE=logbook.db mig "$F2" bash "$MIG" --apply >"$ROOTS/m2.log" 2>&1; then
  bad "migration succeeded despite a missing pilot file"
else ok "migration aborted when a pilot file was not copied"; fi
grep -q "MISSING in shared/data: logbook.db" "$ROOTS/m2.log" && ok "the missing file was reported by name" || bad "missing file not reported"
[ ! -L "$F2/current" ] && ok "no release was adopted after the failed verification" || bad "a release was adopted despite incomplete copy"
[ -f "$F2/data/logbook.db" ] && ok "original pilot data left untouched" || bad "original data was affected"

# ---- M3 ---------------------------------------------------------------------
sect "M3 locally-modified reference files are preserved, not silently overwritten"
F3="$ROOTS/m3"; build_flat "$F3"
( cd "$F3" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm init )
printf '\n{"LOCAL_EDIT":true}\n' >> "$F3/data/missions.json"     # server-side edit, uncommitted
LOCAL_SHA="$(sha256sum "$F3/data/missions.json" | cut -d' ' -f1)"
mig "$F3" bash "$MIG" --apply >"$ROOTS/m3.log" 2>&1 || { bad "migrate --apply failed"; sed 's/^/    /' "$ROOTS/m3.log"; }
REL3="$F3/releases/$(relstamp "$F3")"
[ "$(sha256sum "$REL3/data/missions.json" | cut -d' ' -f1)" = "$LOCAL_SHA" ] && ok "release ships the LOCAL missions.json, not the committed one" || bad "local edit to missions.json was lost in the release"
BK3="$(ls -d "$F3"/reference-local-backup-* 2>/dev/null | head -1)"
[ -n "$BK3" ] && [ "$(sha256sum "$BK3/missions.json" | cut -d' ' -f1)" = "$LOCAL_SHA" ] && ok "a backup of the local reference file was kept" || bad "no backup of the local reference file"
grep -q "PRESERVED locally-modified reference file(s):.*missions.json" "$ROOTS/m3.log" && ok "the local modification was reported" || bad "local modification not reported"

# ---- M4 ---------------------------------------------------------------------
sect "M4 disk-space preflight blocks a migration that will not fit"
F4="$ROOTS/m4"; build_flat "$F4"
if MIG_AVAIL=1000 mig "$F4" bash "$MIG" --apply >"$ROOTS/m4.log" 2>&1; then
  bad "migration proceeded despite insufficient disk space"
else ok "migration aborted on insufficient disk space"; fi
grep -qi "not enough disk space" "$ROOTS/m4.log" && ok "the disk shortfall was reported" || bad "disk shortfall not reported"
[ ! -d "$F4/shared" ] && [ ! -L "$F4/current" ] && ok "nothing was created when the preflight failed" || bad "artifacts left after a failed preflight"
# and it proceeds when space is sufficient
MIG_AVAIL=9000000 mig "$F4" bash "$MIG" --apply >"$ROOTS/m4b.log" 2>&1 && ok "migration proceeds when space is sufficient" || { bad "migration failed with ample disk"; sed 's/^/    /' "$ROOTS/m4b.log"; }

# ---- M5 ---------------------------------------------------------------------
sect "M5 both service units use the release dir and shared-data config"
U="$REPO/deploy/pac.service"; D="$REPO/deploy/pac-discord.service"
grep -q 'WorkingDirectory=/home/pac/pac-acars/current' "$U" && grep -q 'ExecStart=/home/pac/pac-acars/current/.venv/bin/python app.py' "$U" && grep -q 'Environment=PAC_DATA_DIR=/home/pac/pac-acars/shared/data' "$U" && ok "pac.service: release dir + venv + shared data" || bad "pac.service misconfigured"
grep -q 'WorkingDirectory=/home/pac/pac-acars/current' "$D" && grep -q 'ExecStart=/home/pac/pac-acars/current/.venv/bin/python discord_bot.py' "$D" && grep -q 'Environment=PAC_DATA_DIR=/home/pac/pac-acars/shared/data' "$D" && ok "pac-discord.service: release dir + venv + shared data" || bad "pac-discord.service misconfigured"

printf '\n==== %d passed, %d failed ====\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
