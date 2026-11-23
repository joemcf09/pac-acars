#!/usr/bin/env bash
# Replace the test copy's data with a fresh copy of the live data. The live site keeps running and is only read.
# Secrets are removed from the copy (Discord webhooks, the bot token, the email password, the SayIntentions and
# Hoppie keys, the login cookie key), so even a mistake on the test copy can't post or send as PAC.
#   sudo bash /home/pac/pac-staging/current/deploy/refresh_staging_data.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVE="${PAC_LIVE_DATA:-/home/pac/pac-acars/shared/data}"
STAGE="${PAC_STAGING_DATA:-/home/pac/pac-staging/shared/data}"
RESTART="${PAC_STAGING_RESTART-1}"

[ -d "$LIVE" ] || { echo "No live data at $LIVE"; exit 1; }
case "$STAGE" in */pac-staging/*) ;; *) echo "Refusing to write to $STAGE: not a test-copy folder"; exit 1;; esac
echo "Live data:  $(du -sh "$LIVE" | cut -f1) at $LIVE"

if [ "$RESTART" = 1 ]; then sudo systemctl stop pac-staging 2>/dev/null || true; fi
mkdir -p "$STAGE"
# everything except the database (copied safely below), secrets, backups and the live site's own run files
rsync -a --delete \
  --exclude 'logbook.db' --exclude 'logbook.db-wal' --exclude 'logbook.db-shm' \
  --exclude 'bot_secret' --exclude 'hoppie_logon' --exclude 'secret_key' --exclude 'backups/' \
  "$LIVE/" "$STAGE/"
# the database with SQLite's online backup, so a flight being filed on the live site can't corrupt the copy
python3 - "$LIVE/logbook.db" "$STAGE/logbook.db" <<'PY'
import os, sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
if os.path.exists(src):
    for p in (dst, dst + "-wal", dst + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    s, d = sqlite3.connect(src), sqlite3.connect(dst)
    with d:
        s.backup(d)
    s.close(); d.close()
PY
python3 "$HERE/scrub_staging_data.py" "$STAGE"
chown -R pac:pac "$STAGE" 2>/dev/null || true
echo "Test copy data: $(du -sh "$STAGE" | cut -f1) at $STAGE"
if [ "$RESTART" = 1 ] && systemctl list-unit-files pac-staging.service >/dev/null 2>&1; then
  sudo systemctl start pac-staging && echo "Test copy restarted on the fresh data."
fi
