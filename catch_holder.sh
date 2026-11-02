#!/bin/bash
# Catches whatever is holding the SQLite write lock, by name and line number.
#
# Run as root on the server, while the site is being slow:
#     bash /root/catch_holder.sh
#
# How it works: it repeatedly tries to take the write lock itself with a 1 second
# timeout. The moment that fails, something else holds it -- and at that instant
# it dumps the Python stack of every thread in the website process. The holder is
# whichever thread is sitting inside a database transaction.
#
# No code changes, nothing restarted, no risk to the site. It only reads.

set -u
APP=/home/pac/pac-acars
DB=$APP/data/logbook.db
OUT=/root/holder-dumps
PY=$APP/.venv/bin/python

mkdir -p "$OUT"
rm -f "$OUT"/dump-*.txt

echo "### website status"
systemctl is-active pac

PID=$(systemctl show -p MainPID --value pac)
if [ -z "$PID" ] || [ "$PID" = "0" ]; then
  echo "The website is not running, so there is nothing to inspect."
  echo "Start it with: systemctl start pac"
  exit 1
fi
echo "process id: $PID"

echo
echo "### making sure py-spy is available"
if ! command -v py-spy >/dev/null 2>&1; then
  "$PY" -m pip install --quiet py-spy 2>/dev/null \
    && echo "installed into the website's virtualenv" \
    || { pip install --quiet --break-system-packages py-spy 2>/dev/null \
         && echo "installed system-wide"; }
fi
PYSPY=$(command -v py-spy || echo "$APP/.venv/bin/py-spy")
if [ ! -x "$PYSPY" ]; then
  echo "Could not install py-spy. Send me this output and I will take another route."
  exit 1
fi
echo "using: $PYSPY"

echo
echo "### how many connections the process has open to the database right now"
ls -l /proc/"$PID"/fd 2>/dev/null | grep -c logbook.db || true

echo
echo "### watching for the lock to be held (20 checks, about a minute)"
echo "### Load the site in your browser now so there is traffic."
echo

CAUGHT=0
for i in $(seq 1 20); do
  if sqlite3 -cmd ".timeout 1000" "$DB" "BEGIN IMMEDIATE; ROLLBACK;" >/dev/null 2>&1; then
    printf "  check %2d: lock free\n" "$i"
  else
    CAUGHT=$((CAUGHT + 1))
    printf "  check %2d: LOCK HELD -- dumping all thread stacks\n" "$i"
    "$PYSPY" dump --pid "$PID" > "$OUT/dump-$i.txt" 2>&1
    {
      echo ""
      echo "open database file descriptors at this moment:"
      ls -l /proc/"$PID"/fd 2>/dev/null | grep -c logbook.db
    } >> "$OUT/dump-$i.txt"
  fi
  sleep 2
done

echo
if [ "$CAUGHT" -eq 0 ]; then
  echo "### The lock was never held across 20 checks."
  echo "### Either the site is healthy right now, or there was no traffic."
  echo "### Load a few pages (home, missions, career, profile) and run this again."
  exit 0
fi

echo "### Caught it $CAUGHT time(s). Here is where the threads were:"
echo
for f in "$OUT"/dump-*.txt; do
  echo "----- $f"
  grep -E "Thread|va\.py|app\.py|auth\.py|shop\.py|botlink\.py|sqlite3|execute|descriptors|^[0-9]+$" "$f" | head -60
  echo
done

echo "### Full dumps are in $OUT if more detail is needed."
