#!/usr/bin/env bash
# Roll PAC back to a previous release. An atomic symlink flip and a restart; your
# pilot data is never touched (it lives outside every release, under shared/data).
#
#   rollback.sh --list            show the releases on the server and which is live
#   rollback.sh                   roll back to the previous release
#   rollback.sh <stamp>           roll back to a specific release (from --list)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$HERE/lib.sh"

cmd="${1:-}"

if [ "$cmd" = "--list" ] || [ "$cmd" = "-l" ]; then
  cur="$(current_target)"; prev="$(previous_target)"
  printf 'Releases (newest first):\n'
  while read -r name; do
    [ -n "$name" ] || continue
    path="$RELEASES_DIR/$name"
    mark=""
    [ "$path" = "$cur" ]  && mark="  <- current"
    [ "$path" = "$prev" ] && mark="$mark  <- previous"
    printf '  %s%s\n' "$name" "$mark"
  done < <(list_releases)
  exit 0
fi

# Pick the target: an explicit stamp, or the previous release.
if [ -n "$cmd" ]; then
  TARGET="$RELEASES_DIR/$cmd"
  [ -d "$TARGET" ] || die "no such release: $cmd  (try: rollback.sh --list)"
  TARGET="$(readlink -f "$TARGET")"
else
  TARGET="$(previous_target)"
  [ -n "$TARGET" ] || die "no previous release recorded. Pick one explicitly: rollback.sh --list"
fi

CUR="$(current_target)"
if [ "$TARGET" = "$CUR" ]; then
  die "that release is already live ($(basename "$TARGET")). Nothing to do."
fi

step 1 "Rolling back to $(basename "$TARGET")"
# the release we are leaving becomes the new 'previous', so a rollback is itself undoable
if [ -n "$CUR" ]; then set_link "$PREVIOUS_LINK" "$CUR"; fi
set_link "$CURRENT_LINK" "$TARGET"
log "current -> $(basename "$TARGET")"
svc_restart
if [ -n "$SVC_DISCORD_RESTART" ]; then eval "$SVC_DISCORD_RESTART" || true; fi

step 2 "Checking it is healthy"
if health_gate; then
  printf '\nDone. Rolled back to %s and running.\n\n' "$(basename "$TARGET")"
  exit 0
fi
die "the rollback target did not come up healthy. Pilot data is untouched at $SHARED_DATA.
  Pick another release with: $HERE/rollback.sh --list"
