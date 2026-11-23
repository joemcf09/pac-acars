"""The site script is kept in pieces (static/app/*.js) but served as one /static/app.js: every piece, in order, unchanged,
so the page behaves exactly as when it was a single file. Run from the PAC folder: python tests/test_app_bundle.py"""
import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-bundle-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, app_bundle  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

pieces = app_bundle.pieces()
check("the script is in numbered pieces", len(pieces) >= 10 and all(re.match(r"\d\d[a-z]?-[a-z0-9-]+\.js$", p.name) for p in pieces), [p.name for p in pieces])
check("there is no separate static/app.js file to drift out of date", not (ROOT / "static" / "app.js").exists())
client = A.app.test_client()
r = client.get("/static/app.js?v=test")
body = r.get_data(as_text=True)
check("browsers get one app.js", r.status_code == 200 and r.mimetype == "text/javascript", (r.status_code, r.mimetype))
stripped = re.sub(r"/\* ==== static/app/[^ ]+ ==== \*/\n", "", body)
check("it is every piece, in order, unchanged", stripped == app_bundle.plain_source())
check("each piece is marked, so a console error can be traced to its piece", all(f"static/app/{p.name}" in body for p in pieces))
check("it still revalidates on every page load", r.headers.get("Cache-Control") == "no-cache", r.headers.get("Cache-Control"))
again = client.get("/static/app.js?v=test", headers={"If-None-Match": r.headers.get("ETag", "").strip('"')})
check("an unchanged script answers 304, so reloads stay quick", again.status_code == 304, again.status_code)
check("the home page loads it", '/static/app.js?v=' in (ROOT / "static" / "index.html").read_text(encoding="utf-8"))
for name in ("show", "api", "renderMissions", "renderDossier", "renderAcars", "loadLogbook", "renderHome", "renderStaff",
             "renderFleet", "applyAuth", "homeLayout", "staffRelief"):
    check(f"{name}() is still in the script", re.search(rf"\bfunction {name}\(", body) is not None)
node = shutil.which("node")
if node:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(body)
    p = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
    os.unlink(f.name)
    check("the joined script is valid JavaScript", p.returncode == 0, p.stderr[-400:])
    for piece in pieces:   # each piece ends between two statements, so it parses on its own too
        p = subprocess.run([node, "--check", str(piece)], capture_output=True, text=True)
        check(f"{piece.name} parses on its own", p.returncode == 0, p.stderr[-300:])

print("\nAPP BUNDLE TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
