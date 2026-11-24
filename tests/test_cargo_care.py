"""Cargo that feels the flight: cold chain, live animals and fragile freight react to how the flight was flown.
Run from the PAC folder: python tests/test_cargo_care.py"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-care-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import cargo_care as C  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

flowers = {"awb": "901-1", "contents": "Fresh-cut flowers", "shc": ["PEF", "PER", "COL"]}
pups = {"awb": "901-2", "contents": "Live animals", "shc": ["AVI"]}
wafers = {"awb": "901-3", "contents": "Semiconductor wafers", "shc": ["VAL", "CRT"]}
mail = {"awb": "901-4", "contents": "Mail bags", "shc": ["MAL"]}
mia, bog = {"icao": "KMIA", "lat": 25.8}, {"icao": "SKBO", "lat": 4.7}
def rec(taxi_out=12, taxi_in=6, temp_arr=None, rough=0, bank=20, max_g=1.3, bounces=0):
    return NS(oooi={"out": 0, "off": taxi_out * 60, "on": 3600, "in": 3600 + taxi_in * 60}, ride={"max_g": max_g, "min_g": 0.8, "rough": rough, "max_bank": bank, "steep_s": 0},
              max_g=max_g, bounces=bounces, landing_wx={"temp_c": temp_arr} if temp_arr is not None else None)
print("Which freight reacts")
r = C.assess([flowers, pups, wafers, mail], rec(), {"g": 1.2}, bog, mia)
check("flowers, animals and wafers are tracked; mail isn't", [x["kind"] for x in r] == ["cold", "animals", "fragile"], r)
check("a gentle, quick flight keeps everything fine", all(x["status"] == "ok" for x in r), [(x["label"]) for x in r])
print("Cold chain")
hot = C.assess([flowers], rec(taxi_in=25, temp_arr=34), {"g": 1.2}, bog, mia)[0]
check("a long taxi into a 34°C ramp is a temperature excursion", hot["status"] == "excursion" and "34°C" in " ".join(hot["log"]), hot)
est = C.assess([flowers], rec(), {"g": 1.2}, bog, mia)[0]
check("without a METAR the temperature is labeled as an estimate", "estimated" in " ".join(est["log"]), est)
print("Live animals")
rough = C.assess([pups], rec(rough=3, bank=40), {"g": 1.7}, bog, mia)[0]
check("turbulence, steep banks and a firm landing distress animals", rough["status"] == "excursion" and "distressed" in rough["label"], rough)
print("Fragile")
hard = C.assess([wafers], rec(), {"g": 1.9}, bog, mia)[0]
check("a 1.9 G landing damages fragile freight", hard["status"] == "excursion" and "1.90 G" in hard["log"][0], hard)
firm = C.assess([wafers], rec(bounces=1), {"g": 1.5}, bog, mia)[0]
check("one bounce is a hard handling, inspected, no damage", firm["status"] == "watch", firm)

print("Through a real PIREP")
import debrief  # noqa: E402
p = {"status": "Delivered", "arr": "KMIA", "dep": "SKBO", "flight_number": "PAC1", "block_min": 60, "payload_lbs": 1000,
     "cargo_care": C.assess([wafers], rec(), {"g": 1.9}, bog, mia), "landing_rate": -650, "landing_g": 1.9}
booking = {"mission": {"origin": {"icao": "SKBO"}, "destination": {"icao": "KMIA"}}, "aircraft": "B763F", "flight_number": "PAC1", "requested_at": 1,
           "dispatch": {"shipments": [{**wafers, "shipper": {"name": "TSMC"}, "consignee": {"name": "Apple"}, "pieces": 4, "weight_lbs": 900,
                                       "destination": {"icao": "KMIA"}, "awb_doc": {}}], "deck": {}}}
try:
    db = debrief.build(p, booking, NS(oooi={"in": 3600}, fuel={}, ofp=None), {"B763F": {}})
    check("the customer says it arrived damaged", db["customer"]["tone"] == "bad" and "damaged" in db["customer"]["text"], db["customer"])
    check("and the cargo results carry the condition", db["cargo"][0]["care"]["label"] == "Damaged in transit", db["cargo"][0])
except Exception as e:
    check("debrief builds with cargo care", False, repr(e))

print("PAC's own freight")
kit = {"awb": "999-1", "contents": "AOG kit", "shc": [], "shipper": {"name": "PAC Engineering Stores"}, "consignee": {"name": "PAC AOG Team Detroit"},
       "pieces": 3, "weight_lbs": 800, "destination": {"icao": "KDTW"}, "awb_doc": {}}
p2 = {"status": "Delivered", "arr": "KDTW", "dep": "KCVG", "flight_number": "PAC8800", "block_min": 50, "payload_lbs": 800, "landing_rate": -120}
b2 = {"mission": {"origin": {"icao": "KCVG"}, "destination": {"icao": "KDTW"}}, "aircraft": "B763F", "flight_number": "PAC8800", "requested_at": 2,
      "dispatch": {"shipments": [kit], "deck": {}}}
try:
    cu = debrief.build(p2, b2, NS(oooi={"in": 3600}, fuel={}, ofp=None), {"B763F": {}})["customer"]
    check("an AOG kit to PAC's own team is feedback from colleagues, not a customer", cu["label"] == "From the receiving team"
          and "book PAC again" not in cu["text"] and "customer" not in cu["text"].lower(), cu)
    check("a customer delivery is still labelled as customer feedback", db["customer"]["label"] == "Customer feedback", db["customer"])
except Exception as e:
    check("debrief builds for PAC's own freight", False, repr(e))
print(); print("All cargo care checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
