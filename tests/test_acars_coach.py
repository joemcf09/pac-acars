"""PAC ACARS 1.1: touch-and-go practice, approach gates, SOP coach, fuel checks and the landing debrief.

Run from the PAC folder:   python tests/test_acars_coach.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import acars_core  # noqa: E402
import sim_sources  # noqa: E402
import tracker  # noqa: E402
from sim_sources import Telemetry  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


print("Landing practice circuit")
apt = {"icao": "KCVG", "lat": 39.0488, "lon": -84.6678}
r = tracker.FlightRecorder({"practice": True, "flight_number": "PRACTICE", "aircraft": "", "mission": {"origin": apt, "destination": apt}})
clock, lat = [1000.0], [39.03]


def step(agl, ias, vs, ground, gear=True, beacon=True, strobe=True, brake=False, gs=None):
    clock[0] += 0.5
    lat[0] += 0.0001
    r.update(Telemetry(t=clock[0], lat=lat[0], lon=-84.66, alt_ft=900 + agl, agl_ft=agl, ias=ias, gs=ias if gs is None else gs, vs_fpm=vs,
                       hdg=0, on_ground=ground, engines_running=True, parking_brake=brake, fuel_lbs=20000, weight_lbs=150000,
                       gear_down=gear, flaps=0.5, g=1.0, beacon=beacon, landing_lights=True, strobe=strobe, bank=10))


for _ in range(10):
    step(0, 0, 0, True, brake=True, gs=0, beacon=False)
for _ in range(20):
    step(0, 10, 0, True, beacon=False, gs=10)
for k in range(2):
    for i in range(40):
        step(0, 60 + i * 3, 0, True, strobe=False)
    for i in range(60):
        step(5 + i * 20, 160, 1500, False)
    for i in range(120):
        step(1200, 140, 0, False)
    for i in range(80):
        step(1200 - i * 15, 140, -1300 if k == 0 else -700, False)
    step(0, 135, -350 if k == 0 else -180, True)
    for i in range(30):
        step(0, 120 - i, 0, True)
texts = [m["text"] for m in r.messages]
check("both touchdowns recorded", len(r.touchdowns) == 2, r.touchdowns)
check("steep first approach flagged at 1,000 ft", any(t.startswith("UNSTABLE AT 1000FT") and "SINK" in t for t in texts))
check("second approach stable", "STABLE AT 1000FT" in texts, texts)
check("beacon reminder", any("BEACON SHOULD BE ON" in t for t in texts))
check("strobe reminder", any("STROBES ON WHEN ENTERING" in t for t in texts))
check("no penalties in practice", not any(e["penalty"] for e in r.events), r.events)

print("Demo flight with a SimBrief plan")
clock2 = [1_800_000_000.0]
sim_sources.time.time = lambda: clock2[0]
O = {"icao": "KCVG", "lat": 39.0488, "lon": -84.6678, "elevation": 896}
D = {"icao": "KMIA", "lat": 25.79325, "lon": -80.29056, "elevation": 8}
bk = {"flight_number": "PAC1234", "aircraft": "B742F", "requested_at": 1, "aircraft_info": {"icao": "B742", "mtow_lbs": 833000},
      "ofp": {"trip_fuel_lbs": 30000, "block_fuel_lbs": 45000, "reserve_fuel_lbs": 6000, "taxi_fuel_lbs": 800, "distance_nm": 830,
              "est_enroute_min": 120, "cruise_ft": 35000, "origin": O, "destination": D},
      "mission": {"title": "Auto parts", "origin": O, "destination": D, "payload_lbs": 80000, "cargo": "Auto parts", "target_block_min": 140}}
src = sim_sources.DemoSource(O, D, cruise_ft=35000, block_fuel_lbs=45000, zfw_lbs=250000, speedup=30)
rec = tracker.FlightRecorder(bk)
for _ in range(200000):
    clock2[0] += 0.25
    rec.update(src.read())
    if rec.complete:
        break
texts = [m["text"] for m in rec.messages]
check("flight completes", rec.complete)
check("fuel check at top of climb", any(t.startswith("FUEL CHECK TOC") for t in texts))
check("fuel check at top of descent", any(t.startswith("FUEL CHECK TOD") for t in texts))
check("top of descent reminder", any("TOP OF DESCENT IN ABOUT" in t for t in texts))
check("aircraft check: demo has 2 engines, the 747-200 has 4", any("HAS 4" in t for t in texts))
check("no coaching errors", not getattr(rec, "coach_error", None), getattr(rec, "coach_error", None))
# put the demo's touchdown on KMIA runway 09, 1,500 ft past its (displaced) landing threshold
rw = json.loads((ROOT / "data" / "runways.json").read_text(encoding="utf-8"))["KMIA"]
end = next(x for x in rw if x[0].startswith("09") or x[5].startswith("09"))
ident, tlat, tlon, thdg, disp = (end[0], end[1], end[2], end[3], end[4]) if end[0].startswith("09") else (end[5], end[6], end[7], end[8], end[9])
import math  # noqa: E402
k = (1500 + (disp or 0)) / 3.28084 / 111320
td_lat, td_lon = tlat + k * math.cos(math.radians(thdg)), tlon + k * math.sin(math.radians(thdg)) / math.cos(math.radians(tlat))
td = dict(rec.touchdowns[0], lat=td_lat, lon=td_lon, hdg=thdg)
rec.landing_series = [[x[0], x[1], x[2], x[3], x[4], td_lat, td_lon, thdg, x[8], x[9]] for x in rec.landing_series]
d = acars_core.landing_debrief(rec, td, ROOT / "data")
check("debrief finds the runway and touchdown point", d.get("airport") == "KMIA" and d.get("runway") == ident and 1300 < (d.get("touchdown_ft") or 0) < 1700,
      (d.get("airport"), d.get("runway"), d.get("touchdown_ft")))
check("debrief has tips", bool(d["tips"]))
check("flight record still exports as JSON", bool(json.dumps(rec.export())))
again = tracker.FlightRecorder.from_export(bk, json.loads(json.dumps(rec.export())))
check("record reloads (resume) with the new fields", again.touchdowns == rec.touchdowns)

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
