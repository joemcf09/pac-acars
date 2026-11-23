"""Anonymous usage counts (usage.py): pages opened, visitors per day, load times and script errors, for staff only,
with no IP addresses, pilot IDs or cookies stored. Run from the PAC folder: python tests/test_usage.py"""
import os, shutil, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-usage-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, usage, app_bundle  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

client = A.app.test_client()
UA = {"User-Agent": "Mozilla/5.0 test"}
def beacon(body, ip="203.0.113.7", ua=UA):
    # as it arrives in production: from a Cloudflare server, with the visitor's address in CF-Connecting-IP
    return client.post("/api/usage", json=body, headers={**ua, "CF-Connecting-IP": ip}, environ_base={"REMOTE_ADDR": "162.158.10.20"})

r = beacon({"view": "missions", "kind": "pilot", "device": "desktop"})
check("a guest browser can send a beacon (no sign-in needed)", r.status_code == 204, r.status_code)
beacon({"view": "missions", "kind": "pilot", "device": "desktop"})                 # same visitor, again
beacon({"view": "missions", "kind": "pilot", "device": "desktop"}, ip="198.51.100.9")  # someone else
beacon({"view": "home", "kind": "guest", "device": "phone"}, ip="198.51.100.20")
beacon({"view": "../../etc", "kind": "pilot"})                                     # not a page name
beacon({"view": "missions", "kind": "admin", "device": "fridge"}, ip="198.51.100.30")  # unknown kind/device fall back
client.post("/api/usage", data='{"view":"fleet","kind":"guest","device":"tablet"}', headers={**UA, "Content-Type": "text/plain"})  # sendBeacon sends text/plain

rep = usage.report(7)
pages = {p["view"]: p for p in rep["pages"]}
check("page opens are counted", pages.get("missions", {}).get("opens") == 4, pages.get("missions"))
check("a visitor opening a page twice is one visitor", pages["missions"]["visitors"] == 3, pages["missions"])
check("pilots and guests are told apart", pages["missions"]["pilot"] == 3 and pages["missions"]["guest"] == 1 and pages["home"]["guest"] == 1)
check("phones are counted", pages["home"]["phone"] == 1)
check("a beacon sent as plain text (sendBeacon) counts", "fleet" in pages)
check("made-up page names are ignored", not any("/" in v or "." in v for v in pages))
check("visitors per day are counted once each", rep["daily"][-1]["visitors"] == 5, rep["daily"])

# what is (not) stored
con = sqlite3.connect(A.DATA / "usage.db")
dump = "\n".join(con.iterdump())
check("no IP address is stored", "203.0.113.7" not in dump and "198.51.100.9" not in dump)
check("no browser string is stored", "Mozilla" not in dump)
check("the usage counts are kept apart from the logbook", not (A.DATA / "logbook.db").exists() or "views" not in
      [r[0] for r in sqlite3.connect(A.DATA / "logbook.db").execute("SELECT name FROM sqlite_master")])

# a new day forgets yesterday's fingerprints and key
tomorrow = time.time() + 86400
usage.record({"view": "home", "kind": "guest", "device": "phone"}, "198.51.100.20", "Mozilla/5.0 test", now=tomorrow)
days = {r[0] for r in con.execute("SELECT day FROM seen")} | {r[0] for r in con.execute("SELECT day FROM day_keys")}
check("fingerprints and the daily key are deleted the next day", days == {usage._day(tomorrow)}, days)
check("but the daily totals stay", con.execute("SELECT COUNT(*) FROM views WHERE day=?", (usage._day(),)).fetchone()[0] >= 3)
con.close()

# load times and script errors
beacon({"load_ms": 1450, "kind": "guest", "device": "phone"}, ip="198.51.100.41")
beacon({"load_ms": 9000, "kind": "guest", "device": "phone"}, ip="198.51.100.42")
text, _ = app_bundle.source()
line = text.split("\n").index(next(l for l in text.split("\n") if l.startswith("function renderStaff()"))) + 1
beacon({"error": {"message": "x is not defined", "place": f"/static/app.js:{line}"}, "kind": "staff"}, ip="198.51.100.43")
rep = usage.report(7)
check("load times fall in their buckets", rep["loads"].get("phone") == [0, 1, 0, 0, 0, 1], rep["loads"])
err = rep["errors"][0] if rep["errors"] else {}
check("script errors are counted", err.get("message") == "x is not defined" and err.get("n") == 1, rep["errors"])
check("and say which piece of the script they came from", "09-staff.js:" in (err.get("place") or ""), err.get("place"))

# too many beacons from one visitor are dropped
for _ in range(80):
    beacon({"view": "stats", "kind": "pilot"}, ip="198.51.100.99")
check("one visitor can't flood the counts", {p["view"]: p for p in usage.report(7)["pages"]}["stats"]["opens"] <= usage.MAX_PER_MINUTE)

# who can read it
check("guests can't read the counts", client.get("/api/staff/usage").status_code == 401)
with A.db() as c:
    c.execute("INSERT OR IGNORE INTO pilots (id, name) VALUES ('PAC0001', 'Joseph Pagani')")
    c.execute("UPDATE pilots SET password_hash='x', status='Active', staff=1 WHERE id='PAC0001'")
    c.execute("INSERT OR IGNORE INTO pilots (id, name) VALUES ('PAC0042', 'Line Pilot')")
    c.execute("UPDATE pilots SET password_hash='x', status='Active', staff=0 WHERE id='PAC0042'")
with client.session_transaction() as s:
    s["pid"] = "PAC0042"
check("pilots can't read the counts", client.get("/api/staff/usage").status_code == 403)
with client.session_transaction() as s:
    s["pid"] = "PAC0001"
r = client.get("/api/staff/usage?days=30")
check("staff can", r.status_code == 200 and r.json["days"] == 30 and r.json["totals"]["opens"] >= 6, r.status_code)
check("a silly period is clamped", client.get("/api/staff/usage?days=99999").json["days"] == usage.KEEP_DAYS)

js = app_bundle.plain_source()
check("every page change is counted", "usageView(view);" in js and "function usageView(" in js)
check("staff have a Usage tab", '["usage", "Usage", 0]' in js and "usage: staffUsage" in js)
check("the privacy policy says so", "Anonymous page counts" in js)

print("\nUSAGE TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
