#!/usr/bin/env bash
# ONE-TIME, REVERSIBLE migration from the old flat install to the versioned
# release layout that update.sh and rollback.sh use.
#
#   Before:  $ROOT/app.py, $ROOT/data/ (reference + pilot data mixed), $ROOT/.venv
#   After:   $ROOT/releases/<stamp>/ (code + reference JSON + .venv),
#            $ROOT/current -> it,  $ROOT/shared/data/ (pilot data; PAC_DATA_DIR)
#
# Dry-run by default: prints what it would do and changes nothing. Re-run with
# --apply to perform it; --undo reverts it. It refuses to run twice.
#
# Reference data (small; ships inside every release, read from the code tree):
#   airports.json conflict_zones_shapes.json fleet.json missions.json
#   partners.json routes.json runways.json
# Everything else under data/ is pilot data (can be multiple GB): it is COPIED to
# shared/data once and never shipped inside a release.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib.sh"

REFERENCE_FILES=(airports.json conflict_zones_shapes.json fleet.json missions.json partners.json routes.json runways.json)
# space the migration needs beyond the pilot-data copy: room for the release venv, plus headroom
VENV_MARGIN_KB="${PAC_VENV_MARGIN_KB:-614400}"     # ~600 MiB
SAFETY_KB="${PAC_DISK_SAFETY_KB:-1048576}"         # ~1 GiB

APPLY=0; UNDO=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  --undo)  UNDO=1 ;;
  ""|--dry-run) APPLY=0 ;;
  *) die "usage: migrate_to_releases.sh [--apply|--undo|--dry-run]" ;;
esac

run() { if [ "$APPLY" = 1 ] || [ "$UNDO" = 1 ]; then eval "$@"; else printf '  would: %s\n' "$*"; fi; }
gib() { awk "BEGIN{printf \"%.2f\", ${1:-0}/1048576}"; }
is_reference() { local b="$1" r; for r in "${REFERENCE_FILES[@]}"; do [ "$b" = "$r" ] && return 0; done; return 1; }

# Verify every file under $1 exists under $2 with an identical checksum (used by --undo).
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

# Verify EVERY required pilot file in <src> was copied to <dst> with a matching
# checksum. Top-level reference files (3rd arg, comma-separated) are expected NOT
# to be in <dst> and are skipped. This catches a dropped/missed file, not just a
# corrupted one.
verify_complete() {
  python3 - "$1" "$2" "$3" <<'PY'
import hashlib, os, sys
src, dst, excl = sys.argv[1], sys.argv[2], set(x for x in sys.argv[3].split(",") if x)
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""): h.update(b)
    return h.hexdigest()
missing = corrupt = checked = 0
for root, _, files in os.walk(src):
    for fn in files:
        s = os.path.join(root, fn); rel = os.path.relpath(s, src)
        if os.path.dirname(rel) == "" and fn in excl:   # a top-level reference file
            continue
        d = os.path.join(dst, rel); checked += 1
        if not os.path.exists(d):
            print("  MISSING in shared/data:", rel); missing += 1
        elif sha(s) != sha(d):
            print("  CORRUPT copy:", rel); corrupt += 1
print(f"  checked {checked} pilot file(s): {missing} missing, {corrupt} corrupt")
sys.exit(1 if (missing or corrupt) else 0)
PY
}

if [ "$UNDO" = 1 ]; then
  step undo "Reverting the release layout back to a flat install"
  CUR="$(current_target)"
  [ -n "$CUR" ] || die "nothing to undo: no current release symlink at $CURRENT_LINK"
  [ -d "$SHARED_DATA" ] || die "nothing to undo: no $SHARED_DATA"
  mkdir -p "$ROOT/data"
  cp -a "$CUR/." "$ROOT/" || die "could not copy the code back; NOTHING was removed, your data is safe at $SHARED_DATA"
  rm -rf "$ROOT/.venv"
  cp -a "$SHARED_DATA/." "$ROOT/data/" || die "could not copy pilot data back; NOTHING was removed, your data is safe at $SHARED_DATA"
  if ! verify_tree "$SHARED_DATA" "$ROOT/data"; then
    die "verification failed: the copied-back pilot data does not match (see above).
  NOTHING was removed. Your only good copy is safe at $SHARED_DATA. Resolve this before retrying."
  fi
  log "verified: all pilot data copied back intact"
  rm -f "$CURRENT_LINK" "$PREVIOUS_LINK"
  rm -rf "$RELEASES_DIR"
  KEPT="$ROOT/shared.undone-$(date -u +%Y%m%d-%H%M%S)"
  mv "$ROOT/shared" "$KEPT"
  printf '\nUndo complete and verified. Pilot data is back at %s/data.\n' "$ROOT"
  printf 'A safety copy of the pilot data remains at %s (delete it only once you are satisfied).\n' "$KEPT"
  printf 'Re-point both services at WorkingDirectory=%s and remove PAC_DATA_DIR.\n\n' "$ROOT"
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

