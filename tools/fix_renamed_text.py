"""One-off repair for airframes renamed before the rename also updated text.

The first version of Staff › Airframes › Rename moved the airframe, its history and write-ups, but left the
old registration inside mission and job titles (for example "Ferry N803PC to Miami"). This rewrites those.
Safe to run more than once; it only touches text, never the airframes themselves.

On the server:   ~/pac-acars/.venv/bin/python ~/pac-acars/tools/fix_renamed_text.py N801PC=N738PC N802PC=N739PC ...
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import va  # noqa: E402

pairs = [a.upper().split("=", 1) for a in sys.argv[1:] if "=" in a]
if not pairs:
    print(__doc__)
    sys.exit(1)
con = sqlite3.connect(ROOT / "data" / "logbook.db", timeout=30)
with con:
    for old, new in pairs:
        print(f"{old} -> {new}: {va.carry_reg_text(con, old, new)} record(s) updated")
con.close()
