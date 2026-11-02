#!/usr/bin/env bash
# Update PAC on the server from a zip you've uploaded. Your data is never touched.
#   scp pac-acars.zip pac@pac-va.com:~/     then on the server:  ~/pac-acars/deploy/update.sh ~/pac-acars.zip
set -euo pipefail
ZIP=${1:?Usage: update.sh /path/to/pac-acars.zip}
PAC_DIR=/home/pac/pac-acars
TMP=$(mktemp -d)
echo "Backing up first…"
"$PAC_DIR/deploy/backup.sh" >/dev/null
unzip -q "$ZIP" -d "$TMP"
SRC="$TMP/pac-acars"
echo "Stopping PAC…"
sudo systemctl stop pac
# program files only: everything under data/ is yours and stays
rsync -a --delete \
  --exclude 'data/' --exclude '.venv/' --exclude 'acars_client/config.json' \
  --exclude 'static/downloads/' \
  --exclude 'acars_client/build/dist/' --exclude 'acars_client/build/work/' --exclude 'acars_client/build/Output/' \
  "$SRC/" "$PAC_DIR/"
# PAC's own reference data does live in data/ (the route network, airports, runways, fleet, missions, partners):
# copy just those files, so new routes and missions arrive. Your logbook, settings, pilots and uploads are never touched.
for f in routes.json airports.json runways.json fleet.json missions.json partners.json; do
  if [ -f "$SRC/data/$f" ]; then install -m 644 "$SRC/data/$f" "$PAC_DIR/data/$f"; fi
done
"$PAC_DIR/.venv/bin/pip" install -q -r "$PAC_DIR/requirements.txt"
sudo systemctl start pac
# the Discord bot picks up the new version too (if it's installed)
if systemctl list-unit-files pac-discord.service >/dev/null 2>&1 && systemctl is-enabled --quiet pac-discord 2>/dev/null; then
  sudo systemctl restart pac-discord || true
fi
rm -rf "$TMP"
sleep 2
systemctl is-active --quiet pac && echo "PAC updated and running." || { echo "PAC did not start. Check: journalctl -u pac -n 50"; exit 1; }
