"""Dashboard start-here checklist and the reorganized menu: the dashboard reports how many flights a pilot has filed
(demo flights left out), and the Learn menu holds the Academy, handbook, cargo guide and downloads.
Run from the PAC folder: python tests/test_start_here.py"""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-start-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Start-Test-1"})
d = c.get("/api/pilot/dashboard").get_json() or {}
check("a new pilot has filed no flights", d.get("flights_filed") == 0, d.get("flights_filed"))
with A.db() as con:
    for demo in (0, 1):
        con.execute("INSERT INTO pireps (filed_at, flight_number, aircraft, dep, arr, block_min, distance_nm, payload_lbs, demo, pilot_id) VALUES (?,?,?,?,?,?,?,?,?, 'PAC0001')",
                    (time.time(), "PAC1", "B738F", "KCVG", "KIND", 40, 100, 20000, demo))
d = c.get("/api/pilot/dashboard").get_json() or {}
check("a real flight counts, a demo flight doesn't", d.get("flights_filed") == 1, d.get("flights_filed"))
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
check("the Learn menu is there with the Academy first", "Learn <span" in html and html.index("PAC Academy") < html.index('data-view="handbook"'))
js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
check("home and dashboard sections are wired in", all(x in js for x in ("${whyPacHTML()}", "${startHereHTML(d)}", "loadHappeningNow(now,d)")))

check("home page layout is wired in for visitors and pilots", all(x in js for x in ("homeLayout();", "function fmtLbShort", "fillJoinGroupFlight(d)", "hero-slim")))
print("\nSTART HERE TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
