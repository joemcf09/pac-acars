"""The load sheet carries what the mission says: racehorses are racehorses, not someone's general freight.
Run from the PAC folder: python tests/test_cargo_matches_mission.py"""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dispatch, shipments  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
p = dispatch.pool_for("Thoroughbred racehorses in stalls with grooms", "Racehorses")
check("racehorses are on the manifest, as live animals", p[0][0].startswith("Thoroughbred racehorses") and "AVI" in p[0][1], p)
check("and the shipper comes from the racehorse business", shipments.sector_for(p[0][0]) == "racehorses")
check("an unknown cargo goes on the manifest in the mission's own words", dispatch.pool_for("Hotel and resort supplies", "x")[0][0] == "Hotel and resort supplies")
check("isotopes are radioactive dangerous goods on the NOTOC", dispatch.pool_for("Medical isotopes in shielded containers", "")[0][2] == "rry")
src = (ROOT / "va.py").read_text() + (ROOT / "missiongen.py").read_text()
generic = [c for m in re.finditer(r'"cargo": \[([^\]]*)\]', src) for c in re.findall(r'"([^"]+)"', m.group(1)) if dispatch.pool_for(c, "") is dispatch.GENERAL]
check("no mission falls back to unrelated general freight", not generic, generic)
print("\nCARGO MATCHES MISSION TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
