"""Operating rules on the release: night curfews, slot-coordinated airports and ETOPS for twins.
Run from the PAC folder: python tests/test_ops_rules.py"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-ops-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, ops_rules as O  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

late = O.rules({"origin": {"icao": "KCVG"}, "destination": {"icao": "EDDF"}, "date": "11 NOV 2026", "std": "2000Z", "sta": "0350Z", "aircraft": "B763F"}, A.AIRPORTS)
kinds = {r["kind"]: r for r in late}
check("arriving Frankfurt at 0450 local is inside its night curfew", kinds.get("curfew", {}).get("warn") and "0450 LOCAL" in kinds["curfew"]["text"], late)
check("Frankfurt is slot coordinated", "slot" in kinds)
check("a twin across the Atlantic needs ETOPS", kinds.get("etops") and "ETOPS 1" in kinds["etops"]["text"])
day = O.rules({"origin": {"icao": "KCVG"}, "destination": {"icao": "EDDF"}, "date": "11 NOV 2026", "std": "1400Z", "sta": "2150Z", "aircraft": "B763F"}, A.AIRPORTS)
check("a daytime arrival is outside the curfew", not [r for r in day if r["kind"] == "curfew" and r["warn"]])
check("summer time is handled (Frankfurt is UTC+2 in July)", O.curfew("EDDF", O._when("15 JUL 2026", "2030Z"))["local"] == "2230")
quad = O.rules({"origin": {"icao": "PHNL"}, "destination": {"icao": "KLAX"}, "date": "11 NOV 2026", "std": "1000Z", "sta": "1500Z", "aircraft": "B748F"}, A.AIRPORTS)
check("four-engine freighters are exempt from ETOPS", not [r for r in quad if r["kind"] == "etops"])
twin = O.rules({"origin": {"icao": "PHNL"}, "destination": {"icao": "KLAX"}, "date": "11 NOV 2026", "std": "1000Z", "sta": "1500Z", "aircraft": "B763F"}, A.AIRPORTS)
check("Honolulu to Los Angeles in a 767 needs ETOPS 180", any("ETOPS 180" in r["text"] for r in twin), twin)
domestic = O.rules({"origin": {"icao": "KCVG"}, "destination": {"icao": "KIND"}, "date": "11 NOV 2026", "std": "1400Z", "sta": "1450Z", "aircraft": "B738F"}, A.AIRPORTS)
check("a short domestic hop has no restrictions", domestic == [], domestic)
check("the release prints them and the deicing note", all(x in (ROOT / "static" / "dispatch.html").read_text(encoding="utf-8") for x in ("OPERATING RESTRICTIONS", "function deiceNote")))
print("\nOPS RULES TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
