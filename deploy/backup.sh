#!/usr/bin/env bash
# Nightly backup of everything that matters, kept for 30 days.
# Install with:  sudo cp deploy/backup.sh /etc/cron.daily/pac-backup && sudo chmod +x /etc/cron.daily/pac-backup
set -euo pipefail
PAC_DIR=/home/pac/pac-acars
OUT=/home/pac/backups
KEEP_DAYS=30
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%d-%H%M)
# SQLite is copied with its own backup command, so a flight being filed can't corrupt the copy
sqlite3 "$PAC_DIR/data/logbook.db" ".backup '/tmp/pac-logbook-$STAMP.db'"
tar -czf "$OUT/pac-$STAMP.tar.gz" \
  -C /tmp "pac-logbook-$STAMP.db" \
  -C "$PAC_DIR" data/settings.json data/profile.json data/site.json data/fleet_custom.json \
  data/secret_key data/stand_positions.json data/gallery data/fleet_photos data/downloads 2>/dev/null || true
rm -f "/tmp/pac-logbook-$STAMP.db"
find "$OUT" -name 'pac-*.tar.gz' -mtime +$KEEP_DAYS -delete
echo "Backed up to $OUT/pac-$STAMP.tar.gz"

# Off-site copy (strongly recommended: a server can die). Set this up with `rclone config` first,
# then uncomment the line below, using the name you gave the remote.
# rclone copy "$OUT/pac-$STAMP.tar.gz" pacbackup:pac-backups/
