"""Automated flight tests.

Flies scripted flights (tests/flightgen.py) through the real tracker, PIREP
builder, landing and takeoff analysis, economics and pay, and checks the
results. Run from the ACARS folder:   python tests/test_flights.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.chdir(ROOT)

# use a throwaway database so tests never touch the real logbook
_tmp = tempfile.mkdtemp()
import app as A  # noqa: E402

A.DB_PATH = Path(_tmp) / "logbook.db"
A.db().close()
import va  # noqa: E402
va.C["DATA"] = Path(_tmp)
from tracker import FlightRecorder  # noqa: E402
from flightgen import fly  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'ok ' if cond else 'FAIL'} {name}{'' if cond else ' · ' + str(detail)}")
    if not cond:
        failures.append(f"{name}: {detail}")


def run(label, trip_fuel=None, **opts):
    m = A.ROUTES["PAC1022"]  # KCVG to KCLT, B733F recommended
    ofp = {"trip_fuel_lbs": trip_fuel} if trip_fuel else None
    booking = {"mission": m, "aircraft": "B733F", "ofp": ofp, "flight_number": "PAC1022", "airframe": None, "requested_at": 1_789_990_000}
    rec = FlightRecorder(booking)
    samples = fly("KCVG", "36C", "KCLT", "36C", **opts)
    for s in samples:
        rec.update(s)
    p = A.build_pirep(booking, rec)
    print(f"\n{label}: phases {' '.join(x['phase'] for x in rec.timeline)}")
    return rec, p, samples


def burn(samples, rec):
    f_off = next(s.fuel_lbs for s in samples if s.t >= rec.oooi["off"])
    f_on = next(s.fuel_lbs for s in samples if s.t >= rec.oooi["on"])
    return f_off - f_on


# ---------------------------------------------------------------- a clean flight
rec, p, samples = run("Clean flight", td_fpm=-90)
rec2, p, samples = run("Clean flight with an OFP", trip_fuel=round(burn(samples, rec)), td_fpm=-90)
rec = rec2
phases = [x["phase"] for x in rec.timeline]
for ph in ("PUSHBACK", "TAXI_OUT", "TAKEOFF", "INITIAL_CLIMB", "CLIMB", "CRUISE", "DESCENT", "APPROACH", "LANDING", "TAXI_IN", "ARRIVED"):
    check(f"phase {ph} reached", ph in phases, phases)
check("no go-around", "GO_AROUND" not in phases, phases)
check("status Delivered", p["status"] == "Delivered", p["status"])
check("landing rate about -90 fpm", -130 <= (p["landing_rate"] or 0) <= -60, p["landing_rate"])
la, ta = p.get("landing_analysis") or {}, p.get("takeoff_analysis") or {}
check("landing runway KCLT 36C", la.get("runway") == "36C", la.get("runway"))
# ground truth: where the scripted aircraft actually touched down
import math as _m
from flightgen import runway_end
_A = runway_end("KCLT", "36C")
_td = next(s for s in samples if s.on_ground and s.t > rec.oooi["off"])
_e = (_td.lon - _A["lon"]) * 111320 * _m.cos(_m.radians(_A["lat"])); _n = (_td.lat - _A["lat"]) * 111320
_true_ft = (_e * _m.sin(_m.radians(_A["hdg"])) + _n * _m.cos(_m.radians(_A["hdg"]))) / 0.3048
check("touchdown point matches where the wheels touched", abs((la.get("touchdown_ft") or -9999) - _true_ft) <= 150, (la.get("touchdown_ft"), round(_true_ft)))
check("on the centreline", la.get("centerline_ft") is not None and abs(la["centerline_ft"]) <= 10, la.get("centerline_ft"))
check("stable approach", la.get("stable") is True, la.get("stability_note"))
check("takeoff runway KCVG 36C", ta.get("runway") == "36C", ta.get("runway"))
check("rotation speed about 150 kt", 146 <= (ta.get("rotate_ias") or 0) <= 154, ta.get("rotate_ias"))
check("rotation rate about 2.5°/s", 1.8 <= (ta.get("rotation_rate") or 0) <= 3.2, ta.get("rotation_rate"))
check("no tail strike", ta.get("tail_strike") is False, ta.get("max_pitch_ground"))
check("no touch-back", ta.get("touchback") is False)
check("grade A", p["grade"] == "A", (p["score"], p["breakdown"]))
check("no review flags", not p["flags"], p["flags"])
check("PAC makes money on a recommended aircraft", p["economics"]["profit"] > 0, p["economics"])
check("pilot is paid", (p.get("pay") or {}).get("total", 0) > 0, p.get("pay"))
skill = {x["label"].split(" (")[0] for x in (p.get("pay") or {}).get("skill", [])}
for k in ("Grade A flight", "Butter landing", "Fuel within 3% of plan", "Stable approach", "Clean flight, no review flags"):
    check(f"skill bonus: {k}", k in skill, skill)

# ---------------------------------------------------------------- a hard landing
rec, p, _ = run("Hard landing", td_fpm=-720)
check("hard landing measured", (p["landing_rate"] or 0) <= -650, p["landing_rate"])
check("hard landing flagged for review", any("Hard landing" in f for f in p["flags"]), p["flags"])
check("inspection cost charged", "hard_landing_inspection" in p["economics"]["costs"], p["economics"]["costs"])
check("no landing skill bonus", not any("landing" in x["label"].lower() for x in (p.get("pay") or {}).get("skill", [])))

# ---------------------------------------------------------------- a bounce
rec, p, _ = run("Bounced landing", bounce=True)
check("bounce counted", (p.get("bounces") or 0) >= 1, p.get("bounces"))
check("landing rate from the first contact, not the second", -200 <= (p["landing_rate"] or 0) <= -100, p["landing_rate"])
check("still one landing, no go-around", "GO_AROUND" not in [x["phase"] for x in rec.timeline])
check("no butter bonus after a bounce", not any("Butter" in x["label"] for x in (p.get("pay") or {}).get("skill", [])))

# ---------------------------------------------------------------- wheels back on the runway after liftoff
rec, p, _ = run("Touch-back after liftoff", touchback=True)
phases = [x["phase"] for x in rec.timeline]
check("no phantom landing or go-around", "GO_AROUND" not in phases and phases.count("LANDING") == 1, phases)
check("touch-back logged", any("TOUCHED RUNWAY AFTER LIFTOFF" in m["text"] for m in rec.messages))
check("touch-back in takeoff analysis", (p.get("takeoff_analysis") or {}).get("touchback") is True)

# ---------------------------------------------------------------- integrity
rec, p, _ = run("Sim rate 4x in cruise", sim_rate_s=60)
check("sim-rate flag", any("Sim rate" in f for f in p["flags"]), p["flags"])
# sim rate while parked at the stand (loading a heavy) is fine; taxiing at 16x is not
import dataclasses  # noqa: E402
_m = A.ROUTES["PAC1022"]
for _label, _pick in (("Sim rate 16x while loading at the stand", lambda i, x: i < 40),
                      ("Sim rate 16x while taxiing", lambda i, x: x.on_ground and x.gs >= 3)):
    _b = {"mission": _m, "aircraft": "B733F", "ofp": None, "flight_number": "PAC1022", "airframe": None, "requested_at": 1_789_990_000}
    _rec = FlightRecorder(_b)
    for _i, _s in enumerate(fly("KCVG", "36C", "KCLT", "36C")):
        _rec.update(dataclasses.replace(_s, sim_rate=16.0) if _pick(_i, _s) else _s)
    _p = A.build_pirep(_b, _rec)
    _flag = any("Sim rate" in f for f in _p["flags"])
    if "stand" in _label:
        check("sim rate while parked at the stand isn't flagged", not _flag, _p["flags"])
    else:
        check("sim rate while taxiing is still flagged", _flag, _p["flags"])
rec, p, _ = run("Paused 11 minutes in cruise", pause_s=660)
check("pause flag", any("Paused" in f for f in p["flags"]), p["flags"])
rec, p, _ = run("Overspeed below FL100", overspeed_s=40)
over = [b for b in p["breakdown"] if "250" in b[0]]
check("one overspeed penalty for one continuous exceedance", len(over) == 1, over)

# ---------------------------------------------------------------- go-around, then a steep descent to land (like PAC9545 into JFK)
rec, p, _ = run("Go-around, then a steep final descent", td_fpm=-98, go_around_dive=True)
phases = [x["phase"] for x in rec.timeline]
check("go-around detected", "GO_AROUND" in phases, phases)
check("one landing after the go-around", phases.count("LANDING") == 1, phases)
check("final approach judged unstable (the dive after the go-around)", (p.get("landing_analysis") or {}).get("stable") is False,
      (p.get("landing_analysis") or {}).get("stability_note"))
check("landing label says Butter", any(b[0].startswith("Butter landing") for b in p["breakdown"]), p["breakdown"])

# after a real go-around, only the final approach is judged (direct check on the analysis)
import analysis as _an
_ser, _t = [], 0.0
def _pt(agl, vs, gnd=0):
    global _t
    _ser.append([_t, agl, vs, 140, 1.0, 35.2, -80.95, 356, gnd, 140]); _t += 1.0
for a in range(1000, 300, -12): _pt(a, -1800)          # first approach: a dive, unstable
for a in range(300, 1300, 25): _pt(a, 1500)             # go-around: climbs 1,000 ft
for a in range(1300, 0, -12): _pt(a, -720)              # final approach: steady 3 degrees
_pt(0, -120, 1)
_la = _an.analyze_landing(_ser, _t - 1, -120, 1.1, [], ROOT / "data", lambda *a: 0)
check("after a go-around, the final approach is judged on its own", _la.get("stable") is True, _la.get("stability_note"))

# ---------------------------------------------------------------- dispatch messages and maintenance
def run_with(label, before_file, **opts):
    m = A.ROUTES["PAC1022"]
    booking = {"mission": m, "aircraft": "B733F", "ofp": None, "flight_number": "PAC1022", "airframe": "N010PC", "requested_at": 1_789_990_000}
    rec = FlightRecorder(booking)
    samples = fly("KCVG", "36C", "KCLT", "36C", **opts)
    for s_ in samples:
        rec.update(s_)
    before_file(rec)
    print(f"\n{label}")
    return rec, A.build_pirep(booking, rec), booking


slow = dict(td_fpm=-150)
# a long ATC hold: 60 min of extra block time, reported to dispatch
def add_hold(rec):
    rec.oooi["in"] += 60 * 60
    rec.reported_delays = [{"t": rec.oooi["off"], "minutes": 60, "reason": "ATC"}]
rec, p, _ = run_with("Late with a reported ATC delay", add_hold, **slow)
check("excused: still Delivered, not late", p["status"] == "Delivered", (p["status"], p["breakdown"]))
check("excusal noted on the PIREP", any("reported to dispatch" in b[0] for b in p["breakdown"]), p["breakdown"])
def add_hold_unreported(rec):
    rec.oooi["in"] += 60 * 60
rec, p, _ = run_with("Late without reporting", add_hold_unreported, **slow)
check("unreported: Delivered late", p["status"] == "Delivered late", p["status"])

# declared diversion: fly to KCLT but declare KCLT's neighbour; then relabel the destination so KCLT is the diversion airport
def declare(rec):
    rec.dest = dict(A.AIRPORTS["KGSO"])
    rec.declared_diversion = {"icao": "KCLT", "reason": "WEATHER", "t": rec.oooi["on"] - 600}
rec, p, _ = run_with("Declared diversion", declare, **slow)
check("declared diversion counts as Diverted", p["status"] == "Diverted" and p["arr"] == "KCLT", (p["status"], p["arr"]))
check("declared diversion penalty is -10", any(b[1] == -10 and "declared to dispatch" in b[0] for b in p["breakdown"]), p["breakdown"])

# a grounding fault written up in flight grounds the tail when the PIREP is filed
def fault(rec):
    rec.faults = [{"ata": 32, "description": "Left main brake overheating", "severity": "grounding", "category": "C", "t": rec.oooi["on"]}]
rec, p, booking = run_with("Grounding write-up in flight", fault, **slow)
with A.db() as con:
    con.execute("UPDATE airframes SET status='Booked' WHERE reg='N010PC'")
    pid = con.execute("INSERT INTO pireps (filed_at, flight_number, dep, arr, aircraft, demo, review_status) VALUES (?,?,?,?,?,0,'Accepted')",
                      (1_790_100_000, "PAC1022", "KCVG", "KCLT", "B733F")).lastrowid
va.after_file(p, booking, rec, pid)
af = {a["reg"]: a for a in va.airframes()}["N010PC"]
check("tail grounded for maintenance at KCLT", af["status"] == "Maintenance" and af["location"] == "KCLT", (af["status"], af["location"]))
check("write-up open on the tail", any(i["ata"] == 32 for i in af["open_items"]), af["open_items"])
iid = next(i["id"] for i in af["open_items"] if i["ata"] == 32)
va.clear_item(iid, "Brake unit replaced", "Staff")
check("clearing the write-up returns the tail to service", {a["reg"]: a for a in va.airframes()}["N010PC"]["status"] == "Available")

# ---------------------------------------------------------------- hand-over from the PAC ACARS app
import json as _json
m = A.ROUTES["PAC1022"]
booking = {"mission": m, "aircraft": "B733F", "ofp": None, "flight_number": "PAC1022", "airframe": None, "requested_at": 1}
rec = FlightRecorder(booking)
for s_ in fly("KCVG", "36C", "KCLT", "36C", td_fpm=-120, bounce=True):
    rec.update(s_)
rec.reported_delays = [{"t": rec.oooi["off"], "minutes": 20, "reason": "ATC"}]
rebuilt = FlightRecorder.from_export(booking, _json.loads(_json.dumps(rec.export())))
p1, p2 = A.build_pirep(booking, rec), A.build_pirep(booking, rebuilt)
print("\nHand-over from the ACARS app")
for k in ("score", "grade", "landing_rate", "bounces", "status", "points", "breakdown", "landing_analysis", "takeoff_analysis", "economics"):
    check(f"rebuilt record gives the same {k}", p1[k] == p2[k], (p1[k], p2[k]) if k in ("score", "grade", "points") else k)

# ---------------------------------------------------------------- type-rating checkrides
def checkride(label, **opts):
    m = va.checkride_mission("PAC0001", "TR-B737")
    booking = {"mission": m, "aircraft": "B733F", "ofp": None, "flight_number": "PAC-TR", "airframe": None, "requested_at": 1_789_990_000}
    rec = FlightRecorder(booking)
    import analysis
    rw = analysis.runways(A.DATA)  # the checkride starts where the pilot is: use that airport's real runways
    for smp in fly(m["origin"]["icao"], rw[m["origin"]["icao"]][0][0], m["destination"]["icao"], rw[m["destination"]["icao"]][0][0], **opts):
        rec.update(smp)
    p = A.build_pirep(booking, rec)
    print(f"\n{label}: score {p['score']}, landing {p['landing_rate']} fpm, checkride {p.get('type_checkride')}")
    return rec, p, booking


_cr = va.checkride_mission("PAC0001", "TR-B737")
print(f"\nType-rating checkride, B737 ({_cr['origin']['icao']} to {_cr['destination']['icao']}, {_cr['distance_nm']} nm)")
check("checkride starts where the pilot is", _cr["origin"]["icao"] == va.pilot_location("PAC0001"), (_cr["origin"]["icao"], va.pilot_location("PAC0001")))
check("checkride is a short sector", 250 <= _cr["distance_nm"] <= 1000, _cr["distance_nm"])
rec, p, booking = checkride("Good checkride flight")
check("a good flight passes the checkride", (p.get("type_checkride") or {}).get("passed") is True, p.get("type_checkride"))
with A.db() as con:
    con.execute("DELETE FROM type_ratings WHERE pilot_id='PAC0001'")
    type_report = con.execute(
        "INSERT INTO pireps (filed_at, mission_id, aircraft, status, score, demo, review_status, pilot_id, detail) "
        "VALUES (?,?,?,?,?,0,'Accepted','PAC0001',?)",
        (1_789_990_000, "TR-B737", booking["aircraft"], p["status"], p["score"],
         __import__("json").dumps({"type_checkride": p["type_checkride"]}))).lastrowid
va.after_file(p, booking, rec, type_report)
with A.db() as con:
    row = con.execute("SELECT source, score FROM type_ratings WHERE pilot_id='PAC0001' AND family='B737'").fetchone()
check("passing records the rating", row is not None and row["source"] == "checkride", dict(row) if row else None)
rec, p, booking = checkride("Hard landing on a checkride", td_fpm=-620)
tc = p.get("type_checkride") or {}
check("a hard landing fails the checkride", tc.get("passed") is False, tc)
check("the reason is given", any("landing firmer" in r for r in tc.get("reasons", [])), tc.get("reasons"))
rec, p, booking = checkride("Bounced checkride landing", bounce=True)
tc = p.get("type_checkride") or {}
check("a bounce fails the checkride", tc.get("passed") is False and any("bounce" in r for r in tc.get("reasons", [])), tc)
booking_wrong = {**booking, "aircraft": "A306F"}
check("booking the checkride in the wrong type is refused",
      bool(va.check_booking(va.checkride_mission("PAC0001", "TR-B737"), "A306F", None, {})[0]))

# ---------------------------------------------------------------- planning helper with real-shaped weather
print("\nPlanning helper")
import weather  # noqa: E402
_real_metars = weather.metars
_raw = {"KCVG": "KCVG 291753Z 20015KT 10SM FEW050 24/12 A3002", "KCLT": "KCLT 291752Z 04030G38KT 10SM BKN030 21/14 A2998"}
weather.metars = lambda ids: {k: weather.decode_metar(v) for k, v in _raw.items() if k in ids}  # the shape weather.metars really returns
_c = A.app.test_client()
with A.app.test_request_context():
    pass
import auth  # noqa: E402
with A.db() as con:
    con.execute("UPDATE pilots SET password_hash=? WHERE id='PAC0001'", (auth.generate_password_hash("test-password-1"),))
_c.post("/api/auth/login", json={"pilot_id": "PAC0001", "password": "test-password-1"})
_r = _c.post("/api/plan/helper", json={"mission_id": "PAC1022", "aircraft": "B733F"})
check("planning helper answers with live weather", _r.status_code == 200, (_r.status_code, (_r.get_json() or {}).get("error")))
_h = _r.get_json() or {}
check("departure runway faces the wind (KCVG 18C)", (_h.get("departure") or {}).get("runway") == "18C", _h.get("departure"))
check("headwind worked out", ((_h.get("departure") or {}).get("headwind_kt") or 0) > 10, _h.get("departure"))
weather.metars = lambda ids: (_ for _ in ()).throw(TimeoutError("down"))
check("planning helper copes without weather", _c.post("/api/plan/helper", json={"mission_id": "PAC1022", "aircraft": "B733F"}).status_code == 200)
weather.metars = _real_metars

# ---------------------------------------------------------------- the living mission board and partner feed
print("\nLiving mission board (simulated 20 days)")
import time as _t  # noqa: E402
_real_time = _t.time
_T = [_real_time()]
_t.time = lambda: _T[0]
try:
    _seen, _keys, _repeats, _sizes, _short = set(), {}, 0, set(), 0
    for _ in range(80):  # every 6 hours
        va.refresh_mission_board(here=va.pilot_location())
        _board = [m for m in va.mission_board() if m.get("live")]
        _sizes.add(len(_board))
        _short += sum(1 for m in _board if m["origin"]["icao"] == va.pilot_location()) < va.LIVE_HERE_MIN
        for m in _board:
            if m["id"] in _seen:
                continue
            _seen.add(m["id"])
            k = f"classic|{m['id']}" if m.get("classic") else f"{m['scenario']}|{m['origin']['icao']}|{m['destination']['icao']}"
            _repeats += k in _keys and _T[0] - _keys[k] < va.LIVE_NO_REPEAT_DAYS * 86400
            _keys[k] = _T[0]
        _T[0] += 6 * 3600
    check("the board always holds its full set", _sizes == {va.LIVE_BOARD_SIZE}, _sizes)
    check("there's always work from where the pilot is", _short == 0, _short)
    check("the board keeps changing (over 50 different missions)", len(_seen) > 50, len(_seen))
    check("no route repeats within ten days", _repeats == 0, _repeats)
    _req = set()
    for _ in range(96):  # 24 hours, every 15 minutes
        va.refresh_jobs_today(here=va.pilot_location())
        _req |= {j["id"] for j in va.jobs_today() if j.get("contract")}
        _T[0] += 900
    check("partner requests trickle in through the day", 6 <= len(_req) <= 20, len(_req))
finally:
    _t.time = _real_time

print("\nFLIGHT TESTS", "PASSED" if not failures else f"FAILED ({len(failures)})")
for f in failures:
    print(" -", f)
sys.exit(1 if failures else 0)
