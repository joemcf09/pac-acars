"""A landing or takeoff must find its runway even if something earlier asked for runways from a folder that has no
runways.json (pilot data on the server). Run from the PAC folder: python tests/test_runway_cache.py"""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import analysis  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

with tempfile.TemporaryDirectory() as empty:
    analysis._RUNWAYS = None
    first = analysis.runways(Path(empty))                      # the wrong folder, asked first
    check("a folder without runways.json still gives the runway table", "KSJC" in first and "KBFL" in first)
    analysis._RUNWAYS = None
    analysis.runways(Path(empty))
    check("and asking again with the right folder works", "KSJC" in analysis.runways(ROOT / "data"))

# a touchdown on KSJ 12R, 600 m past the threshold, must match its runway after the wrong-folder lookup
analysis._RUNWAYS = None
with tempfile.TemporaryDirectory() as empty:
    analysis.runways(Path(empty))
rw = analysis.runways(ROOT / "data")["KSJC"][1]               # 12R / 30L
import math
h = math.radians(rw[3]); lat0, lon0 = rw[1], rw[2]
lat = lat0 + 600 * math.cos(h) / 111_320.0
lon = lon0 + 600 * math.sin(h) / (111_320.0 * math.cos(math.radians(lat0)))
series = [[t, max(0, 40 - t * 40), -250, 140, 1.1, lat, lon, rw[3], 1 if t >= 1 else 0, 130] for t in (0.0, 0.5, 1.0, 1.5)]
res = analysis.analyze_landing(series, 1.0, -250, 1.1, ["KSJC"], ROOT / "data", 240)
check("a landing at KSJC finds runway 12R", res and res.get("runway") == "12R", res and res.get("runway"))
print("\nRUNWAY CACHE TEST PASSED" if not failures else f"\n{len(failures)} FAILED")
sys.exit(1 if failures else 0)
