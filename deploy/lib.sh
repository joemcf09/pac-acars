#!/usr/bin/env bash
# Shared helpers for PAC's versioned-release deploy and rollback.
# Sourced by update.sh and rollback.sh. Every setting is overridable by an
# environment variable so the same scripts run unchanged in production and can
# be exercised end to end by the test harness in an isolated directory.
#
# Production layout this assumes (created once by migrate_to_releases.sh):
#
#   $PAC_DEPLOY_ROOT/                 (default /home/pac/pac-acars)
#     releases/<stamp>/               a full program tree + its own .venv  (read-only at runtime)
#     current  -> releases/<stamp>    the symlink the systemd service runs from
#     previous -> releases/<stamp>    the last-good release, for an instant rollback
#     shared/data/                    ALL pilot data (PAC_DATA_DIR) -- the only writable state
#
# Why this is safe: the app reads reference data (routes, airports, fleet,
# missions, partners, runways) from its own code tree, and reads AND writes
# pilot data (logbook.db, settings, bookings, flight_state, uploads) only under
# PAC_DATA_DIR. So a release directory is read-only at runtime, pilot data lives
# outside every release, and deploy and rollback are a single atomic symlink
# flip that never copies or deletes pilot data.

set -euo pipefail

# ---- configuration (env-overridable) ---------------------------------------
ROOT="${PAC_DEPLOY_ROOT:-/home/pac/pac-acars}"
RELEASES_DIR="${PAC_RELEASES_DIR:-$ROOT/releases}"
SHARED_DATA="${PAC_SHARED_DATA:-$ROOT/shared/data}"
CURRENT_LINK="$ROOT/current"
PREVIOUS_LINK="$ROOT/previous"
KEEP_RELEASES="${PAC_KEEP_RELEASES:-5}"

HEALTH_URL="${PAC_HEALTH_URL:-http://127.0.0.1:5050/up}"
HEALTH_TIMEOUT="${PAC_HEALTH_TIMEOUT:-30}"

# Service control. Defaults drive systemd; the test harness overrides these to
# start/stop a throwaway app instance instead. Each is a full command line.
SVC_RESTART="${PAC_SVC_RESTART:-sudo systemctl restart pac}"
SVC_ISACTIVE="${PAC_SVC_ISACTIVE:-systemctl is-active --quiet pac}"
SVC_DISCORD_RESTART="${PAC_SVC_DISCORD_RESTART:-}"   # empty = skip (handled by caller)

# How a release builds its own virtual environment. Overridable so the harness
# can exercise the "dependency install failed" path deterministically.
VENV_BUILD="${PAC_VENV_BUILD:-}"   # empty = use build_venv() below

# ---- logging ---------------------------------------------------------------
log()  { printf '  %s\n' "$*"; }
step() { printf '\n[%s] %s\n' "$1" "$2"; }
die()  { printf '\n  FAILED: %s\n\n' "$*" >&2; exit 1; }

# ---- symlink helpers (atomic) ----------------------------------------------
# Resolve the release a symlink points at, as an absolute path, or "" if none.
link_target() {
  local link="$1"
  [ -L "$link" ] || { echo ""; return 0; }
  readlink -f "$link"
}

current_target()  { link_target "$CURRENT_LINK"; }
previous_target() { link_target "$PREVIOUS_LINK"; }

# Point a symlink at a target atomically (create-temp-then-rename). mv -T over an
# existing symlink is a single atomic rename on Linux, so readers never see a
# missing or half-written link.
set_link() {
  local link="$1" target="$2" tmp
  tmp="$(dirname "$link")/.$(basename "$link").tmp.$$"
  ln -sfn "$target" "$tmp"
  mv -Tf "$tmp" "$link"
}

# ---- health gate -----------------------------------------------------------
# A release is healthy only when the web app answers /up with 200 AND the
# service reports active. /up is a shallow liveness check: it is 200 only if the
# app is serving and the database reads, and it ignores background subsystems,
# so it never false-fails on a routine restart.
http_ok() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -o /dev/null --max-time 5 "$HEALTH_URL"
  else
    wget -q -O /dev/null --timeout=5 "$HEALTH_URL"
  fi
}

svc_restart()  { eval "$SVC_RESTART"; }
svc_isactive() { eval "$SVC_ISACTIVE"; }

# Poll until healthy or the timeout elapses. Returns 0 healthy, 1 not.
health_gate() {
  local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if svc_isactive && http_ok; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# ---- venv ------------------------------------------------------------------
# Build a release's own virtual environment and install its pinned deps. A
# failure here must abort the deploy BEFORE the symlink is flipped, so the old
# release keeps serving untouched.
build_venv() {
  local rel="$1"
  if [ -n "$VENV_BUILD" ]; then
    PAC_RELEASE="$rel" eval "$VENV_BUILD"
    return $?
  fi
  python3 -m venv "$rel/.venv"
  "$rel/.venv/bin/pip" install -q --upgrade pip
  "$rel/.venv/bin/pip" install -q -r "$rel/requirements.txt"
}

# ---- releases --------------------------------------------------------------
# Newest-first list of release directory names.
list_releases() {
  [ -d "$RELEASES_DIR" ] || return 0
  ls -1 "$RELEASES_DIR" 2>/dev/null | sort -r
}

# Remove old releases, but never the current or previous target.
prune_releases() {
  local keep="$KEEP_RELEASES" cur prev n=0 name path
  cur="$(current_target)"; prev="$(previous_target)"
  while read -r name; do
    [ -n "$name" ] || continue
    path="$RELEASES_DIR/$name"
    if [ "$path" = "$cur" ] || [ "$path" = "$prev" ]; then continue; fi
    n=$((n + 1))
    if [ "$n" -ge "$keep" ]; then
      rm -rf "$path" && log "pruned old release $name"
    fi
  done < <(list_releases)
}
