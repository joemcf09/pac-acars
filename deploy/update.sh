#!/usr/bin/env bash
# Update PAC from a zip you've uploaded, as a versioned release with an
# automatic health check and an automatic rollback if the new version does not
# come up healthy. Your pilot data is never touched.
#
#   scp pac-acars.zip pac@pac-va.com:~/     then on the server:
#   ~/pac-acars/current/deploy/update.sh ~/pac-acars.zip
#
# What it does, stopping (and rolling back) at the first failure:
#   1. Backs up pilot data first (belt and braces; data is never overwritten).
#   2. Unpacks the new code into releases/<stamp>/ (never over the running code).
#   3. Builds that release's own virtualenv and installs its deps. If this
#      fails, nothing is flipped: the old release keeps serving. (no downtime)
#   4. Atomically flips `current` to the new release and restarts the service.
#   5. Health-gates the new release on /up. If it does not come up healthy,
#      automatically flips `current` back to the previous release and restarts.
#   6. Prunes old releases, keeping the most recent few.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$HERE/lib.sh"

ZIP="${1:?Usage: update.sh /path/to/pac-acars.zip}"
[ -f "$ZIP" ] || die "zip not found: $ZIP"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
NEW="$RELEASES_DIR/$STAMP"
PREV_AT_START="$(current_target)"

mkdir -p "$RELEASES_DIR" "$SHARED_DATA"

step 1 "Backing up pilot data first"
# The backup is BLOCKING: if it fails, abort now, before anything changes. A
# deploy must never proceed without a verified backup in hand.
[ -x "$HERE/backup.sh" ] || die "backup.sh is missing or not executable; aborting before any change."
if ! PAC_DATA_DIR="$SHARED_DATA" "$HERE/backup.sh"; then
  die "backup failed; aborting before any change. Nothing was touched. See the output above."
fi

step 2 "Unpacking the new release into $STAMP"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$ZIP" -d "$TMP"
# the package holds a single top-level pac-acars/ folder
SRC="$TMP/pac-acars"
[ -d "$SRC" ] || die "the zip does not contain a top-level pac-acars/ folder"
[ -f "$SRC/app.py" ] || die "the package has no app.py"
mkdir -p "$NEW"
cp -a "$SRC/." "$NEW/"
# a release never carries pilot data or a stale venv
rm -rf "$NEW/.venv"

step 3 "Building this release's virtualenv and installing dependencies"
if ! build_venv "$NEW"; then
  rm -rf "$NEW"
  die "dependency install failed. Nothing was changed: the current release is still serving.
  Check the output above. The failed release was removed."
fi
log "dependencies installed"

step 4 "Switching to the new release"
# remember where to fall back to, then flip atomically
if [ -n "$PREV_AT_START" ]; then set_link "$PREVIOUS_LINK" "$PREV_AT_START"; fi
set_link "$CURRENT_LINK" "$NEW"
log "current -> $STAMP"
# A failed restart must NOT abort the script under set -e: fall through to the
# health gate so the automatic rollback runs.
svc_restart || log "the restart command reported failure; the health check will decide"
if [ -n "$SVC_DISCORD_RESTART" ]; then eval "$SVC_DISCORD_RESTART" || true; fi

step 5 "Checking the new release is healthy"
if health_gate; then
  log "healthy: $HEALTH_URL answered and the service is active"
  step 6 "Tidying old releases"
  prune_releases || true
  printf '\nDone. PAC updated to %s and running.\n\n' "$STAMP"
  exit 0
fi

# ---- the new release did not come up healthy -------------------------------
if [ -z "$PREV_AT_START" ]; then
  # Finding 5: first deploy, nothing to roll back to. Do NOT leave a broken
  # release wired up as 'current'. Stop the service, unset the symlink so the
  # next deploy starts clean, keep the failed release for inspection, and print
  # a safe recovery procedure. Pilot data was never touched.
  printf '\n  The first release did not pass the health check.\n' >&2
  svc_stop || log "could not stop the service (it may already be down)"
  rm -f "$CURRENT_LINK"
  die "first deploy failed and there is no previous release to roll back to.
  The service was stopped and 'current' was left unset, so nothing broken is wired up.
  Pilot data is untouched at $SHARED_DATA.
  Recovery: fix the package and re-run this deploy (it will start clean), or inspect
  the failed release at $NEW and the service logs. The failed release was NOT made current."
fi

printf '\n  The new release did not pass the health check. Rolling back automatically...\n' >&2
set_link "$CURRENT_LINK" "$PREV_AT_START"
log "current -> $(basename "$PREV_AT_START") (rolled back)"
svc_restart || log "the restart command reported failure; verifying health anyway"
if [ -n "$SVC_DISCORD_RESTART" ]; then eval "$SVC_DISCORD_RESTART" || true; fi
if health_gate; then
  log "the previous release is healthy again"
  log "the failed release is kept at $NEW for inspection"
  die "deploy failed and was rolled back to $(basename "$PREV_AT_START"). The site is up on the previous version.
  Pilot data was never touched. Inspect the failed release at $NEW."
else
  die "deploy failed AND the rollback did not come up healthy. Manual attention needed.
  Pilot data is untouched at $SHARED_DATA. Try: $HERE/rollback.sh --list"
fi
