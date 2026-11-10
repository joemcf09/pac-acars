"""An airframe left 'Booked' with no booking holding it goes back to Available; one on an open booking stays Booked.
Run from the PAC folder: python tests/test_booked_heal.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-heal-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, va  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
A.app.test_client().post("/api/auth/setup", json={"password": "Heal-Test-1"})
old = time.time() - 3600
with A.db() as con:
    regs = [r["reg"] for r in con.execute("SELECT reg FROM airframes ORDER BY reg LIMIT 3")]
    con.execute("UPDATE airframes SET status='Booked', updated=? WHERE reg IN (?,?)", (old, regs[0], regs[1]))
    con.execute("UPDATE airframes SET status='Booked', updated=? WHERE reg=?", (time.time(), regs[2]))
    con.execute("INSERT OR REPLACE INTO bookings (pilot_id, data, requested_at) VALUES ('PAC0002', ?, ?)", (json.dumps({"airframe": regs[1]}), old))
st = {a["reg"]: a["status"] for a in va.airframes()}
check("booked with no booking: released", st[regs[0]] == "Available", st[regs[0]])
check("on an open booking: stays booked", st[regs[1]] == "Booked", st[regs[1]])
check("just booked (under ten minutes): left alone", st[regs[2]] == "Booked", st[regs[2]])
print("\nBOOKED HEAL TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
