#!/usr/bin/env bash
# The Discord bot reads data/bot_secret next to its own code, but the secret lives in shared/data (releases hold only
# reference data). Every release must therefore get a link to it, or the bot sits offline waiting for PAC.
# Isolated throwaway directory, no systemd, no network (same harness as run.sh).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/common.sh"

WORK="$(mktemp -d)"
setup_env "$WORK/srv" "${PAC_TEST_PORT:-5097}"
trap 'stop_app; rm -rf "$WORK"' EXIT

UP="$REPO/deploy/update.sh"
PKG_A="$WORK/a.zip"; PKG_B="$WORK/b.zip"
mk_pkg "$PKG_A"; mk_pkg "$PKG_B"
SECRET="test-bot-secret-0123456789"

# the secret exists in shared data before the first deploy, as it does in production
mkdir -p "$PAC_SHARED_DATA" && printf '%s' "$SECRET" > "$PAC_SHARED_DATA/bot_secret"

sect "B1 first release links the bot secret"
if "$UP" "$PKG_A" >"$WORK/b1.log" 2>&1; then
  ok "deploy healthy (release $(cur_stamp))"
  L="$PAC_DEPLOY_ROOT/current/data/bot_secret"
  [ -L "$L" ] && ok "current/data/bot_secret is a symlink" || bad "current/data/bot_secret is not a symlink"
  [ "$(readlink -f "$L")" = "$(readlink -f "$PAC_SHARED_DATA/bot_secret")" ] && ok "it points at shared/data/bot_secret" || bad "it points somewhere else"
  [ "$(cat "$L" 2>/dev/null)" = "$SECRET" ] && ok "the bot would read the real secret through it" || bad "the secret is not readable through the link"
else bad "first deploy exited non-zero"; sed 's/^/    /' "$WORK/b1.log"; fi
STAMP_A="$(cur_stamp)"

sect "B2 the next release gets its own link"
if "$UP" "$PKG_B" >"$WORK/b2.log" 2>&1; then
  [ "$(cur_stamp)" != "$STAMP_A" ] && ok "current advanced to a new release" || bad "current did not change"
  [ "$(cat "$PAC_DEPLOY_ROOT/current/data/bot_secret" 2>/dev/null)" = "$SECRET" ] && ok "new release reads the secret" || bad "new release cannot read the secret"
  [ "$(cat "$PAC_DEPLOY_ROOT/releases/$STAMP_A/data/bot_secret" 2>/dev/null)" = "$SECRET" ] && ok "the previous release still reads it (rollback keeps the bot working)" || bad "previous release lost the secret"
  [ "$(cat "$PAC_SHARED_DATA/bot_secret")" = "$SECRET" ] && ok "the shared secret itself is untouched" || bad "shared secret changed"
else bad "second deploy exited non-zero"; sed 's/^/    /' "$WORK/b2.log"; fi

printf '\n==== %d passed, %d failed ====\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
