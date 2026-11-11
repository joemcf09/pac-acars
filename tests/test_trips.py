"""Trip pairings: loops from a hub in one type, duty days under 13 h, legs flown in order with layover rest,
per diem at the end. Run from the PAC folder: python tests/test_trips.py"""
import os, shutil, subprocess, sys, tempfile, time, random
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-trips-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, trips as T  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

built = [t for t in (T.build(list(A.ROUTES.values()), A.FLEET, random.Random(i), f"T2611-{i:03d}", time.time()) for i in range(30)) if t]
check("trips can be built from the scheduled network", len(built) >= 10, len(built))
t = built[0]
check("a trip starts and ends at the same hub", t["stations"][0] == t["stations"][-1] == t["hub"] and t["hub"] in T.HUBS)
check("every leg is in the trip's aircraft type", all(l["aircraft"] == [b["aircraft"]] for b in built for l in b["legs"]))
check("legs connect", all(b["legs"][i]["destination"]["icao"] == b["legs"][i + 1]["origin"]["icao"] for b in built for i in range(len(b["legs"]) - 1)))
for b in built:
    days = {}
    for i, l in enumerate(b["legs"]):
        days[l["trip"]["day"]] = days.get(l["trip"]["day"], 0) + l["target_block_min"] + (T.REPORT_MIN if l["trip"]["day"] not in days else T.TURN_MIN)
    ok = all(v <= T.MAX_DUTY_MIN or len([l for l in b["legs"] if l["trip"]["day"] == d]) == 1 for d, v in days.items())
    if not ok:
        break
check("duty days stay within 13 hours (unless a single long leg)", ok, b["id"])

with A.db() as con:
    made = T.refresh(con, A.ROUTES.values(), A.FLEET)
    check("the board fills with open trips", made == T.OPEN_TRIPS, made)
    tid = con.execute("SELECT id FROM trips WHERE status='open'").fetchone()[0]
    try:
        T.leg(con, f"{tid}-1", "PAC0001"); check("legs can't be booked without a bid", False)
    except ValueError:
        check("legs can't be booked without a bid", True)
    T.bid(con, tid, "PAC0001")
    try:
        T.bid(con, con.execute("SELECT id FROM trips WHERE status='open'").fetchone()[0], "PAC0001"); check("one trip at a time", False)
    except ValueError:
        check("one trip at a time", True)
    trip = T._row(con, tid)
    try:
        T.leg(con, f"{tid}-2", "PAC0001"); check("legs must be flown in order", False)
    except ValueError:
        check("legs must be flown in order", True)
    try:
        T.leg(con, f"{tid}-1", "PAC0002"); check("only the bidder may fly it", False)
    except ValueError:
        check("only the bidder may fly it", True)
    now = time.time()
    paid = []
    for i, l in enumerate(trip["legs"]):
        m = T.leg(con, l["id"], "PAC0001", now=now)
        check(f"leg {i + 1} resolves", m and m["id"] == l["id"])
        if i == 0:
            check("a failed leg doesn't move the trip", T.settle(con, "PAC0001", m, {"status": "Failed"}, lambda *a: paid.append(a)) is None and T._row(con, tid)["legs_done"] == 0)
        now += m["target_block_min"] * 60
        res = T.on_filed(con, "PAC0001", m, True, now=now) if i < len(trip["legs"]) - 1 else None
        if l["trip"]["layover"] and i < len(trip["legs"]) - 1:
            nxt = trip["legs"][i + 1]["id"]
            try:
                T.leg(con, nxt, "PAC0001", now=now + 3600); check("the next leg waits for 10 hours' rest", False)
            except ValueError as e:
                check("the next leg waits for 10 hours' rest", "rest" in str(e))
            now += T.REST_MIN * 60 + 60
        if i == len(trip["legs"]) - 1:
            con.execute("UPDATE trips SET started=? WHERE id=?", (time.time() - 2 * 86400, tid))
            out = T.settle(con, "PAC0001", m, {"status": "Delivered", "review_status": "Accepted"}, lambda *a: paid.append(a))
            check("finishing the trip pays per diem for the time away", out and out["per_diem"] > 100 and paid and paid[-1][1] == "per_diem", out)
    check("the trip is done", T._row(con, tid)["status"] == "done")
    b = T.board(con, "PAC0001")
    check("the board shows no trip held after it's done", b["mine"] is None and b["open"])

c = A.app.test_client()
r = c.get("/api/trips")
check("the trips endpoint answers", r.status_code in (200, 401, 302), r.status_code)
print("\n" + ("All trip checks passed." if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
