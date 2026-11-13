"""Read-only profitability report: where PAC's money goes, month by month, by aircraft type and by flight.
Run on the server:  sudo -u pac python3 tools/profit_report.py   (changes nothing)"""
import json, os, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timezone

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
data = os.environ.get("PAC_DATA_DIR") or os.path.join(here, "data")
con = sqlite3.connect(os.path.join(data, "pac.db") if os.path.exists(os.path.join(data, "pac.db")) else
                      next(os.path.join(data, f) for f in os.listdir(data) if f.endswith(".db")))
con.row_factory = sqlite3.Row
month = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m")
m = defaultdict(lambda: defaultdict(float)); types = defaultdict(lambda: defaultdict(float)); flights = []
for r in con.execute("""SELECT id, filed_at, flight_number, dep, arr, aircraft, revenue, cost, payload_lbs, detail FROM pireps
        WHERE demo=0 AND review_status='Accepted' AND revenue IS NOT NULL"""):
    eco = (json.loads(r["detail"] or "{}").get("economics") or {})
    costs = eco.get("costs") or {"other": r["cost"] or 0}
    k = month(r["filed_at"]); m[k]["revenue"] += r["revenue"] or 0; m[k]["flights"] += 1
    for c, v in costs.items(): m[k]["cost:" + c] += v or 0
    t = types[r["aircraft"] or "?"]; t["revenue"] += r["revenue"] or 0; t["cost"] += sum(costs.values()); t["flights"] += 1
    flights.append(((r["revenue"] or 0) - sum(costs.values()), r["flight_number"], r["dep"], r["arr"], r["aircraft"], r["payload_lbs"],
                    {c: round(v) for c, v in costs.items() if v and v > 20000}))
try:
    for r in con.execute("SELECT time, kind, amount FROM company_ledger"): m[month(r["time"])]["ledger:" + r["kind"]] += r["amount"] or 0
except sqlite3.Error: pass
for r in con.execute("SELECT time, kind, amount FROM wallet WHERE kind IN ('per_diem','profit_share','campaign','mentoring','hotel')"):
    m[month(r["time"])]["pilots:" + r["kind"]] += r["amount"] or 0
for k in sorted(m)[-4:]:
    s = m[k]; cost = sum(v for x, v in s.items() if x.startswith("cost:")); led = sum(v for x, v in s.items() if x.startswith("ledger:"))
    ppl = sum(v for x, v in s.items() if x.startswith("pilots:"))
    print(f"\n== {k}: {int(s['flights'])} flights  revenue ${s['revenue']:,.0f}  flight costs ${cost:,.0f}  other ${led:,.0f}  pilot pay ${ppl:,.0f}  NET ${s['revenue']-cost-ppl+led:,.0f}")
    for x, v in sorted(s.items(), key=lambda kv: -abs(kv[1])):
        if x not in ("revenue", "flights"): print(f"   {x:28s} {v:>14,.0f}")
print("\n== By aircraft type (all time)")
for a, t in sorted(types.items(), key=lambda kv: kv[1]["revenue"] - kv[1]["cost"]):
    print(f"   {a:7s} {int(t['flights']):4d} flights  revenue ${t['revenue']:>12,.0f}  cost ${t['cost']:>12,.0f}  margin {((t['revenue']-t['cost'])/max(1,t['revenue'])*100):6.1f}%")
print("\n== 10 biggest losing flights")
for f in sorted(flights)[:10]: print(f"   ${f[0]:>12,.0f}  {f[1]} {f[2]}-{f[3]} {f[4]} {f[5] or 0:,.0f} lb  big costs: {f[6]}")
