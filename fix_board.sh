#!/bin/bash
# Stops the website, finds out whether anything holds the database write lock,
# fills the mission board with nothing competing for it, then starts back up.
#
# Run as root on the server:   bash /root/fix_board.sh
#
# The site is down while the board fills. Expect under two minutes.

set -u
APP=/home/pac/pac-acars
PY=$APP/.venv/bin/python
DB=$APP/data/logbook.db

echo "### stopping the website and the bot"
systemctl stop pac pac-discord 2>/dev/null
sleep 3
systemctl is-active pac pac-discord

echo
echo "### is anything still holding the database open?"
# With the service stopped, any line here is a real finding worth reading.
lsof "$DB" 2>/dev/null || echo "(nothing holding it open -- that is what we want)"

echo
echo "### database files, including any write-ahead log left behind"
ls -la "$APP"/data/logbook.db* 2>/dev/null

echo
echo "### filling the mission board"
cd "$APP" || exit 1
sudo -u pac "$PY" "$APP/seed_board.py"
RC=$?

echo
if [ "$RC" -eq 0 ]; then
  echo "### starting the website"
  systemctl start pac
  sleep 5
  systemctl is-active pac

  echo
  echo "### waiting 30s, then showing any lock or timing complaints"
  sleep 30
  if journalctl -u pac --since '-2 min' --no-pager | grep -E 'took|locked|failed' | tail -15; then
    echo
    echo "^^ lines above mean it is still contending. Send them over."
  else
    echo "(no 'took', 'locked' or 'failed' lines at all -- that is the good outcome)"
  fi
else
  echo "### the seed script exited $RC, so the website was deliberately left down."
  echo "### Nothing was lost and nothing was broken. Send me the output above."
  echo "### To bring the site up anyway:   systemctl start pac"
fi
