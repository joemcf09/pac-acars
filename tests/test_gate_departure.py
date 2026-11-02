"""PAC ACARS starts the flight when the aircraft leaves the gate, even with awkward add-ons and pushback tugs."""
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as A  # noqa: E402
from sim_sources import SourceError, Telemetry, XPlaneSource  # noqa: E402
from tracker import FlightRecorder, TrackerThread  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


m = A.ROUTES["PAC1022"]          # KCVG to KCLT
O = m["origin"]


def rec():
    return FlightRecorder({"mission": m, "aircraft": m["aircraft"][0], "ofp": None, "flight_number": "PAC9601", "airframe": None,
                           "requested_at": time.time()})


def tel(t, dlat=0.0, gs=0.0, brake=True, engines=False):
    return Telemetry(t=t, lat=O["lat"] + dlat, lon=O["lon"], alt_ft=37, agl_ft=0, ias=0, gs=gs, vs_fpm=0, hdg=180, on_ground=True,
                     engines_running=engines, parking_brake=brake, fuel_lbs=26257, weight_lbs=511557, gear_down=True, flaps=0, g=1.0)


def roll(r, n, start, speed_kt, brake, gs_reported=None, engines=False):
    """n seconds of pushing back at speed_kt, sampled every 0.5 s."""
    lat = r.last.lat - O["lat"] if r.last else 0.0
    for i in range(int(n * 2)):
        t = start + i * 0.5
        lat -= speed_kt / 3600 * 0.5 / 60
        r.update(tel(t, lat, speed_kt if gs_reported is None else gs_reported, brake, engines))
    return start + n


print("Waiting at the gate")
r = rec()
for i in range(20):
    r.update(tel(1000 + i))
check("parked with the brake set: still preflight", r.phase == "PREFLIGHT")
check("…and it says to release the parking brake", "Release the parking brake" in (r.waiting_for() or ""), r.waiting_for())
r.update(tel(1021, brake=False))
check("brake off, not moving: it says it's waiting for movement", "waiting for the aircraft to move" in (r.waiting_for() or ""), r.waiting_for())

print("Normal pushback")
r = rec(); r.update(tel(1000))
roll(r, 6, 1001, 3, brake=False)
check("brake off and moving: the gate departure is logged", r.phase == "PUSHBACK" and r.oooi["out"], r.phase)

print("An aircraft whose parking brake value stays set while it moves")
r = rec(); r.update(tel(1000))
roll(r, 4, 1001, 3, brake=True)
check("not logged after a moment (could be a brief glitch)", r.phase == "PREFLIGHT")
roll(r, 6, 1005, 3, brake=True)
check("logged once it has clearly been moving", r.phase == "PUSHBACK" and r.oooi["out"], r.phase)
check("the pilot is told why", any("PARKING BRAKE READS SET" in x["text"] for x in r.messages))

print("A pushback tug that doesn't report ground speed")
r = rec(); r.update(tel(1000, brake=False))
roll(r, 20, 1001, 3, brake=False, gs_reported=0.0)
check("moving 30 m with ground speed 0 still counts", r.phase == "PUSHBACK", (r.phase, round(getattr(r, "moved_m", 0))))

print("Taxi straight out under power")
r = rec(); r.update(tel(1000, brake=False))
roll(r, 6, 1001, 10, brake=False, engines=True)
check("engines running at taxi speed: straight to taxi out", r.phase == "TAXI_OUT", r.phase)

print("X-Plane parking brake values")
xp = XPlaneSource()
xp._pump = lambda wait=0.0: False          # no network in the test: feed values directly
xp.last_rx = xp.last_sub = time.time()
base = {"lat": O["lat"], "lon": O["lon"]}
xp.values = {**base, "pbrake": 1.0, "pbrake2": 0.0}
check("set only when both values agree (one stuck on)", xp.read().parking_brake is False)
xp.values = {**base, "pbrake": 1.0, "pbrake2": 1.0}
check("set when both say so", xp.read().parking_brake is True)
xp.values = {**base, "pbrake": 1.0}
check("an aircraft without the second value still works", xp.read().parking_brake is True)


class Flaky:
    name = "X-Plane"

    def __init__(self):
        self.tries = 0

    def connect(self):
        self.tries += 1
        if self.tries < 3:
            raise SourceError("No data from X-Plane yet.")

    def read(self):
        return tel(time.time(), brake=True)

    def close(self):
        pass


print("Connecting while X-Plane is still loading")
src = Flaky()
th = TrackerThread(src, rec(), interval=0.05, check_origin=False)
th.stop_flag.wait = lambda s: time.sleep(0.05)       # don't wait 3 s between tries in the test
th.start()
time.sleep(1.0)
check("keeps trying and connects by itself", th.connected and src.tries == 3, (th.connected, src.tries, th.error))
check("reports when the last data arrived", getattr(th, "last_sample", 0) > time.time() - 2)
th.stop(); th.join(2)

print("\n" + ("GATE DEPARTURE TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
