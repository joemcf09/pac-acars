"""Wrong-password limits apply per visitor, not per Cloudflare server: the visitor's own address comes from
CF-Connecting-IP, but only on requests that really came through Cloudflare.
Run from the PAC folder: python tests/test_client_ip.py"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-clientip-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, client_ip  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

CF, CF6, DIRECT = "162.158.10.20", "2606:4700:10::6816:1", "203.0.113.50"
def ip_for(remote, header=None):
    with A.app.test_request_context("/", environ_base={"REMOTE_ADDR": remote}, headers={"CF-Connecting-IP": header} if header else {}):
        return client_ip.client_ip()

check("through Cloudflare, the visitor's own address is used", ip_for(CF, "198.51.100.7") == "198.51.100.7")
check("also over IPv6", ip_for(CF6, "2001:db8::5") == "2001:db8::5")
check("a request straight to the server can't pick its address", ip_for(DIRECT, "198.51.100.7") == DIRECT)
check("a garbled header is ignored", ip_for(CF, "not-an-ip") == CF)
check("no header: the connecting address", ip_for(CF) == CF)

with A.db() as con:
    con.execute("INSERT OR IGNORE INTO pilots (id, name) VALUES ('PAC0009', 'Test Pilot')")
    con.execute("UPDATE pilots SET password_hash=?, status='Active' WHERE id='PAC0009'", (generate_password_hash("right-password"),))
client = A.app.test_client()
def login(visitor, password="wrong"):
    return client.post("/api/auth/login", json={"pilot_id": "PAC0009", "password": password},
                       headers={"CF-Connecting-IP": visitor}, environ_base={"REMOTE_ADDR": CF})

codes = [login("198.51.100.66").status_code for _ in range(11)]
check("ten wrong passwords lock that visitor out", codes[:10] == [401] * 10 and codes[10] == 429, codes)
check("another pilot on the same Cloudflare server can still sign in", login("198.51.100.77", "right-password").status_code == 200)
r = client.post("/api/auth/login", json={"pilot_id": "PAC0009", "password": "wrong"},
                headers={"CF-Connecting-IP": "198.51.100.88"}, environ_base={"REMOTE_ADDR": DIRECT})
check("a direct request that claims a fresh address still counts against its own", r.status_code == 401)

print("\nCLIENT IP TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
