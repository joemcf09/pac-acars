"""Tidying Staff › Applications: old test applications go, current pilots' joining records and pending ones stay,
and pilot IDs are still never reused afterwards.

Run from the PAC folder:   python tests/test_applications.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


staff = A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Applications-Test-1"})
guest = A.app.test_client()


def apply(name):
    r = guest.post("/api/applications", json={"name": name, "email": f"{name.split()[0].lower()}@example.com", "agree": True,
                                               "simulator": "MSFS 2024", "hub": "KCVG", "motivation": "test"})
    assert r.status_code == 200, r.get_data(as_text=True)


def apps():
    return {a["name"]: a for a in staff.get("/api/staff/overview").get_json()["applications"]}


def review(name, action):
    return staff.post(f"/api/staff/applications/{apps()[name]['id']}", json={"action": action, "email_it": False}).get_json()


print("Setting the scene: two test pilots, one real pilot, one declined, one waiting")
for n in ("Test Pilot One", "Test Pilot Two", "Real Pilot", "Spam Bot", "Waiting Applicant"):
    apply(n)
ids = {n: review(n, "approve")["pilot_id"] for n in ("Test Pilot One", "Test Pilot Two", "Real Pilot")}
review("Spam Bot", "reject")
check("pilot IDs issued in order", list(ids.values()) == ["PAC0002", "PAC0003", "PAC0004"], ids)
for n in ("Test Pilot One", "Test Pilot Two"):
    r = staff.delete(f"/api/staff/pilots/{ids[n]}", json={"confirm": ids[n], "keep_flights": False})
    check(f"{n} removed from the roster", r.status_code == 200, r.get_json())
a = apps()
check("removed pilots' applications are flagged as not on the roster",
      not a["Test Pilot One"]["on_roster"] and not a["Test Pilot Two"]["on_roster"] and a["Real Pilot"]["on_roster"], a)

print("Deleting one at a time")
r = staff.delete(f"/api/staff/applications/{a['Real Pilot']['id']}")
check("a current pilot's joining record can't be deleted", r.status_code == 409 and "PAC0004" in r.get_json()["error"], r.get_json())
r = staff.delete(f"/api/staff/applications/{a['Test Pilot One']['id']}")
check("a removed test pilot's application can be deleted", r.status_code == 200 and "Test Pilot One" not in apps())
check("deleting it again says it's gone", staff.delete(f"/api/staff/applications/{a['Test Pilot One']['id']}").status_code == 404)

print("Clearing the rest in one go")
r = staff.post("/api/staff/applications/clear-old", json={})
check("old applications are cleared", r.status_code == 200 and r.get_json()["deleted"] == 2, r.get_json())
left = apps()
check("the real pilot's record stays", "Real Pilot" in left, list(left))
check("the application waiting for review stays", left.get("Waiting Applicant", {}).get("status") == "Pending", list(left))
check("nothing else is left", set(left) == {"Real Pilot", "Waiting Applicant"}, list(left))
check("clearing again finds nothing", staff.post("/api/staff/applications/clear-old", json={}).get_json()["deleted"] == 0)

print("Pilot IDs afterwards")
new = review("Waiting Applicant", "approve")["pilot_id"]
check("the next pilot still gets a fresh ID", new == "PAC0005", new)

print("Only staff")
check("visitors can't delete applications", guest.delete(f"/api/staff/applications/{left['Real Pilot']['id']}").status_code == 401)
check("visitors can't clear them", guest.post("/api/staff/applications/clear-old", json={}).status_code == 401)

print("\nAPPLICATIONS TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
