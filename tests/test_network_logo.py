"""The VATSIM logo in the home page's Network partners section: staff upload the official file, visitors see it
unaltered, and nothing unsafe gets through. (Uses a stand-in image; the real file comes from vats.im/logo.)

Run from the PAC folder:   python tests/test_network_logo.py
"""
import io
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)
shutil.rmtree(DATA / "network_logos", ignore_errors=True)

import app as A  # noqa: E402
from PIL import Image  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


buf = io.BytesIO()
Image.new("RGBA", (400, 120), (40, 90, 200, 255)).save(buf, "PNG")
PNG = buf.getvalue()
staff, guest = A.app.test_client(), A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Network-Logo-Test-1"})


def up(data, name, mime):
    return staff.post("/api/staff/network-logo", data={"file": (io.BytesIO(data), name, mime)}, content_type="multipart/form-data")


home = guest.get("/api/va/home").get_json()["network_logos"]
check("the official logo is built in", home["vatsim"] == "/static/partners/vatsim-logo.svg" and not home["vatsim_uploaded"], home)
check("but the section stays hidden until staff switch it on (PAC isn't a VATSIM partner yet)", home["show"] is False, home)
check("staff can switch it on", staff.post("/api/settings", json={"vatsim_partner_section": True}).status_code == 200
      and guest.get("/api/va/home").get_json()["network_logos"]["show"] is True)
check("visitors can't", guest.post("/api/settings", json={"vatsim_partner_section": False}).status_code in (401, 403))
staff.post("/api/settings", json={"vatsim_partner_section": False})
check("and off again", guest.get("/api/va/home").get_json()["network_logos"]["show"] is False)
built = guest.get(home["vatsim"])
check("and served as an image", built.status_code == 200 and b"<svg" in built.data[:400], built.status_code)
check("it's VATSIM's file, unaltered (no scripts, no outside links)",
      not any(x in built.data.lower() for x in (b"<script", b"javascript:", b"onload=", b"href=\"http")))
check("visitors can't upload one", guest.post("/api/staff/network-logo", data={"file": (io.BytesIO(PNG), "v.png", "image/png")},
                                              content_type="multipart/form-data").status_code == 401)
r = up(PNG, "VATSIM_Logo_No_Tagline.png", "image/png")
check("staff upload the PNG", r.status_code == 200 and r.get_json()["logos"]["vatsim"], r.get_json())
url = guest.get("/api/va/home").get_json()["network_logos"]["vatsim"]
check("the home page offers it to visitors", bool(url), url)
img = guest.get(url)
check("visitors get the file exactly as uploaded", img.status_code == 200 and img.data == PNG, img.status_code)
check("served as an image only", img.headers.get("X-Content-Type-Options") == "nosniff")
check("a renamed text file is refused", up(b"hello", "logo.png", "image/png").status_code == 400)
check("a JPEG is refused (the pack has PNG and SVG)", up(PNG, "logo.jpg", "image/jpeg").status_code == 400)
check("an SVG with a script is refused", up(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "v.svg", "image/svg+xml").status_code == 400)
svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="#2483c5"/></svg>'
check("a clean SVG is accepted", up(svg, "VATSIM.svg", "image/svg+xml").status_code == 200)
s = guest.get(guest.get("/api/va/home").get_json()["network_logos"]["vatsim"])
check("and replaces the PNG", s.data == svg and not (DATA / "network_logos" / "vatsim.png").exists())
check("an SVG can't run anything", "sandbox" in s.headers.get("Content-Security-Policy", ""), s.headers.get("Content-Security-Policy"))
r = staff.delete("/api/staff/network-logo")
check("removing an upload goes back to the built-in logo", r.status_code == 200 and r.get_json()["logos"]["vatsim"] == "/static/partners/vatsim-logo.svg")
check("the full backup includes it", "network_logos" in A.USER_DIRS)

shutil.rmtree(DATA / "network_logos", ignore_errors=True)
print("\nNETWORK LOGO TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
