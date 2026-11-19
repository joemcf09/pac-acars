"""Volumetric loading, stage 1: every type has a cargo volume, a dispatch gets a weight and a volume load factor,
light freight cubes out before dense freight, and none of it touches the score, pay or revenue.
Run from the PAC folder: python tests/test_volume.py"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-volume-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, volume, shipments  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

# ---------------------------------------------------------------- the fleet data
for code, ac in A.FLEET.items():
    cap = volume.capacity_m3(ac)
    ok = cap and 60 <= ac["max_payload_lbs"] / 2.20462 / cap <= 300   # kg per m3 at which the type fills both ways at once
    check(f"{code} has a believable cargo volume", ok, (ac.get("cargo_volume_ft3"), ac.get("max_payload_lbs")))
check("the provisional volumes are marked", A.FLEET["B732F"]["volume_provisional"] and not A.FLEET["B763F"]["volume_provisional"])

# ---------------------------------------------------------------- light freight cubes out, dense freight weighs out
def manifest(contents, lbs, n=10):
    return {"positions": [{"pos": f"M{i}", "contents": contents, "weight_lbs": lbs / n} for i in range(n)]}

ac = A.FLEET["B77F"]
light = volume.load_factors(manifest("Cross-border e-commerce parcels", ac["max_payload_lbs"] * 0.85), ac)
dense = volume.load_factors(manifest("Industrial machinery", ac["max_payload_lbs"] * 0.85), ac)
check("e-commerce on a 777F is limited by volume", light["limited_by"] == "volume" and light["volume_pct"] > light["weight_pct"], light)
check("machinery on a 777F is limited by weight", dense["limited_by"] == "weight" and dense["volume_pct"] < dense["weight_pct"], dense)
check("both carry the same weight load factor", light["weight_pct"] == dense["weight_pct"] == 85.0)
over = volume.load_factors(manifest("Garments on hangers", ac["max_payload_lbs"]), ac)
check("a full weight of garments would not fit in the hold", over["over_volume"] and over["volume_pct"] > 100, over)
check("no volume for the type means no load factor", volume.load_factors(manifest("Mail", 10000), {"max_payload_lbs": 50000}) is None)
check("an empty manifest has no load factor", volume.load_factors({"positions": []}, ac) is None)
check("the figures are informational", light["informational"] is True and not any(k in light for k in ("score", "points", "revenue")))

# ---------------------------------------------------------------- a real dispatch, with its air waybills
m = A.ROUTES["PAC1022"]
booking = {"mission": m, "aircraft": "B733F", "ofp": None, "flight_number": "PAC1022", "airframe": None, "requested_at": 1_789_990_000}
d = A.build_dispatch_with_transfers(booking, [])
shipments.enrich(d)
lf = volume.load_factors(d, A.FLEET["B733F"])
awb_m3 = sum(s["awb_doc"]["vol_m3"] for s in d["shipments"])
check("a real dispatch gets a load factor", lf and lf["weight_pct"] > 0 and lf["volume_pct"] > 0, lf)
check("its volume is the air waybills' volume", lf and abs(lf["volume_ft3"] - awb_m3 * volume.FT3_PER_M3) <= 1, (lf, awb_m3))

print("\nVOLUME TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
