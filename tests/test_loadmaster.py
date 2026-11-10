"""Loadmaster score: how well a load is planned (envelope, margin, limits, aft CG, no gaps). Advice only.
Run from the PAC folder: python tests/test_loadmaster.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wb  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

code = "B738F"
pm = wb.POSITION_MAP[code]
mains = sorted(p for p, r in pm.items() if not r.startswith("LOWER"))
good = wb.balance(code, [{"pos": p, "weight_lbs": 3500} for p in mains[:9]], 92000, 20000, 12000)["loadmaster"]
check("an even, gap-free load inside the envelope scores well", good["score"] >= 85 and good["grade"] in ("Excellent", "Good"), good)
check("every part of the score is explained", len(good["items"]) == 5 and sum(i[2] for i in good["items"]) == 100)
heavy_ends = [{"pos": p, "weight_lbs": (9000 if i in (0, 9) else 2000)} for i, p in enumerate(mains[:10])]
he = wb.balance(code, heavy_ends, 92000, 20000, 12000)["loadmaster"]
mid = [{"pos": p, "weight_lbs": (9000 if i in (4, 5) else 2000)} for i, p in enumerate(mains[:10])]
hm = wb.balance(code, mid, 92000, 20000, 12000)["loadmaster"]
check("heavy units at the ends of the hold cost points; in the middle they don't", he["items"][-1][1] < hm["items"][-1][1] == 10, (he["items"][-1], hm["items"][-1]))
bad = wb.balance(code, [{"pos": p, "weight_lbs": 7000} for p in mains[:4]], 92000, 20000, 12000)["loadmaster"]
check("outside the envelope: zero, and it says where", bad["score"] == 0 and "outside the envelope" in bad["items"][0][0], bad)
check("no weight-and-balance data: no score", wb.balance("A306F", [], 1, 1, 1) is None or (wb.balance("A306F", [], 1, 1, 1) or {}).get("loadmaster") is None)

print("\nLOADMASTER TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
