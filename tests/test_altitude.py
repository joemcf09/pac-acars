"""PAC ACARS shows the altimeter altitude (the flight level at cruise), not the true height above sea level.

Run from the PAC folder:   python tests/test_altitude.py
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim_sources import MSFSSource, XPlaneSource, altimeter_alt, M_TO_FT  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


class R:
    def __init__(self, v): self.value = v


BASE = {"lat": 39.0, "lon": -84.6, "agl": 37000.0, "ias": 251.0, "gs": 429.0, "vs": -75.0, "hdg": 257.0, "on_ground": 0,
        "eng1": 1, "eng2": 1, "eng3": 0, "eng4": 0, "pbrake": 0, "fuel": 7926.0, "weight": 140000.0, "gear": 0, "flaps": 0.0,
        "g": 1.0, "td": 0, "slew": 0, "pitch": -2.5, "rate": 1.0, "abstime": None}


def msfs(alt, ind):
    s = MSFSSource()
    vals = dict(BASE, alt=alt, ind_alt=ind)
    s.req = {k: R(vals.get(k)) for k in MSFSSource.VARS}
    return s.read()


print("MSFS")
t = msfs(37504.0, 36001.0)   # Alex's flight: FL360 on a warm day
check("shows the altimeter: FL360", round(t.alt_ft) == 36001, t.alt_ft)
check("keeps the true altitude too", round(t.true_alt_ft) == 37504, t.true_alt_ft)
t = msfs(37504.0, None)
check("no altimeter reading: true altitude", round(t.alt_ft) == 37504, t.alt_ft)

print("X-Plane")
x = XPlaneSource()
x._pump = lambda wait=0.0: False
x.last_rx = x.last_sub = time.time()
x.values = {"lat": 39.0, "lon": -84.6, "elev_m": 37504 / M_TO_FT, "agl_m": 11000.0, "ias": 251.0, "gs_ms": 220.0,
            "vs_fpm": 0.0, "hdg": 257.0, "on_ground": 0.0, "eng1": 1.0, "ind_alt_ft": 36000.0}
t = x.read()
check("shows the altimeter: FL360", round(t.alt_ft) == 36000, t.alt_ft)
check("keeps the true altitude", round(t.true_alt_ft) == 37504, t.true_alt_ft)
del x.values["ind_alt_ft"]
check("aircraft without the default altimeter: true altitude", round(x.read().alt_ft) == 37504)

print("Bad readings")
check("altimeter far off (stuck at 0 in flight): true altitude", altimeter_alt(0.0, 36000.0) == 36000.0)
check("normal readings close together: altimeter", altimeter_alt(35900.0, 37400.0) == 35900.0)

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
