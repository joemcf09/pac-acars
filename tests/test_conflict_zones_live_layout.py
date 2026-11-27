"""Conflict zones work with the live server's layout, where pilot data (PAC_DATA_DIR) lives apart from the release
and the country outlines ship with the code. Before the fix only the two hand-drawn caution areas showed on the maps
and no restricted country did. Run from the PAC folder: python tests/test_conflict_zones_live_layout.py"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-zones-") as temp:
        data = Path(temp) / "data"; data.mkdir()       # like shared/data on the server: no reference files in it
        (data / "settings.json").write_text(json.dumps({"conflict_zones_enabled": True}))
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

check("pilot data really is separate from the release here", A.DATA != A.RESOURCE_DATA and not (A.DATA / "conflict_zones_shapes.json").exists())
feats = A.app.test_client().get("/api/conflict-zones/map").json["features"]
levels = {f["properties"]["id"]: f["properties"]["level"] for f in feats}
check("restricted countries are on the map", levels.get("russia") == "restricted" and levels.get("ukraine") == "restricted", levels)
check("so are the country caution areas, not just the hand-drawn ones", levels.get("somalia") == "caution" and levels.get("haiti") == "caution", levels)
check("every zone with an outline is drawn", len(feats) >= 20, len(feats))
import conflict_zones as Z  # noqa: E402
st = {"conflict_zones_enabled": True}
z = Z.assess({"icao": "EPWA"}, {"icao": "UUEE"}, None, st, A.RESOURCE_DATA)
check("a flight into Russia is still judged restricted", z and z.get("level") == "restricted", z)
z = Z.assess({"icao": "EDDF"}, {"icao": "OMDB"}, [(50.0, 8.6), (45.0, 35.0), (34.0, 45.0), (25.2, 55.4)], st, A.RESOURCE_DATA)
check("a track over Ukraine and Iraq is caught by the outlines", z and z.get("level") == "restricted", z)

print("\nCONFLICT ZONE LIVE LAYOUT TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
