"""Flight intervention and incident actions in an isolated PAC data directory."""
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-flight-ops-") as temp:
        data = Path(temp) / "data"
        data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        env = dict(os.environ, PAC_DATA_DIR=str(data))
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=env).returncode)

sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import auth  # noqa: E402

founder = A.app.test_client()
assert founder.post("/api/auth/setup", json={"password": "Flight-Ops-Test-123"}).status_code == 200
with A.db() as con:
    con.execute("""INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location)
        VALUES ('PAC0014','Test Pilot','pilot@example.com','KCVG',?,'Active','Passed',0,'KCVG')""", (time.time(),))
auth._set_password("PAC0014", "Pilot-Test-123")
pilot = A.app.test_client()
assert pilot.post("/api/auth/login", json={"pilot_id": "PAC0014", "password": "Pilot-Test-123"}).status_code == 200
assert pilot.get("/api/staff/flight-ops").status_code == 403
support_url = "/api/staff/pilot-support/PAC0014"
assert pilot.get(support_url).status_code == 403
assert founder.get("/api/staff/pilot-support/PAC9999").status_code == 404
initial = founder.get(support_url).get_json()
assert initial["pilot"]["name"] == "Test Pilot" and initial["booking"] is None
assert not initial["access"]["staff"] and initial["caps"] == []
assert "password_hash" not in initial["pilot"] and "email" not in initial["pilot"]
assert "PAC0014" not in A.SESSIONS
with A.db() as con:
    con.execute("INSERT INTO roles (pilot_id,role,note,since) VALUES (?,?,?,?)",
                ("PAC0014", "academy_director", "Test support access", time.time()))
scoped = founder.get(support_url).get_json()
assert scoped["caps"] == ["academy"] and scoped["roles"] == ["academy_director"]
assert pilot.get(support_url).status_code == 403

m = next(x for x in A.MISSIONS.values() if not x.get("job") and not x.get("live") and not x.get("urgent"))
key = time.time()
A.save_booking({"mission": m, "aircraft": m["aircraft"][0], "flight_number": "PAC4321",
                "requested_at": key, "airframe": None}, "PAC0014")
s = A.session("PAC0014")
s["recorder"] = SimpleNamespace(complete=True, phase="ARRIVED")
saved = A.flight_state_path("PAC0014")
saved.write_bytes(b"test draft")
A.save_json(A.CHECKPOINT_PATH, {"requested_at": key, "phase": "APPROACH", "saved_at": time.time()})
support = founder.get(support_url).get_json()
assert support["booking"]["number"] == "PAC4321"
assert support["acars"]["unfiled_draft"] and support["acars"]["saved_state"]
assert support["acars"]["checkpoint"]["phase"] == "APPROACH"
assert A.load_booking("PAC0014") is not None and saved.exists()
listed = founder.get("/api/staff/flight-ops").get_json()["flights"]
assert len(listed) == 1 and listed[0]["draft"] and listed[0]["saved_state"] and listed[0]["checkpoint"]
path = "/api/staff/flight-ops/PAC0014/intervene"
payload = {"action": "clear_draft", "reason": "X-Plane crashed on approach", "booking_key": key}
assert pilot.post(path, json=payload).status_code == 403
s.update(remote={"flight": "PAC4321"}, remote_seen=time.time())
assert founder.post(path, json=payload).status_code == 409
s.update(remote=None, remote_seen=0)
assert founder.post(path, json={**payload, "booking_key": key - 1}).status_code == 409
assert founder.post(path, json=payload).status_code == 200
assert s["recorder"] is None and not saved.exists() and not A.CHECKPOINT_PATH.exists()
assert A.load_booking("PAC0014") is not None

png = b"\x89PNG\r\n\x1a\n" + b"test evidence"
created = founder.post("/api/staff/flight-incidents", json={"pilot_id": "PAC0014",
    "kind": "simulator_crash", "summary": "GPU crash before reaching PANC",
    "evidence_note": "Pilot supplied X-Plane screenshot",
    "screenshot": "data:image/png;base64," + base64.b64encode(png).decode()})
assert created.status_code == 201, created.get_json()
iid = created.get_json()["id"]
assert founder.get(f"/api/staff/flight-incidents/{iid}/evidence").data == png
assert pilot.get(f"/api/staff/flight-incidents/{iid}/evidence").status_code == 403
pay = f"/api/staff/flight-incidents/{iid}/goodwill"
assert pilot.post(pay, json={"amount": 850, "note": "Simulator crash goodwill"}).status_code == 403
before = A.va.balance("PAC0014")
assert founder.post(pay, json={"amount": 850, "note": "Simulator crash goodwill"}).status_code == 200
assert founder.post(pay, json={"amount": 850, "note": "Simulator crash goodwill"}).status_code == 409
assert A.va.balance("PAC0014") - before == 850
assert founder.post(f"/api/staff/flight-incidents/{iid}/close",
                    json={"resolution": "False draft cleared; pilot may retry"}).status_code == 200
assert founder.post(path, json={"action": "release_booking", "reason": "Pilot chose to retry flight",
                                "booking_key": key}).status_code == 200
assert A.load_booking("PAC0014") is None
with A.db() as con:
    assert con.execute("SELECT COUNT(*) FROM pireps WHERE pilot_id='PAC0014'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM flight_interventions WHERE pilot_id='PAC0014'").fetchone()[0] == 2
print("staff flight intervention and incident checks passed")
