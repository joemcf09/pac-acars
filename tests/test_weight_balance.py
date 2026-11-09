"""Weight and balance for the 737-800 freighter: real envelope, positions and trim; the math adds up; the release and
the load planner use it."""
import copy, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wb, dispatch

failures = []
def check(name, ok, info=""):
    print(("  ok  " if ok else "FAIL  ") + name, "" if ok else info)
    if not ok: failures.append(name)

m = wb.Model("B738F")
d = wb.data("B738F")
# 1. conversions reproduce the source tables exactly
check("%MAC from arm matches the AEI envelope tables", all(abs(m.pct_mac(a) - p) < 0.06 for a, p in
      [(636.4, 6.0), (640.0, 8.3), (645.8, 12.0), (651.1, 15.4), (653.3, 16.8), (677.4, 32.3), (680.6, 34.3), (683.2, 36.0), (675.4, 31.0), (669.4, 27.2), (667.0, 25.6)]))
check("index formula: the reference station is index 45 at any weight", abs(m.index(60000, 658.26) - 45) < 1e-9)
check("index formula matches AEI table 1 (36,287 kg at 6.0% MAC -> 27.41)", abs(m.index(36287, m.arm_of(6.0)) - 27.41) < 0.01, m.index(36287, m.arm_of(6.0)))
check("takeoff limits at a table weight", m.limits("takeoff", 70760) == (8.3, 36.0))
check("takeoff limits interpolate between points", abs(m.limits("takeoff", 74615.5)[0] - 10.15) < 0.01, m.limits("takeoff", 74615.5))
check("trim at a table point (60 t, 16% MAC, flaps 1/5 -> 5.97)", abs(m.trim(60000, 16) - 5.97) < 1e-6, m.trim(60000, 16))
check("trim between rows and columns", 5.36 < m.trim(65000, 18) < 6.66, m.trim(65000, 18))
check("main-deck positions are the real 10 + P12", list(m.d["main_deck"]["positions"][i]["pos"] for i in range(11)) == [f"M{i}" for i in range(1, 11)] + ["P12"])
check("positions are 97 in apart, front to back", all(abs(m.arms[f"M{i+1}"] - m.arms[f"M{i}"] - 97) < 0.01 for i in range(1, 10)))

# 2. a release's balance
units = [{"pos": f"M{i:02d}", "weight_lbs": w} for i, w in zip(range(1, 11), [4000, 5000, 5500, 5800, 6500, 6500, 5800, 5000, 4000, 3000])]
units += [{"pos": "M12", "weight_lbs": 1500}, {"pos": "FWD BULK", "weight_lbs": 1800}, {"pos": "AFT BULK", "weight_lbs": 2200}]
pay = sum(u["weight_lbs"] for u in units)
b = wb.balance("B738F", units, 87400, 21000, 12500)
zf, to, lw = b["phases"]
check("weights add up exactly: ZFW = DOW + payload", zf["weight_lbs"] == 87400 + pay)
check("TOW = ZFW + takeoff fuel; LW = TOW - trip", to["weight_lbs"] == zf["weight_lbs"] + 21000 and lw["weight_lbs"] == to["weight_lbs"] - 12500)
check("CG from moments: ZFW arm is the weighted average", abs(zf["arm_in"] - (87400 * m.basic_arm + sum(u["weight_lbs"] * m.arms[wb.POSITION_MAP['B738F'][u['pos']]] for u in units)) / zf["weight_lbs"]) < 0.06)
fwd = copy.deepcopy(units); fwd[9]["pos"], fwd[0]["pos"] = "M01", "M10"   # swap the 3,000 lb rear unit and 4,000 lb front unit
bf = wb.balance("B738F", fwd, 87400, 21000, 12500)
check("putting the heavier unit at the back moves the CG aft", bf["phases"][0]["pct_mac"] > zf["pct_mac"], (bf["phases"][0]["pct_mac"], zf["pct_mac"]))
heavy_aft = [{"pos": f"M{i:02d}", "weight_lbs": 6400} for i in (6, 7, 8, 9)] + [{"pos": "M10", "weight_lbs": 5400}, {"pos": "AFT BULK", "weight_lbs": 8000}]
ha = wb.balance("B738F", heavy_aft, 87400, 21000, 12500)
lite = wb.balance("B738F", [{"pos": "M05", "weight_lbs": 6000}], 87400, 21000, 12500)
check("an aft-heavy load has a more aft CG than a centered one", ha["phases"][0]["pct_mac"] > lite["phases"][0]["pct_mac"])
over = wb.balance("B738F", [{"pos": "M01", "weight_lbs": 7000}], 87400, 21000, 12500)
check("a unit over its position limit is flagged (M1 max 5,498 lb)", any("M01" in w for w in over["warnings"]) and not over["ok"], over["warnings"])
check("light airplane: main-deck cargo outside M05-M07 is flagged", any("M05 to M07" in w for w in wb.balance("B738F", [{"pos": "M01", "weight_lbs": 2000}], 87400, 3000, 1000)["warnings"]))
bad = wb.balance("B738F", [{"pos": f"M{i:02d}", "weight_lbs": 5400} for i in (1, 2, 3, 4)], 87400, 21000, 12500)
if not bad["within_envelope"]:
    check("out of the envelope gives move advice", "Move about" in (bad["advice"] or ""), bad["advice"])
