"""MSFS touchdown-rate values must be fresh before they replace vertical-speed samples.

Run from the PAC folder: python tests/test_landing_measurement.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sim_sources import MSFSSource  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


class Reading:
    def __init__(self, value):
        self.value = value


def source_with(**updates):
    values = {
        "lat": 35.2, "lon": -80.9, "alt": 760.0, "ind_alt": 760.0, "agl": 0.0,
        "ias": 135.0, "gs": 125.0, "vs": -100.0, "hdg": 180.0, "on_ground": 1,
        "eng1": 1, "eng2": 1, "eng3": 0, "eng4": 0, "pbrake": 0, "fuel": 10000.0,
        "weight": 140000.0, "gear": 1, "flaps": 0.5, "g": 1.0, "td": 419.0,
        "slew": 0, "pitch": 0.0, "rate": 1.0, "abstime": None, "bank": None,
        "beacon": None, "landing_lt": None, "strobe": None, "nav_lt": None,
        "taxi_lt": None, "n_eng": 2,
    }
    values.update(updates)
    source = MSFSSource()
    source.req = {key: Reading(value) for key, value in values.items()}
    return source


def record_landing(sample, forced=None):
    airport = {"icao": "KCLT", "lat": 35.2, "lon": -80.9}
    recorder = FlightRecorder({"flight_number": "PAC0001", "aircraft": "B738F",
                               "mission": {"origin": airport, "destination": airport}})
    recorder.recent_vs = [(sample.t - 0.25, -100.0), (sample.t - 0.1, -100.0)]
    if forced:
        forced.update({"lat": sample.lat, "lon": sample.lon, "ias": sample.ias})
    recorder._touchdown_at(sample.t, sample, forced=forced)
    return recorder.landing


print("Stale SimConnect touchdown value")
source = source_with(td=419.0, on_ground=1)
initial = source.read()
check("an existing touchdown value is treated as a baseline", initial.touchdown_fpm is None, initial.touchdown_fpm)
source.req["on_ground"].value = 0
airborne = source.read()
check("the old value stays unavailable in flight", airborne.touchdown_fpm is None, airborne.touchdown_fpm)
source.req["on_ground"].value = 1
stale = source.read()
landing = record_landing(stale)
check("stale -419 fpm cannot override current -100 fpm samples",
      landing["rate_fpm"] == -100 and landing["rate_source"] == "vertical_speed", landing)

print("Fresh SimConnect touchdown value")
source = source_with(td=0.0, on_ground=0)
source.read()
source.req["td"].value = 419.0
source.req["on_ground"].value = 1
fresh = source.read()
check("a newly observed touchdown value is retained", fresh.touchdown_fpm == -419.0, fresh.touchdown_fpm)
source._fresh_touchdown_time -= 0.6
debounced = source.read()
check("the fresh value survives the ground-confirmation debounce",
      debounced.touchdown_fpm == -419.0, debounced.touchdown_fpm)
landing = record_landing(debounced)
check("the record identifies both rate sources for review",
      landing["rate_fpm"] == -419 and landing["rate_source"] == "sim_touchdown"
      and landing["vs_rate_fpm"] == -100 and landing["touchdown_fpm"] == -419, landing)
bounced_landing = record_landing(
    debounced, {"rate": -100, "vs_rate": -100, "touchdown_fpm": -419})
check("a bounce preserves the first contact's measured rate and comparison",
      bounced_landing["rate_fpm"] == -419 and bounced_landing["rate_source"] == "sim_touchdown"
      and bounced_landing["vs_rate_fpm"] == -100, bounced_landing)

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
