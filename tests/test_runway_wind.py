"""Runway wind analysis on the release: head/tailwind and crosswind for each runway from the METAR, gusts included.
Run from the PAC folder: python tests/test_runway_wind.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import analysis, runway_wind  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

h, x = runway_wind.components(270, 20, 270)
check("wind straight down the runway: all headwind", round(h) == 20 and round(x) == 0)
h, x = runway_wind.components(360, 20, 270)
check("wind from the right at 90 degrees: all crosswind, from the right", round(h) == 0 and round(x) == 20)
h, x = runway_wind.components(90, 15, 270)
check("wind from behind: tailwind", round(h) == -15)

kcvg = analysis.runways(ROOT / "data").get("KCVG")
check("runway data for KCVG", bool(kcvg))
rw = runway_wind.analyse(kcvg, {"dir": 360, "spd": 18, "gust": 28, "vrb": False}, 8000)
best = rw["ends"][0]
check("a north wind favors runway 36L/36C/36R at KCVG", best["runway"].startswith("36") and best.get("favored"), best)
check("gusts are worked out too", best["gust_head"] > best["head"], best)
worst = [e for e in rw["ends"] if e["runway"].startswith("18")]
check("the opposite runways show the tailwind and say so", worst and worst[0]["head"] < -10 and "tailwind over 10 kt" in worst[0]["notes"], worst[:1])
cross = runway_wind.analyse(kcvg, {"dir": 270, "spd": 32, "gust": None, "vrb": False})
check("a strong crosswind is flagged on runways across it", any("crosswind over 30 kt" in e["notes"] for e in cross["ends"] if e["runway"].startswith(("18", "36"))))
check("calm wind: any runway", runway_wind.analyse(kcvg, {"dir": 0, "spd": 0, "gust": None, "vrb": False})["calm"])
check("variable wind: no favored runway", not any(e.get("favored") for e in runway_wind.analyse(kcvg, {"dir": None, "spd": 4, "gust": None, "vrb": True})["ends"]))
short = runway_wind.analyse(kcvg, {"dir": 90, "spd": 10, "gust": None, "vrb": False}, 20000)
check("runways shorter than the aircraft needs are flagged and go last", all(e["short"] for e in short["ends"]) and "shorter" in short["ends"][0]["notes"][-1])
check("no wind or no runways: nothing", runway_wind.analyse(kcvg, None) is None and runway_wind.analyse([], {"dir": 1, "spd": 5}) is None)

print("\nRUNWAY WIND TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
