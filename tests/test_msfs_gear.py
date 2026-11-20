"""MSFS gear readings for the live approach coach. Run: python tests/test_msfs_gear.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim_sources import MSFSSource  # noqa: E402


def read_gear(handle, extended):
    source = MSFSSource()
    values = {
        "lat": 69.68, "lon": 18.92, "alt": 1000, "agl": 500,
        "ias": 130, "gs": 130, "vs": -700, "hdg": 180,
        "on_ground": 0, "gear": handle, "gear_extended": extended,
    }
    source._v = lambda key, refresh=True: values.get(key)
    return source.read().gear_down


assert MSFSSource.VARS["gear"][1] == "percent over 100"
assert MSFSSource.VARS["gear_extended"][1] == "percent"
assert read_gear(0, 100), "physical extension should override a stale PMDG handle value"
assert read_gear(1, 0), "an aircraft without a working extension value should keep the handle fallback"
assert not read_gear(0, 0), "two clear gear-up readings must still trigger the warning"
assert read_gear(None, None), "unavailable readings must not claim gear up"
print("MSFS gear source checks passed")
