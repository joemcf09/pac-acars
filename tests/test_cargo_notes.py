"""Handover notes: the pilot who flew freight in can leave a note for whoever flies it on; it shows on the load sheet.
Run from the PAC folder: python tests/test_cargo_notes.py"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-notes-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import analysis  # noqa: E402
import app as A  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Notes-Test-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False, "cargo_orders_enabled": False})
rw = analysis.runways(A.DATA)
onward = None
for route in [r for r in A.ROUTES.values() if r.get("category") == "Scheduled"][:60]:
    ac = next(a for a in route["aircraft"] if a in A.FLEET)
    ls = c.post("/api/plan/loadsheet", json={"mission_id": route["id"], "aircraft": ac}).json
    if any((s.get("destination") or {}).get("icao") not in (None, route["destination"]["icao"]) for s in ls.get("shipments", [])):
        onward = (route, ac, ls); break
route, ac, ls = onward
c.delete("/api/booking")
b = c.post("/api/booking", json={"mission_id": route["id"], "aircraft": ac, "manifest_seed": ls["seed"], "zone_ack": True}).json
o, d = route["origin"]["icao"], route["destination"]["icao"]
c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
rec = FlightRecorder(b)
for s_ in fly(o, rw[o][0][0], d, rw[d][0][0], td_fpm=-150):
    rec.update(s_)
c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
c.post("/api/pirep", json={"remarks": "notes"})
with A.db() as con:
    sid = con.execute("SELECT id FROM cargo_shipments WHERE status='AT_STATION' AND current_station=?", (d,)).fetchone()[0]
    delivered = con.execute("SELECT id FROM cargo_shipments WHERE status LIKE 'DELIVERED%'").fetchone()
det = c.get(f"/api/cargo/shipments/{sid}").json
check("the pilot who flew it in may leave a note", det["can_note"] is True, det.get("can_note"))
r = c.post(f"/api/cargo/shipments/{sid}/notes", json={"text": "AKE in M04, straps checked. Consignee wants it before 0600Z."})
check("the note saves", r.status_code == 200 and r.json["notes"][0]["text"].startswith("AKE in M04"), r.json)
check("too-short notes are refused", c.post(f"/api/cargo/shipments/{sid}/notes", json={"text": "ok"}).status_code == 400)
if delivered:
    check("no notes on delivered freight", c.post(f"/api/cargo/shipments/{delivered[0]}/notes", json={"text": "late note here"}).status_code == 403)
nxt = next((r2 for r2 in A.ROUTES.values() if r2["origin"]["icao"] == d and r2.get("category") == "Scheduled"
            and any(t["id"] == sid for t in (c.post("/api/plan/loadsheet", json={"mission_id": r2["id"], "aircraft": next(a for a in r2["aircraft"] if a in A.FLEET)}).json.get("transfer_options") or []))), None)
if nxt:
    ls2 = c.post("/api/plan/loadsheet", json={"mission_id": nxt["id"], "aircraft": next(a for a in nxt["aircraft"] if a in A.FLEET)}).json
    t = next(t for t in ls2["transfer_options"] if t["id"] == sid)
    check("the next pilot sees it on the load sheet", t["notes"] and "straps checked" in t["notes"][0]["text"], t)
v = A.app.test_client()
check("visitors can't leave notes", v.post(f"/api/cargo/shipments/{sid}/notes", json={"text": "hello there"}).status_code == 401)
print(); print("All handover note checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
