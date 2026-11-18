#!/usr/bin/env bash
# ONE-TIME, REVERSIBLE migration from the old flat install to the versioned
# release layout that update.sh and rollback.sh use.
#
#   Before:  $ROOT/app.py, $ROOT/data/ (reference + pilot data mixed), $ROOT/.venv
#   After:   $ROOT/releases/<stamp>/ (the code + .venv),  $ROOT/current -> it,
#            $ROOT/shared/data/ (pilot data only; PAC_DATA_DIR points here)
#
# It is dry-run by default: it prints exactly what it would move and changes
# nothing. Re-run with --apply to perform it. It refuses to run twice.
#
# Reference data (ships with every release, stays in the code tree):
#   airports.json conflict_zones_shapes.json fleet.json missions.json
#   partners.json routes.json runways.json
# Everything else under data/ is pilot data and moves to shared/data.
#
# After --apply you must point the service at the new layout (the script prints
# the exact service lines). To undo before that, see --undo.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib.sh"

REFERENCE_FILES=(airports.json conflict_zones_shapes.json fleet.json missions.json partners.json routes.json runways.json)
APPLY=0; UNDO=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  --undo)  UNDO=1 ;;
  ""|--dry-run) APPLY=0 ;;
  *) die "usage: migrate_to_releases.sh [--apply|--undo|--dry-run]" ;;
esac

run() { if [ "$APPLY" = 1 ] || [ "$UNDO" = 1 ]; then eval "$@"; else printf '  would: %s\n' "$*"; fi; }

if [ "$UNDO" = 1 ]; then
  step undo "Reverting the release layout back to a flat install"
  CUR="$(current_target)"
  [ -n "$CUR" ] || die "nothing to undo: no current release symlink at $CURRENT_LINK"
  [ -d "$SHARED_DATA" ] || die "nothing to undo: no $SHARED_DATA"
  # move the code back to $ROOT, merge pilot data back into $ROOT/data
  run "cp -a '$CUR/.' '$ROOT/'"
  run "rm -rf '$ROOT/.venv'"           # a fresh venv is rebuilt by the old update.sh if needed
  run "cp -a '$SHARED_DATA/.' '$ROOT/data/'"
  run "rm -f '$CURRENT_LINK' '$PREVIOUS_LINK'"
  run "rm -rf '$RELEASES_DIR' '$ROOT/shared'"
  printf '\nUndo complete. Re-point the service at WorkingDirectory=%s and remove PAC_DATA_DIR.\n\n' "$ROOT"
  exit 0
fi

# ---- guard against running twice -------------------------------------------
if [ -L "$CURRENT_LINK" ] || [ -d "$RELEASES_DIR" ]; then
  die "already migrated: $CURRENT_LINK / $RELEASES_DIR exist. Use update.sh to deploy."
fi
[ -f "$ROOT/app.py" ] || die "this does not look like a flat PAC install (no $ROOT/app.py)"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
NEW="$RELEASES_DIR/$STAMP"
step 1 "Plan"
log "new release dir:   $NEW"
log "shared pilot data: $SHARED_DATA"
log "current ->         releases/$STAMP"

step 2 "Create the shared pilot-data directory and move pilot data into it"
run "mkdir -p '$SHARED_DATA'"
if [ -d "$ROOT/data" ]; then
  # move everything from data/ to shared/data EXCEPT the reference files
  while IFS= read -r -d '' p; do
    base="$(basename "$p")"
    skip=0
    for r in "${REFERENCE_FILES[@]}"; do [ "$base" = "$r" ] && skip=1; done
    [ "$skip" = 1 ] && continue
    run "mkdir -p '$SHARED_DATA'"
    run "cp -a '$p' '$SHARED_DATA/'"
  done < <(find "$ROOT/data" -mindepth 1 -maxdepth 1 -print0)
else
  log "no existing data/ dir; starting shared/data empty"
fi

step 3 "Create the first release from the current code"
run "mkdir -p '$NEW'"
# copy the code tree, excluding the new scaffolding, the venv and pilot data dir.
# tar is used (not rsync) so this has no extra dependency on any host.
run "tar -C '$ROOT' --exclude=./releases --exclude=./shared --exclude=./current --exclude=./previous --exclude=./.venv -cf - . | tar -C '$NEW' -xf -"

step 4 "Build the release virtualenv"
if [ "$APPLY" = 1 ]; then build_venv "$NEW" || die "venv build failed; nothing was flipped"; else log "would: build venv at $NEW/.venv"; fi

step 5 "Point current at the first release"
run "ln -sfn '$NEW' '$CURRENT_LINK'"

cat <<EOF

Next: update the systemd unit to run from the release and use shared data.
  WorkingDirectory=$ROOT/current
  ExecStart=$ROOT/current/.venv/bin/python app.py
  Environment=PAC_DATA_DIR=$SHARED_DATA
Then:  sudo systemctl daemon-reload && sudo systemctl restart pac
Verify /up, then keep deploying with current/deploy/update.sh.
To revert this migration before switching the service: $HERE/migrate_to_releases.sh --undo
EOF
[ "$APPLY" = 1 ] || printf '\n(DRY RUN: nothing was changed. Re-run with --apply to perform it.)\n\n'
