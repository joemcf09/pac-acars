#!/usr/bin/env bash
# Backup of everything that matters, kept for 30 days. Runs nightly, and also at
# the start of every deploy. Reads the pilot-data directory, so it works with the
# release layout (shared/data) and the old flat layout alike.
#   Install nightly:  sudo cp deploy/backup.sh /etc/cron.daily/pac-backup && sudo chmod +x /etc/cron.daily/pac-backup
set -euo pipefail

# Where pilot data lives. After migrate_to_releases.sh this is shared/data; the
# service already exports PAC_DATA_DIR. Overridable for testing.
DATA="${PAC_DATA_DIR:-/home/pac/pac-acars/shared/data}"
OUT="${PAC_BACKUP_DIR:-/home/pac/backups}"
KEEP_DAYS="${PAC_BACKUP_KEEP_DAYS:-30}"

[ -d "$DATA" ] || { echo "No data dir at $DATA; nothing to back up."; exit 0; }
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%d-%H%M)
DB="$DATA/logbook.db"
SNAP="/tmp/pac-logbook-$STAMP.db"

# Copy the database with SQLite's own online backup, so a flight being filed can
# never corrupt the copy. Use the sqlite3 CLI if present, else Python's sqlite3.
if [ -f "$DB" ]; then
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB" ".backup '$SNAP'"
  else
    python3 - "$DB" "$SNAP" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(src); d = sqlite3.connect(dst)
with d: s.backup(d)
s.close(); d.close()
PY
  fi
fi

# Archive the db snapshot plus the irreplaceable pilot files that exist.
FILES=()
[ -f "$SNAP" ] && FILES+=("-C" "/tmp" "pac-logbook-$STAMP.db")
for rel in settings.json profile.json site.json fleet_custom.json secret_key \
           stand_positions.json gallery fleet_photos downloads; do
  [ -e "$DATA/$rel" ] && FILES+=("-C" "$DATA" "$rel")
done
if [ "${#FILES[@]}" -gt 0 ]; then
  tar -czf "$OUT/pac-$STAMP.tar.gz" "${FILES[@]}" 2>/dev/null || true
fi
rm -f "$SNAP"
find "$OUT" -name 'pac-*.tar.gz' -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true
echo "Backed up to $OUT/pac-$STAMP.tar.gz"

# Off-site copy (strongly recommended). Configure rclone, then uncomment:
# rclone copy "$OUT/pac-$STAMP.tar.gz" pacbackup:pac-backups/
