"""Urgent requests keep being made after weeks of running: the numbering can't loop forever, and doesn't clash.

Before this fix, once 100 urgent requests had ever been made, the next one searched forever for a free number,
pinning the server's CPU at 100% and slowing the whole site. Run from the PAC folder:  python tests/test_urgent_ids.py
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import va  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Urgent-Ids-Pass-1"})
now = time.time()
with A.db() as con:   # three weeks of history: every old number used, all finished, some long ago
    for i, n in enumerate(list(range(9500, 9600)) + list(va.URGENT_IDS)):
        created = now - (3 + i % 25) * 86400
        con.execute("INSERT OR REPLACE INTO urgent (id, data, created, expires, status) VALUES (?,?,?,?, ?)",
                    (f"PAC{n}", json.dumps({"id": f"PAC{n}"}), created, created + 3600, "expired" if i % 2 else "completed"))

out = {}
t = threading.Thread(target=lambda: out.update(r=va.urgent_missions()), daemon=True)
t.start()
t.join(10)
check("new urgent requests are made quickly even with every number used before", not t.is_alive())
new = out.get("r") or []
check("and they appear", len(new) >= 1, new)
check("numbered PAC9410-9499, clear of rotations, tours and jobs",
      all(9410 <= int(m["id"][3:]) <= 9499 for m in new), [m["id"] for m in new])
check("no urgent number is also a rotation or tour leg", not ({m["id"] for m in new} & set(va.TOUR_LEGS)))
with A.db() as con:
    old = con.execute("SELECT COUNT(*) FROM urgent WHERE created < ?", (now - 30 * 86400,)).fetchone()[0]
check("finished requests older than 30 days are cleared away", old == 0, old)

with A.db() as con:   # every number busy right now: no new request, and no hang
    for n in va.URGENT_IDS:
        con.execute("INSERT OR REPLACE INTO urgent (id, data, created, expires, status) VALUES (?,?,?,?, 'expired')",
                    (f"PAC{n}", json.dumps({"id": f"PAC{n}"}), now, now))
    con.execute("DELETE FROM urgent WHERE status='open'")
t = threading.Thread(target=lambda: out.update(r2=va.urgent_missions()), daemon=True)
t.start()
t.join(10)
check("when every number is in use it simply waits, without hanging", not t.is_alive() and out.get("r2") == [], out.get("r2"))

print("\nURGENT IDS TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