check("an old release with an M11 unit is reported, not miscalculated", wb.balance("B738F", [{"pos": "M11", "weight_lbs": 1000}], 87400, 1, 1)["available"] is False)
check("types without data return None", wb.balance("B763F", units, 1, 1, 1) is None)
check("fuel fills the wing tanks first", m.fuel_split(10000) == (10000, 0.0) and abs(m.fuel_split(30000)[1] - (30000 - m.main_cap_lbs)) < 1e-6)
check("the 737 is verified by the sim calibration", b["provisional"] is False and b["provisional_note"] is None)
cal = d["calibration"]
for rd in cal["readings"]:
    f = rd["fuel_lbs"]; wing, ctr = m.fuel_split(f)
    arm = (m.basic_lbs * m.basic_arm + wing * m.main_arm + ctr * m.center_arm) / (m.basic_lbs + f)
    check(f"reproduces the PMDG FMC CG at {f:,} lb fuel ({rd['fmc_cg_pct']}%)", abs(m.pct_mac(arm) - rd["fmc_cg_pct"]) < 0.06, round(m.pct_mac(arm), 2))
check("basic weight equals the FMC ZFW (87,375 lb)", round(m.basic_lbs) == 87375)

# 3. manifests and paperwork
fleet = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fleet.json")))
fleet = {k: v for k, v in (fleet.items() if isinstance(fleet, dict) else [])}
code_key = next((k for k in fleet if k in ("B738F", "B738")), None)
FLEET = {"B738F": fleet.get(code_key, {"max_payload_lbs": 52800, "mtow_lbs": 174200, "name": "737"})}
FLEET["B738F"].setdefault("max_payload_lbs", 52800); FLEET["B738F"].setdefault("mtow_lbs", 174200)
mission = {"id": "T1", "title": "Test", "origin": {"icao": "KMIA"}, "destination": {"icao": "MYNN"}, "payload_lbs": 48000, "cargo": "General freight", "category": "Scheduled"}
caps = wb.position_limits_lbs("B738F")
for n in range(6):
    bk = {"flight_number": f"PAC{9000 + n}", "requested_at": 1794000000 + n * 997, "aircraft": "B738F", "mission": mission, "ofp": {"payload_lbs": 40000 + n * 2500}}
    rel = dispatch.generate(bk, FLEET, "Test Pilot")
    names = {p["pos"] for p in rel["positions"]}
    ok_names = names <= set(caps)
    ok_caps = all(p["weight_lbs"] <= caps[p["pos"]] for p in rel["positions"])
    if not (ok_names and ok_caps):
        check(f"manifest {n} uses real positions within limits", False, [(p["pos"], p["weight_lbs"]) for p in rel["positions"]])
        break
else:
    check("generated 737 manifests use M01-M10, M12 and the holds, each within its real limit", True)
paper = dispatch.paperwork(rel, FLEET)
ls = paper["loadsheet"]
check("the release loadsheet uses the verified calculation", ls["cg_source"] == "calculated" and paper["balance"]["available"], ls["cg_source"])
check("loadsheet CG equals the engine's", ls["mac_tow"] == paper["balance"]["phases"][1]["pct_mac"] and ls["mac_ldw"] == paper["balance"]["phases"][2]["pct_mac"])
check("trim on the loadsheet names units and flaps", "UNITS (FLAPS" in ls["trim"], ls["trim"])

# 4. auto-load to a target CG (PAC1150's real load)
pac1150 = [{"pos": p, "weight_lbs": w} for p, w in zip(["M01","M02","M03","M04","M05","M07","M08","M09","M10"], [4640,2100,3820,4240,4230,5120,4220,6400,2380])] + [{"pos": "FWD BULK", "weight_lbs": 1850}]
movable = [f"M{i:02d}" for i in range(1, 11)]
plan = wb.auto_assign("B738F", pac1150, 87375, 10600, 4500, movable)
moved = [{"pos": plan[u["pos"]], "weight_lbs": u["weight_lbs"]} for u in pac1150]
ab = wb.balance("B738F", moved, 87375, 10600, 4500)
check("auto-load keeps every unit and position unique", len(set(plan.values())) == len(plan) == len(pac1150) and plan["FWD BULK"] == "FWD BULK")
check("auto-load lands the takeoff CG within 0.5% of 24% MAC", abs(ab["phases"][1]["pct_mac"] - 24.0) <= 0.5, ab["phases"][1]["pct_mac"])
check("auto-load result is within limits", ab["ok"], ab["warnings"])
print(); print("WEIGHT AND BALANCE TEST PASSED" if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
