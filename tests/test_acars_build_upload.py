"""Uploading a PAC ACARS build on the Downloads page: renamed copies are accepted, wrong files are refused clearly."""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


EXE, ZIP = b"MZ" + b"\0" * 64, b"PK\x03\x04" + b"\0" * 64

for given, head, want in [
    ("PAC-ACARS-Setup-1.0.0.exe", EXE, "PAC-ACARS-Setup-1.0.0.exe"),
    ("PAC-ACARS-1.0.0-portable.zip", ZIP, "PAC-ACARS-1.0.0-portable.zip"),
    ("PAC-ACARS-Setup-1.0.0 (1).exe", EXE, "PAC-ACARS-Setup-1.0.0.exe"),
    ("PAC-ACARS-1.0.0-portable (2).zip", ZIP, "PAC-ACARS-1.0.0-portable.zip"),
    ("pac-acars-1.0.0-portable - Copy.zip", ZIP, "PAC-ACARS-1.0.0-portable.zip"),
    ("PAC ACARS Setup 1.2.3.exe", EXE, "PAC-ACARS-Setup-1.2.3.exe"),
]:
    name, why = A.acars_build_name(given, head)
    check(f"accepts {given!r}", name == want, f"{name} / {why}")

for given, head in [("PAC ACARS.exe", EXE), ("setup.exe", EXE), ("PAC-ACARS-Setup-1.0.0.exe", ZIP),
                    ("PAC-ACARS-1.0.0-portable.zip", b"hello"), ("PAC-ACARS-1.0.0-portable.rar", ZIP)]:
    name, why = A.acars_build_name(given, head)
    check(f"refuses {given!r} with a reason", name is None and why, f"{name}")
check("the dist exe gets its own explanation", "dist folder" in A.acars_build_name("PAC ACARS.exe", EXE)[1])

c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Build-Upload-Test-1"})
for f in A.ACARS_BUILD_DIR.glob("PAC-ACARS-*"):
    f.unlink()
r = c.post("/api/staff/acars/build", data={"file": (io.BytesIO(ZIP), "PAC-ACARS-1.0.0-portable (1).zip")},
           content_type="multipart/form-data")
check("upload of a renamed portable zip succeeds", r.status_code == 200, r.get_data(as_text=True))
j = r.get_json() or {}
check("saved under its proper name", j.get("file") == "PAC-ACARS-1.0.0-portable.zip", j)
check("Downloads page offers it", (j.get("acars") or {}).get("portable", {}).get("file") == "PAC-ACARS-1.0.0-portable.zip", j)
check("no half-upload left behind", not list(A.ACARS_BUILD_DIR.glob("*.part")))
d = c.get("/api/acars/build/PAC-ACARS-1.0.0-portable.zip")
check("pilots can download it", d.status_code == 200 and d.data == ZIP, d.status_code)
r = c.post("/api/staff/acars/build", data={"file": (io.BytesIO(EXE), "PAC ACARS.exe")}, content_type="multipart/form-data")
check("the dist exe is refused", r.status_code == 400 and "dist folder" in r.get_json()["error"])
c.delete("/api/staff/acars/build/PAC-ACARS-1.0.0-portable.zip")
check("removal works", A.acars_downloads() is None)

print("\n" + ("All build-upload checks passed." if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
