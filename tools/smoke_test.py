"""End-to-end smoke test against a running ACARS server (python app.py).
Usage: python tools/smoke_test.py   (with the server running on :5050, Demo speed-up high)
Fails on any HTTP 500 or non-JSON API answer."""
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

BASE = "http://localhost:5050"
problems = []


import http.cookiejar, os  # noqa: E401,E402
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))  # keeps the sign-in


def call(method, path, body=None, expect_json=True):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        r = OPENER.open(req, timeout=30); code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    data = None
    if expect_json:
        try:
            data = json.loads(raw)
        except ValueError:
            problems.append(f"{method} {path}: not JSON (HTTP {code})")
    if code >= 500 and code != 503:  # 503 = weather offline, expected here
        problems.append(f"{method} {path}: HTTP {code} {raw[:160]!r}")
    return code, data


# sign in. On a fresh site (no passwords yet) the founder's password is set to PAC_TEST_PASSWORD; on a site that already
# has sign-in, PAC_TEST_PASSWORD must be the founder's password. The smoke test never changes an existing password.
TEST_PW = os.environ.get("PAC_TEST_PASSWORD", "smoke-test-password")
code, me = call("GET", "/api/auth/me")
if (me or {}).get("setup_needed"):
    call("POST", "/api/auth/setup", {"password": TEST_PW})
    print(f"Fresh site: the founder's password was set to the test password ({'PAC_TEST_PASSWORD' if 'PAC_TEST_PASSWORD' in os.environ else 'smoke-test-password'}).")
else:
    code, r = call("POST", "/api/auth/login", {"pilot_id": os.environ.get("PAC_TEST_PILOT", "PAC0001"), "password": TEST_PW})
    if code != 200:
        print("This site already has sign-in. Run the smoke test with PAC_TEST_PASSWORD set to the founder's password.")
        sys.exit(1)
# visitors get the public pages only
_anon = urllib.request.build_opener()
for _p, _want in (("/api/va/home", 200), ("/api/logbook", 401), ("/api/staff/overview", 401)):
    try:
        _c = _anon.open(BASE + _p, timeout=10).status
    except urllib.error.HTTPError as e:
        _c = e.code
    if _c != _want:
        problems.append(f"visitor {_p}: HTTP {_c}, expected {_want}")

for path in ["/api/bootstrap", "/api/va/home", "/api/va/career", "/api/va/config", "/api/va/board", "/api/fleet", "/api/profile",
             "/api/logbook", "/api/finance", "/api/urgent", "/api/airframes", "/api/staff/overview", "/api/staff/backups",
             "/api/acars/status", "/api/weather?ids=KCVG", "/api/weather/network", "/api/airports/search?q=cincinnati"]:
    call("GET", path)
