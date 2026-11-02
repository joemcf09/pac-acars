"""SayIntentions.AI VA-Link: PAC briefs each pilot's AI crew about their flight, keeping both keys safe."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "profile.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import auth  # noqa: E402
import sayintentions as SI  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


received, answer = [], {"body": b'{"status": "OK"}', "code": 200}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(n).decode())
        received.append({"api_key": form["api_key"][0], "payload": json.loads(form["payload"][0]),
                         "type": self.headers.get("Content-Type")})
        self.send_response(answer["code"]); self.end_headers(); self.wfile.write(answer["body"])

    def log_message(self, *a): pass


srv = HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
SI.ENDPOINT = f"http://127.0.0.1:{srv.server_port}/sapi/importVAData"


def wait_for(n, timeout=8):
    end = time.time() + timeout
    while len(received) < n and time.time() < end:
        time.sleep(0.1)
    return len(received) >= n


founder = A.app.test_client()
founder.post("/api/auth/setup", json={"password": "Founder-Pass-123"})
with A.db() as con:
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location) VALUES "
                "('PAC0002','Bob Member','bob@example.com','KCVG',1767225600,'Active','Passed',0,'KCVG')")
auth._set_password("PAC0002", "Member-Pass-123")
pilot = A.app.test_client()
pilot.post("/api/auth/login", json={"pilot_id": "PAC0002", "password": "Member-Pass-123"})
guest = A.app.test_client()
VA_KEY, PILOT_KEY = "VAkey_SECRET_123456", "pilotKEY_abcdef123456"

print("Staff set-up and secrecy")
check("pilots can't change SayIntentions settings", pilot.post("/api/settings", json={"si_enabled": True}).status_code == 403)
founder.post("/api/settings", json={"si_enabled": True, "si_va_key": VA_KEY, "si_coupon": "SIVA0TEST", "si_dispatcher_freq": "118.94"})
check("staff can set it up", SI.ready())
founder.post("/api/settings", json={"si_va_key": "", "si_coupon": "SIVA0TEST"})
check("saving with an empty key box keeps the key", A.settings()["si_va_key"] == VA_KEY)
for who, c in (("pilots", pilot), ("staff", founder)):
    boot = json.dumps(c.get("/api/bootstrap").get_json())
    check(f"the VA key never reaches {who}' browsers", VA_KEY not in boot)
check("staff see that the key is saved", founder.get("/api/bootstrap").get_json()["settings"]["si_key_set"] is True)
check("visitors don't see the coupon", "SIVA0TEST" not in json.dumps(guest.get("/api/bootstrap").get_json())
      and guest.get("/api/sayintentions").status_code == 401)
st = pilot.get("/api/sayintentions").get_json()
check("members see the coupon and frequency", st["coupon"] == "SIVA0TEST" and st["frequency"] == "118.94" and st["ready"])

print("Linking a pilot")
check("a nonsense key is refused", pilot.post("/api/sayintentions/key", json={"api_key": "<bad key>"}).status_code == 400)
r = pilot.post("/api/sayintentions/key", json={"api_key": PILOT_KEY}).get_json()
check("saving the key briefs the crew straight away", wait_for(1) and r["key_set"] and r["ok"], r)
first = received[-1]
check("the request is form-encoded as VA-Link expects", first["type"] == "application/x-www-form-urlencoded")
check("it carries the pilot's key and PAC's VA key", first["api_key"] == PILOT_KEY and first["payload"]["va_api_key"] == VA_KEY)
check("all four sections are sent", all(first["payload"].get(k) for k in ("crew_data", "dispatcher_data", "copilot_data", "skyops_data")))
check("without a booking, the AI is told there's no flight", "no PAC flight booked" in first["payload"]["dispatcher_data"])
check("the pilot's key is never shown back", PILOT_KEY not in json.dumps(pilot.get("/api/sayintentions").get_json()))

print("Booking a flight")
founder.post("/api/settings", json={"require_type_ratings": False, "enforce_ranks": False})
frames = [f for f in A.va.airframes() if f["location"] == "KCVG" and f["status"] == "Available"]
m, frame = next((x, f) for x in A.MISSIONS.values() if x["origin"]["icao"] == "KCVG" and x.get("category") != "Checkride"
                for f in frames if f["type"] in x["aircraft"])
BOOK = {"mission_id": m["id"], "aircraft": frame["type"], "airframe": frame["reg"]}
n = len(received)
r = pilot.post("/api/booking", json=BOOK)
check("the pilot can book", r.status_code == 200, r.get_json())
check("booking briefs the crew", wait_for(n + 1))
p = received[-1]["payload"]
fn = A.load_booking("PAC0002")["flight_number"]
check("the dispatcher knows the flight number and route", fn in p["dispatcher_data"] and m["origin"]["icao"] in p["dispatcher_data"]
      and m["destination"]["icao"] in p["dispatcher_data"], p["dispatcher_data"][:400])
check("…the cargo", (m.get("cargo") or "")[:20] in p["dispatcher_data"])
check("…the captain", "Bob Member" in p["copilot_data"])
check("the crew know there are no passengers", "no passenger" in p["crew_data"].lower())
check("PAC's callsign is in the briefing", "PAGANI" in p["dispatcher_data"])
n = len(received)
pilot.delete("/api/booking")
check("cancelling tells the crew the flight is off", wait_for(n + 1) and "no PAC flight booked" in received[-1]["payload"]["dispatcher_data"])

print("Problems")
answer.update(body=b'{"status": "ERROR", "error": "Invalid VA API key"}', code=200)
r = pilot.post("/api/sayintentions/push")
check("a refusal from SayIntentions is reported", r.status_code == 400 and "Invalid VA API key" in (r.get_json().get("error") or ""), r.get_json())
answer.update(body=b'{"status": "OK"}', code=200)
SI.ENDPOINT, real = "http://127.0.0.1:1/nothing", SI.ENDPOINT
r = pilot.post("/api/sayintentions/push").get_json()
check("SayIntentions being down is reported, not fatal", r["ok"] is False and "reach" in (r["error"] or ""), r)
SI.ENDPOINT = real
founder.post("/api/settings", json={"si_enabled": False})
n = len(received)
pilot.post("/api/booking", json=BOOK)
time.sleep(3)
check("switched off: nothing is sent", len(received) == n)
pilot.delete("/api/booking")
founder.post("/api/settings", json={"si_enabled": True})

print("PAC ACARS")
check("the app can pass on the key it found", pilot.post("/api/acars/app/sayintentions", json={"api_key": "newKEY_9876543210", "new_flight": True}).status_code == 200
      and SI.pilot_key("PAC0002") == "newKEY_9876543210")
sys.path.insert(0, str(ROOT / "acars_client"))
os.environ.setdefault("PAC_ACARS_NO_WINDOW", "1")
import client as CL  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "flight.json"
    f.write_text(json.dumps({"flight_details": {"api_key": "fromFILE_12345678", "callsign": "PAC1234"}}), encoding="utf-8")
    os.environ["PAC_SI_FLIGHT_JSON"] = str(f)
    key, mtime = CL.si_flight_json()
    check("PAC ACARS reads the key from SayIntentions' flight.json", key == "fromFILE_12345678" and mtime)
    os.environ["PAC_SI_FLIGHT_JSON"] = str(Path(d) / "missing.json")
    check("…and stays quiet if SayIntentions isn't installed", CL.si_flight_json() == (None, None))

srv.shutdown()
print("\n" + ("SAYINTENTIONS TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