# ---- disk-space preflight --------------------------------------------------
step 2 "Disk-space preflight"
# Use the same file walk for sizing and tar, including untracked runtime assets.
# Prune client build output by path: static/downloads can contain live installers.
cd "$ROOT"
# The initial layout is budgeted on ROOT's filesystem. Fail closed if a
# destination override or mount would make that free-space reading misleading.
for dest in "$RELEASES_DIR" "$SHARED_DATA"; do
  ancestor=$dest
  while [ ! -e "$ancestor" ]; do ancestor=$(dirname "$ancestor"); done
  [ "$(stat -Lc %d "$ancestor")" = "$(stat -c %d .)" ] ||
    die "destination $dest is on another filesystem; single-volume preflight cannot size it"
done
release_files() {
  find . \( -name .git -o -name __pycache__ -o -name '*.pyc' -o -name .pytest_cache \
    -o -name .cache -o -name .mypy_cache -o -name .ruff_cache -o -name node_modules \
    -o -path './acars_client/build' -o -path './acars_client/dist' -o -path './build' \
    -o -path './dist' -o -path './venv' -o -path './.venv' -o -path './data' \
    -o -path './shared' -o -path './shared.undone-*' -o -path './releases' \
    -o -path './reference-local-backup-*' -o -path './current' -o -path './previous' \
    \) -prune -o "$@"
}
# Budget logical sizes rounded per entry to a destination allocation block.
BLOCK=$(stat -f -c %S .)
size_kb() { awk -v b="$BLOCK" '{n += (int(($1+b-1)/b) + ($1==0))*b} END {printf "%.0f\n", n/1024}'; }
RELEASE_KB=$(release_files -printf '%s\n' | size_kb)
shopt -s dotglob nullglob
pilot_paths=()
DATA_COPY_KB=0
for p in "$ROOT"/data/*; do
  if is_reference "${p##*/}"; then
    kb=$(find "$p" -printf '%s\n' | size_kb)
    RELEASE_KB=$(( RELEASE_KB + kb ))
  else
    pilot_paths+=("$p")
    kb=$(find "$p" -printf '%s\n' | size_kb)
    DATA_COPY_KB=$(( DATA_COPY_KB + kb ))
  fi
done
MODREF=""
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  for r in "${REFERENCE_FILES[@]}"; do
    [ -f "$ROOT/data/$r" ] || continue
    if ! git -C "$ROOT" diff --quiet -- "data/$r" 2>/dev/null || ! git -C "$ROOT" diff --cached --quiet -- "data/$r" 2>/dev/null; then
      case " $MODREF " in *" $r "*) : ;; *) MODREF="$MODREF $r" ;; esac
    fi
  done
fi
BACKUP_KB=0
for r in $MODREF; do
  kb=$(find "$ROOT/data/$r" -printf '%s\n' | size_kb)
  BACKUP_KB=$(( BACKUP_KB + kb ))
done
for kib in "$VENV_MARGIN_KB" "$SAFETY_KB"; do
  [[ $kib =~ ^(0|[1-9][0-9]{0,14})$ ]] || die "invalid KiB budget: $kib"
done
VENV_KB=$VENV_MARGIN_KB
if [ -d "$ROOT/.venv" ]; then
  existing=$(du -sk --count-links "$ROOT/.venv" | cut -f1)
  if (( existing > VENV_KB )); then VENV_KB=$existing; fi
