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

# Verify every file under $1 exists under $2 with an identical checksum. Used to
# prove the undo copied pilot data back intact BEFORE anything is removed.
verify_tree() {
  [ "${PAC_UNDO_FORCE_MISMATCH:-0}" = 1 ] && return 1   # test hook
  python3 - "$1" "$2" <<'PY'
import hashlib, os, sys
src, dst = sys.argv[1], sys.argv[2]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""): h.update(b)
    return h.hexdigest()
bad = 0
for root, _, files in os.walk(src):
    for fn in files:
        s = os.path.join(root, fn); rel = os.path.relpath(s, src); d = os.path.join(dst, rel)
        if not os.path.exists(d) or sha(s) != sha(d):
            print("  mismatch:", rel); bad += 1
sys.exit(1 if bad else 0)
PY
}

if [ "$UNDO" = 1 ]; then
  step undo "Reverting the release layout back to a flat install"
  CUR="$(current_target)"
  [ -n "$CUR" ] || die "nothing to undo: no current release symlink at $CURRENT_LINK"
  [ -d "$SHARED_DATA" ] || die "nothing to undo: no $SHARED_DATA"
  mkdir -p "$ROOT/data"
  # 1) restore the code (overlay copy; this never touches pilot data)
  cp -a "$CUR/." "$ROOT/" || die "could not copy the code back; NOTHING was removed, your data is safe at $SHARED_DATA"
  rm -rf "$ROOT/.venv"            # a fresh venv is rebuilt on the next deploy
  # 2) COPY pilot data back (never move: the source copy stays intact)
  cp -a "$SHARED_DATA/." "$ROOT/data/" || die "could not copy pilot data back; NOTHING was removed, your data is safe at $SHARED_DATA"
  # 3) verify the copy byte-for-byte BEFORE removing anything
  if ! verify_tree "$SHARED_DATA" "$ROOT/data"; then
    die "verification failed: the copied-back pilot data does not match (see above).
  NOTHING was removed. Your only good copy is safe at $SHARED_DATA. Resolve this before retrying."
  fi
  log "verified: all pilot data copied back intact"
  # 4) only now retire the new layout, and even then KEEP the data copy (rename, never delete)
  rm -f "$CURRENT_LINK" "$PREVIOUS_LINK"
  rm -rf "$RELEASES_DIR"
  KEPT="$ROOT/shared.undone-$(date -u +%Y%m%d-%H%M%S)"
  mv "$ROOT/shared" "$KEPT"
  printf '\nUndo complete and verified. Pilot data is back at %s/data.\n' "$ROOT"
  printf 'A safety copy of the pilot data remains at %s (delete it only once you are satisfied).\n' "$KEPT"
  printf 'Re-point the service at WorkingDirectory=%s and remove PAC_DATA_DIR.\n\n' "$ROOT"
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
