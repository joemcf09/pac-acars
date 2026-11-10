"""PAC ACARS 1.1.7: SayIntentions gate, auto-start at the departure airport, the sim CG check against the loadsheet,
and aborted flights logged for staff. Run from the PAC folder: python tests/test_acars_117.py"""
import json, os, shutil, subprocess, sys, tempfile, types
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-117-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        env = dict(os.environ, PAC_DATA_DIR=str(data), PAC_SI_FLIGHT_JSON=str(Path(temp) / "flight.json"))
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=env).returncode)
sys.path[:0] = [str(ROOT), str(ROOT / "acars_client")]

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

import acars_core  # noqa: E402

print("CG check at OUT")
bk = {"dispatch": {"signed_snapshot": {"paper": {"loadsheet": {"mac_tow": 22.6, "cg_source": "calculated"}}}}}
check("close to the loadsheet: matches", "MATCHES" in acars_core.cg_check(bk, 23.4))
far = acars_core.cg_check(bk, 26.9)
check("far off: says how far and which way, and what to check", "DIFFERS 4.3% AFT" in far and "PAYLOAD" in far, far)
est = {"dispatch": {"paper": {"loadsheet": {"mac_tow": 24.0, "cg_source": "estimate"}}}}
check("estimated loadsheet CG: shown, but no verdict", "ESTIMATE" in acars_core.cg_check(est, 30.0) and "DIFFERS" not in acars_core.cg_check(est, 30.0))
check("no sim CG (X-Plane, some aircraft): nothing said", acars_core.cg_check(bk, None) is None)
check("no loadsheet: nothing said", acars_core.cg_check({}, 22.0) is None)

import client  # noqa: E402

print("SayIntentions gate")
check("gate name from flight.json", client.si_gate({"flight_details": {"assigned_gate": "b12"}}) == "B12")
check("gate as an object", client.si_gate({"flight_details": {"assigned_gate": {"name": "X17", "lat": 1, "lon": 2}}}) == "X17")
check("no gate yet", client.si_gate({"flight_details": {"assigned_gate": ""}}) is None and client.si_gate({}) is None)
logged = []
fake = types.SimpleNamespace(last=None, msg=lambda t, text, kind: logged.append(text))
client.state.update(rec=fake, thread=types.SimpleNamespace(is_alive=lambda: True), si_gate=None)
Path(os.environ["PAC_SI_FLIGHT_JSON"]).write_text(json.dumps({"flight_details": {"api_key": "k", "assigned_gate": "C4"}}))
client.si_flight_json(); client.si_flight_json()
check("the gate goes in the ACARS log once while tracking", logged == ["SAYINTENTIONS  ATC ASSIGNED GATE C4"], logged)
client.state.update(rec=None, thread=None)

print("Auto-start")
T = lambda **k: types.SimpleNamespace(**{"on_ground": True, "engines_running": True, "gs": 0, "lat": 39.0488, "lon": -84.6678, **k})
booking = {"mission": {"origin": {"icao": "KCVG", "lat": 39.0488, "lon": -84.6678}}}
check("engines running at the departure airport: start", client.auto_start_ready(T(), booking))
check("engines off and parked: wait", not client.auto_start_ready(T(engines_running=False), booking))
check("somewhere else: the alarm asks instead", not client.auto_start_ready(T(lat=40.6413, lon=-73.7781), booking))
check("airborne: the alarm asks instead", not client.auto_start_ready(T(on_ground=False), booking))
check("on by default, with a Settings switch", client.load_config().get("auto_start") is True and "cfgAuto" in (ROOT / "acars_client/ui.html").read_text())

print("Aborted flights are logged for staff")
import app as A  # noqa: E402
c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Abort-Test-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False, "cargo_orders_enabled": False})
ls = c.post("/api/plan/loadsheet", json={"mission_id": "PAC712", "aircraft": "B77F"}).get_json() or {}
bkr = c.post("/api/booking", json={"mission_id": "PAC712", "aircraft": "B77F", "airframe": None, "seed": ls.get("seed"), "zone_ack": True})
r = c.post("/api/acars/app/abort", json={"reason": "Sim crashed on climb", "phase": "CLIMB", "flown_nm": 41, "source": "MSFS"})
st = c.get("/api/staff/overview"); ab = (st.get_json() or {}).get("aborts") or []
check("abort answers", r.status_code == 200)
check("staff see who, which flight, how far and why", ab and ab[0]["reason"] == "Sim crashed on climb" and ab[0]["phase"] == "CLIMB"
      and ab[0]["flown_nm"] == 41 and ab[0]["flight"], ab)
check("the booking is kept", A.load_booking() is not None)

print("\nACARS 1.1.7 TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