fi
NEED_KB=$(( DATA_COPY_KB + RELEASE_KB + BACKUP_KB + VENV_KB + SAFETY_KB ))
AVAIL_KB="${PAC_DISK_AVAIL_KB:-$(df -Pk "$ROOT" | awk 'NR==2{print $4}')}"
[[ $AVAIL_KB =~ ^(0|[1-9][0-9]{0,14})$ ]] || die "cannot determine available disk space"
log "KiB: pilot=$DATA_COPY_KB release=$RELEASE_KB reference-backup=$BACKUP_KB venv=$VENV_KB safety=$SAFETY_KB"
log "required=$NEED_KB KiB; available=$AVAIL_KB KiB"
if [ "$AVAIL_KB" -lt "$NEED_KB" ]; then
  die "not enough disk space to migrate safely: need ~$(gib "$NEED_KB") GiB, only ~$(gib "$AVAIL_KB") GiB free.
  Free space (or move the pre-migration backup off this server) and retry. Nothing was changed."
fi
log "disk preflight passed"

# ---- copy pilot data to shared/data (original is never touched) -------------
step 3 "Copy pilot data to shared/data"
run "mkdir -p '$SHARED_DATA'"
if [ -d "$ROOT/data" ]; then
  for p in "${pilot_paths[@]}"; do
    base="$(basename "$p")"
    is_reference "$base" && continue                       # reference files stay with the code
    [ "${PAC_MIGRATE_SKIP_FILE:-}" = "$base" ] && { log "TEST: skipping $base"; continue; }   # test hook
    if (( APPLY )); then cp -a -- "$p" "$SHARED_DATA/"; else log "would copy $p"; fi
  done
  # Completeness + integrity check: every required pilot file must be in shared/data.
  if [ "$APPLY" = 1 ] && ! verify_complete "$ROOT/data" "$SHARED_DATA" "$(IFS=,; echo "${REFERENCE_FILES[*]}")"; then
    die "the pilot-data copy to $SHARED_DATA is incomplete or corrupt (see above). Aborting.
  Your original data at $ROOT/data is untouched. Nothing was adopted. Resolve this and retry."
  fi
  [ "$APPLY" = 1 ] && log "verified: every pilot file copied to shared/data intact"
else
  log "no existing data/ dir; starting shared/data empty"
fi

# ---- build the release: code + reference JSON ONLY (no bulk pilot data) -----
step 4 "Create the first release (code + reference data only)"
run "mkdir -p '$NEW'"
# Exclude data/ (and the new scaffolding/venv) from the code copy, so GBs of pilot
# data are never duplicated into the release. tar is used (no rsync dependency).
if (( APPLY )); then
  release_files -print0 | tar --no-recursion --null -T - -cf - | tar -C "$NEW" -xf -
else
  log "would copy selected release files to $NEW"
fi
# Detect reference files with local (uncommitted) modifications, so server-side
# edits (e.g. a hand-edited missions.json) are preserved and never silently lost.
if [ -n "${MODREF# }" ]; then
  BK="$ROOT/reference-local-backup-$STAMP"
  run "mkdir -p '$BK'"
  for r in $MODREF; do run "cp -a '$ROOT/data/$r' '$BK/'"; done
  log "PRESERVED locally-modified reference file(s):${MODREF}"
  log "  backed up to $BK; the release ships your LOCAL versions, not the committed ones"
fi
# Ship the reference JSON (the working-tree copy, including any local edits) in the release.
run "mkdir -p '$NEW/data'"
for r in "${REFERENCE_FILES[@]}"; do
  [ -f "$ROOT/data/$r" ] && run "cp -a '$ROOT/data/$r' '$NEW/data/'"
done

step 5 "Build the release virtualenv"
if [ "$APPLY" = 1 ]; then build_venv "$NEW" || die "venv build failed; nothing was flipped"; else log "would: build venv at $NEW/.venv"; fi

step 6 "Point current at the first release"
run "ln -sfn '$NEW' '$CURRENT_LINK'"

cat <<EOF

Next: point BOTH services at the release layout and shared data.
  sudo cp $ROOT/current/deploy/pac.service         /etc/systemd/system/pac.service
  sudo cp $ROOT/current/deploy/pac-discord.service /etc/systemd/system/pac-discord.service
  sudo systemctl daemon-reload && sudo systemctl restart pac pac-discord
Both units run from $ROOT/current with PAC_DATA_DIR=$SHARED_DATA.
Verify /up, then keep deploying with current/deploy/update.sh.
To revert this migration before switching the services: $HERE/migrate_to_releases.sh --undo
EOF
[ "$APPLY" = 1 ] || printf '\n(DRY RUN: nothing was changed. Re-run with --apply to perform it.)\n\n'