call("GET", "/", expect_json=False); call("GET", "/dispatch", expect_json=False)
call("DELETE", "/api/booking")
call("POST", "/api/settings", {"demo_speedup": 400, "enforce_airframes": False})
code, b = call("POST", "/api/booking", {"mission_id": "PAC1022", "aircraft": "B733F", "airframe": "N010PC"})
call("GET", "/api/dispatch")
call("GET", "/api/economics/estimate?mission_id=PAC1022&aircraft=B733F")
call("POST", "/api/economics/estimate", {"mission_id": "PAC1022", "aircraft": "B733F"})
call("GET", "/api/acars/app/download")
# fly the flight the way the PAC ACARS app does: register it, send live updates, hand over the full record
sys.path.insert(0, str(Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from tracker import FlightRecorder  # noqa: E402
from flightgen import fly  # noqa: E402
import acars_core  # noqa: E402
import threading  # noqa: E402
_, hello = call("GET", "/api/acars/app/hello")
bk = (hello or {}).get("booking")
if not bk:
    problems.append("ACARS app hello returned no booking")
else:
    call("POST", "/api/acars/app/start", {"source": "Demo", "requested_at": bk.get("requested_at")})
    rec = FlightRecorder(bk)
    samples = fly("KCVG", "36C", "KCLT", "36C", td_fpm=-150)
    lk = threading.Lock()
    for i, smp in enumerate(samples):
        rec.update(smp)
        if i == 400:  # mid-taxi: dispatch messages through the shared ACARS code the app uses
            for body in ({"type": "delay", "minutes": 10, "reason": "ATC"}, {"type": "text", "text": "Request stand"},
                         {"type": "fault", "ata": 49, "description": "APU slow to start", "severity": "deferred", "category": "C"}):
                err = acars_core.handle_message(rec, lk, body, {"KCLT": {}})
                if err:
                    problems.append(f"ACARS message {body['type']}: {err}")
        if i % 800 == 0:
            call("POST", "/api/acars/app/live", {"status": rec.status()})
    code, st = call("GET", "/api/acars/status")
    if not (st or {}).get("remote"):
        problems.append("website isn't following the app's flight")
    code, done = call("POST", "/api/acars/app/complete", {"record": rec.export(), "requested_at": bk.get("requested_at"), "source": "Demo"}, )
    if code != 200 or not (done or {}).get("draft"):
        problems.append(f"hand-over failed: HTTP {code} {str(done)[:160]}")
call("GET", "/api/pirep/draft")
_, p = call("POST", "/api/pirep", {"remarks": "smoke test"})
if p and p.get("id"):
    call("GET", f"/api/logbook/{p['id']}")
    call("GET", f"/api/pireps/{p['id']}/approach")
    call("GET", f"/api/dispatch/pirep/{p['id']}")
call("GET", "/api/airframes/N010PC")
call("GET", "/api/finance"); call("GET", "/api/staff/overview"); call("GET", "/api/va/board")
_, u = call("GET", "/api/urgent")
if u:
    call("POST", "/api/booking", {"mission_id": u[0]["id"], "aircraft": u[0]["aircraft"][0], "airframe": u[0]["suggested_airframe"]})
    call("GET", "/api/dispatch")
    call("DELETE", "/api/booking")
call("GET", "/api/pilot/me")
call("POST", "/api/staff/wallet/PAC0001", {"amount": 1500, "note": "smoke"})
call("POST", "/api/pilot/jumpseat/quote", {"to": "KSTL"})
call("POST", "/api/pilot/jumpseat", {"to": "KSTL", "kind": "airline"})
call("POST", "/api/pilot/jumpseat", {"to": "KCVG", "kind": "pac"})
call("GET", "/api/finance")
call("GET", "/api/staff/fleet-types")
call("POST", "/api/staff/fleet-types", {"code": "SMK1", "name": "Smoke Freighter", "icao": "SMK1", "simbrief_type": "SMK1",
     "max_payload_lbs": 100000, "mtow_lbs": 350000, "range_nm": 3000, "min_rwy_ft": 8000, "cruise_ktas": 460})
call("POST", "/api/staff/fleet-types/SMK1/retire", {"retired": True})
call("POST", "/api/staff/fleet-types/SMK1/retire", {"retired": False})
call("DELETE", "/api/staff/fleet-types/SMK1")
call("GET", "/api/bootstrap")
_, jobs = call("GET", "/api/jobs")
for kind in ("ferry", "contract"):
    j = next((x for x in (jobs or []) if x["job_kind"] == kind), None)
    if j:
        call("POST", "/api/staff/wallet/PAC0001", {"amount": 5000, "location": j["origin"]["icao"]})
        call("POST", "/api/booking", {"mission_id": j["id"], "aircraft": j["aircraft"][0], "airframe": j.get("suggested_airframe")})
        call("POST", "/api/economics/estimate", {"mission_id": j["id"], "aircraft": j["aircraft"][0]})
        call("GET", "/api/dispatch")
        call("DELETE", "/api/booking")
call("POST", "/api/settings", {"enforce_pilot_location": False})
_, jobs = call("GET", "/api/jobs")
contract = next((j for j in (jobs or []) if j.get("contract")), None)
if not contract:
    problems.append("no partner crew requests generated")
else:
    call("POST", "/api/booking", {"mission_id": contract["id"], "aircraft": contract["aircraft"][0]})
    call("GET", "/api/dispatch")
    call("POST", "/api/economics/estimate", {"mission_id": contract["id"], "aircraft": contract["aircraft"][0]})
    call("DELETE", "/api/booking")
call("POST", "/api/settings", {"enforce_pilot_location": True})
call("GET", "/api/jobs")
call("GET", "/api/news")
call("GET", "/api/staff/news")
call("POST", "/api/staff/news", {"kind": "notam", "title": "Smoke test NOTAM", "body": "Ignore", "days": 1})
_, nl = call("GET", "/api/staff/news")
for n in (nl or []):
    if n["title"] == "Smoke test NOTAM":
        call("DELETE", f"/api/staff/news/{n['id']}")
call("GET", "/api/gallery")
call("GET", "/gallery", expect_json=False) if False else None
call("GET", "/api/maintenance")
call("GET", "/api/maintenance?all=1")
code, w = call("POST", "/api/maintenance", {"reg": "N011PC", "ata": 32, "description": "Smoke test write-up", "severity": "grounding"})
if w and w.get("id"):
    call("POST", f"/api/staff/maintenance/{w['id']}", {"action": "defer", "category": "C"})
    call("POST", f"/api/staff/maintenance/{w['id']}", {"action": "clear", "note": "smoke"})
# PAC ACARS app endpoints
call("POST", "/api/settings", {"enforce_pilot_location": False, "enforce_airframes": False})
code, bk = call("POST", "/api/booking", {"mission_id": "PAC1022", "aircraft": "B733F"})
if code != 200:
    problems.append(f"booking for the ACARS app check failed: {bk}")
call("GET", "/api/acars/app/hello")
call("POST", "/api/acars/app/start", {"source": "Demo"})
call("POST", "/api/acars/app/live", {"status": {"phase": "CRUISE", "messages": []}})
code, st = call("GET", "/api/acars/status")
if not (st or {}).get("remote"):
    problems.append("website does not show the ACARS app's flight")
call("POST", "/api/acars/app/abort", {})
call("DELETE", "/api/booking")
call("POST", "/api/settings", {"enforce_pilot_location": True, "enforce_airframes": True})
call("GET", "/api/stats")
call("POST", "/api/goals", {"kind": "hours", "target": 10, "period": "month"})
call("GET", "/api/goals")
call("GET", "/api/stations")
call("GET", "/api/stations/KCVG")
call("GET", "/api/stations/TJSJ")
call("POST", "/api/staff/stations/KCVG/stands", {"positions": {"N1": [39.0652, -84.6564]}})
call("POST", "/api/staff/stations/KCVG/stands", {"reset": True})
call("GET", "/api/downloads")
call("GET", "/api/downloads/simbrief/B77F.txt", expect_json=False)
call("GET", "/api/staff/discord")
call("GET", "/api/staff/mail")
call("GET", "/api/staff/letter/accepted/PAC0001")
call("GET", "/api/staff/letter/rejected?name=Test&email=t@example.com&reason=Not+yet")
call("GET", "/dispatch", expect_json=False)
call("GET", "/static/dispatch-classic.html", expect_json=False)
call("GET", "/api/recap")
call("GET", "/api/recap?month=2026-01")
call("POST", "/api/ofp/watch", {"on": False})
call("GET", "/api/does-not-exist")  # must answer JSON 404
print("SMOKE TEST", "PASSED" if not problems else "FAILED")
for x in problems:
    print(" -", x)
sys.exit(1 if problems else 0)
