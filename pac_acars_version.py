"""PAC ACARS: sets the version in the Windows build files and checks the build includes the new files.
Run on the Windows PC you build PAC ACARS on, from the PAC folder:   python pac_acars_version.py
Then build as usual with acars_client\\build\\build_acars.bat. Safe to run twice."""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
V, VT = "1.1.1", "1, 1, 1, 0"
BUILD = os.path.join(ROOT, "acars_client", "build")
done, warn = 0, []
for rel, pats in {"version_info.txt": [(r"(Version', ')[0-9.]+'", rf"\g<1>{V}'"), (r"(vers=\()[0-9, ]+(\))", rf"\g<1>{VT}\2")],
                  "installer.iss": [(r'(#define AppVersion ")[0-9.]+"', rf'\g<1>{V}"')],
                  "build_acars.bat": [(r'(set "VERSION=)[0-9.]+"', rf'\g<1>{V}"')]}.items():
    p = os.path.join(BUILD, rel)
    if not os.path.exists(p):
        warn.append(f"{rel} not found in acars_client\\build (run this on the PC you build PAC ACARS on)")
        continue
    s = open(p, encoding="utf-8", newline="").read()
    o = s
    for a, b in pats:
        s = re.sub(a, b, s)
    if s != o:
        open(p, "w", encoding="utf-8", newline="").write(s)
        done += 1
# The build recipe must ship the whole assets folder: 1.1 adds assets\leaflet (the moving map) and assets\runways.json
# (the landing debrief). A recipe that names the asset files one by one would leave them out.
specs = [f for f in os.listdir(BUILD) if f.endswith(".spec")] if os.path.isdir(BUILD) else []
for f in specs:
    s = open(os.path.join(BUILD, f), encoding="utf-8", errors="replace").read()
    if "big-shoulders-stencil" in s or "BigShouldersStencil" in s:
        warn.append(f"{f} names the old stencil font file, which 1.1 removed. Send this file to Claude to fix.")
    if "assets" not in s:
        warn.append(f"{f} doesn't mention the assets folder. Send this file to Claude to check before building.")
    elif re.search(r"assets[\\/]+(fonts|pac-)", s) and "leaflet" not in s:
        warn.append(f"{f} lists asset files one by one, so the new map and runway files would be missing. Send it to Claude.")
print(f"PAC ACARS {V}: {done} build file(s) updated.")
for w in warn:
    print("  CHECK:", w)
if not warn:
    print("Build files look right. Now run acars_client\\build\\build_acars.bat")
