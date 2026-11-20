"""Volumetric loading, stage 2: with the setting on, a booking carries only what fits in the hold, bulky freight cubes out
below the weight limit, PAC prices on chargeable weight, and with the setting off nothing changes at all.
Run from the PAC folder: python tests/test_volume_stage2.py"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-volume2-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, volume, economics, shipments  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

ON, OFF = {"volumetric_loading": True}, {"volumetric_loading": False}
textiles = A.ROUTES["PAC2020"]                         # textile inputs: light, bulky freight (about 93 kg/m3)
machinery = dict(textiles, id="TESTMACH", cargo="Industrial machinery")

# ---------------------------------------------------------------- the switch
check("the setting is off by default", A.settings().get("volumetric_loading") is False)
check("with it off the mission is untouched", volume.booking_mission(textiles, "B752F", A.FLEET, OFF) is textiles)

# ---------------------------------------------------------------- what gets capped
capped = volume.booking_mission(textiles, "B752F", A.FLEET, ON)
vc = capped.get("volume_cap") or {}
check("bulky freight on a 757 is cut to what fits", capped is not textiles and capped["payload_lbs"] < min(textiles["payload_lbs"], A.FLEET["B752F"]["max_payload_lbs"]), vc)
check("the original mission is not changed", textiles["payload_lbs"] == 78500 and "volume_cap" not in textiles)
check("the cap records why", vc.get("from_lbs") == 78500 and vc.get("density_kg_m3", 999) < 120 and vc.get("chargeable_factor", 0) > 1.3, vc)
check("the cap is what the hold holds at that density",
      abs(vc["lbs"] - volume.capacity_m3(A.FLEET["B752F"]) * volume.UTILISATION * vc["density_kg_m3"] * 2.20462) <= 500, vc)
check("dense freight weighs out first, so it is not capped", volume.booking_mission(machinery, "B752F", A.FLEET, ON) is machinery)
check("a ferry flight is never capped", volume.booking_mission(dict(textiles, category="Ferry"), "B752F", A.FLEET, ON).get("volume_cap") is None)
check("a training flight is never capped", volume.booking_mission(dict(textiles, training={"id": "x"}), "B752F", A.FLEET, ON).get("volume_cap") is None)
check("capping twice changes nothing", volume.booking_mission(capped, "B752F", A.FLEET, ON) is capped)

# ---------------------------------------------------------------- the load sheet follows the capped payload
booking = {"mission": capped, "aircraft": "B752F", "ofp": None, "flight_number": "PAC2020", "airframe": None, "requested_at": 1_789_990_000}
d = A.build_dispatch_with_transfers(booking, [])
shipments.enrich(d)
loaded = sum(p["weight_lbs"] for p in d["positions"])
lf = volume.load_factors(d, A.FLEET["B752F"])
check("the load sheet carries the capped weight", abs(loaded - vc["lbs"]) <= 50, (loaded, vc["lbs"]))
check("and it reads as volume limited, close to a full hold", lf["limited_by"] == "volume" and 75 <= lf["volume_pct"] <= 115, lf)

# ---------------------------------------------------------------- pay: chargeable weight
dist = 1500
price_on, _ = economics.contract(capped, A.FLEET, ON, dist)
price_actual, _ = economics.contract(dict(capped, volume_cap=None), A.FLEET, OFF, dist)
check("a cubed-out flight is priced on chargeable weight, above its actual weight", price_on > price_actual, (price_on, price_actual))
est = economics.estimate(capped, "B752F", A.FLEET, ON, dist)
check("the capped flight delivers its whole (capped) load, so revenue is the full contract", est["revenue"] == est["contract_price"], est)

# ---------------------------------------------------------------- end to end, through the website
A.SETTINGS_PATH.write_text(json.dumps(ON))
client = A.app.test_client()
with A.db() as con:
    con.execute("INSERT OR IGNORE INTO pilots (id, name) VALUES ('PAC0001', 'Joseph Pagani')")
    con.execute("UPDATE pilots SET password_hash='x', status='Active' WHERE id='PAC0001'")
with client.session_transaction() as sess:
    sess["pid"] = "PAC0001"
saved = client.post("/api/settings", json={"volumetric_loading": True})
check("the switch saves without a separate form submit", saved.status_code == 200 and saved.json.get("volumetric_loading") is True)
check("the staff page reloads the saved switch", client.get("/api/staff/overview").json["rules"].get("volumetric_loading") is True)
client.post("/api/settings", json={"volumetric_loading": False})
check("the staff page reloads the switched-off state", client.get("/api/staff/overview").json["rules"].get("volumetric_loading") is False)
client.post("/api/settings", json={"volumetric_loading": True})
check("the app script revalidates on reload", client.get("/static/app.js?v=20261120cargo1").headers.get("Cache-Control") == "no-cache")
check("Academy sample PDFs revalidate on reload", "max-age=0" in client.get("/academy/pac-sample-awb.pdf?v=20261120logo").headers.get("Cache-Control", ""))
resp = client.post("/api/economics/estimate", json={"mission_id": "PAC2020", "aircraft": "B752F"})
r = resp.get_json() or {}
check("the dossier estimate sends the payload that fits", (r.get("volume_cap") or {}).get("lbs") == vc["lbs"] and r.get("payload_lbs") == vc["lbs"], r.get("volume_cap"))
r2 = client.post("/api/economics/estimate", json={"mission_id": "PAC2020", "aircraft": "B763F"}).get_json()
check("a bigger hold carries it all, so no cap", r2.get("volume_cap") is None and r2.get("payload_lbs") == 78500, r2.get("volume_cap"))
A.SETTINGS_PATH.write_text(json.dumps(OFF))
r3 = client.post("/api/economics/estimate", json={"mission_id": "PAC2020", "aircraft": "B752F"}).get_json()
check("with the setting off the estimate is the old one", r3.get("volume_cap") is None and r3.get("payload_lbs") == 78500, r3.get("volume_cap"))

print("\nVOLUME STAGE 2 TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
