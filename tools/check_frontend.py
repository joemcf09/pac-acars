"""Syntax-checks the JavaScript inside the web pages with Node (if installed).
Usage: python tools/check_frontend.py"""
import re, shutil, subprocess, sys, tempfile
from pathlib import Path

node = shutil.which("node")
if not node:
    print("Node.js not found; skipping the front-end syntax check.")
    sys.exit(0)
bad = 0
for page in ("index.html", "dispatch.html", "../acars_client/ui.html"):
    html = (Path(__file__).resolve().parent.parent / "static" / page).read_text(encoding="utf-8")
    for i, js in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(js)
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        if r.returncode:
            bad += 1
            print(f"{page} script {i + 1}: SYNTAX ERROR\n{r.stderr.strip()[:800]}")
for js in sorted((Path(__file__).resolve().parent.parent / "static").glob("*.js")):
    r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
    if r.returncode:
        bad += 1
        print(f"{js.name}: SYNTAX ERROR\n{r.stderr.strip()[:800]}")
print("FRONT-END CHECK", "FAILED" if bad else "PASSED")
sys.exit(1 if bad else 0)
