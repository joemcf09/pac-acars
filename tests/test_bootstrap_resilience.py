"""One failing section of the start-up data (say, a bad record behind the mission board) mustn't blank the whole site.

Run from the PAC folder:   python tests/test_bootstrap_resilience.py
"""
import sys
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
c.post("/api/auth/setup", json={"password": "Resilience-Pass-1"})
r = c.get("/api/bootstrap")
check("a normal start-up has nothing partial", r.status_code == 200 and "partial" not in r.json, r.json.get("partial"))


def boom(*a, **k):
    raise ValueError("bad record")


real = va.mission_board, va.career
va.mission_board, va.career = boom, boom
r = c.get("/api/bootstrap")
va.mission_board, va.career = real
check("the site still loads when the mission board and career fail", r.status_code == 200, r.status_code)
check("and says which parts are missing", r.json.get("partial") == ["missions", "career"], r.json.get("partial"))
check("with safe empty values in their place", r.json["missions"] == [] and r.json["career"] == {} and r.json["routes"])

print("\nBOOTSTRAP RESILIENCE TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
