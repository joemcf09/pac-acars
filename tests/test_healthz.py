"""/healthz for an outside monitor: 200 OK when everything is healthy, 503 naming the problem, no data leaked."""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-hz-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, botlink  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Hz-Test-1"}); c.post("/api/auth/logout")
r = c.get("/healthz")
check("anyone (the monitor) can reach it without signing in", r.status_code in (200, 503), r.status_code)
check("a fresh site with no worker report or backup says what's wrong", r.status_code == 503 and "mission worker" in r.text and "backups" in r.text, r.text)
now = time.time()
(Path(A.DATA) / "mission-worker-status.json").write_text(json.dumps({"state": "success", "last_success_at": now, "duration_seconds": 2}))
b = Path(A.BACKUP_DIR) / "20261110-test"; b.mkdir(parents=True, exist_ok=True)
(b / "logbook.db").write_bytes(b"x" * 10); (b / "backup-complete.json").write_text(json.dumps({"completed_at": now}))
with A.db() as con:
    con.execute("INSERT OR REPLACE INTO urgent (id, data, created, expires, status) VALUES ('PAC8899','{}',?,?,'open')", (now, now + 3600))
botlink._seen["poll"] = now
r = c.get("/healthz")
check("everything healthy: 200 OK", r.status_code == 200 and r.text == "OK", (r.status_code, r.text))
botlink._seen["poll"] = now - 600
r = c.get("/healthz")
bot_on = botlink.enabled()
check("bot silent for 10 minutes: 503 names it (when the bot is on)", (r.status_code == 503 and "discord bot" in r.text) if bot_on else r.status_code == 200, (bot_on, r.text))
check("only names the problem, no data", len(r.text) < 80)
# /up is the shallow member-facing check: it ignores the subsystems /healthz watches
botlink._seen["poll"] = now - 600          # bot still 'silent', which makes /healthz 503...
check("/healthz is 503 while the bot is silent (when bot on)", (c.get("/healthz").status_code == 503) if bot_on else True)
r = c.get("/up")
check("/up stays 200 when only a subsystem (bot/backups) is unhealthy", r.status_code == 200 and r.text == "OK", (r.status_code, r.text))
check("/up needs no sign-in", "set-cookie" not in {k.lower() for k in r.headers.keys()} or r.status_code == 200)
print("\nHEALTHZ TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
