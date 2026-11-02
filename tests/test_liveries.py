"""Liveries on the Fleet page: staff add them as a file or a link, painters get the credit, pilots download them.

Run from the PAC folder:   python tests/test_liveries.py
"""
import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "liveries.json"):
    (DATA / _f).unlink(missing_ok=True)
shutil.rmtree(DATA / "liveries", ignore_errors=True)

import app as A  # noqa: E402
import botlink  # noqa: E402
import discord_bot as DB  # noqa: E402
import liveries as L  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


ZIP = b"PK\x03\x04" + b"\0" * 2048
SEVENZ = b"7z\xbc\xaf\x27\x1c" + b"\0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64

staff = A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Livery-Test-Pass-1"})
guest = A.app.test_client()


def add(fields, files=None):
    data = {**fields, **(files or {})}
    r = staff.post("/api/staff/liveries", data=data, content_type="multipart/form-data")
    return r.status_code, r.get_json() or {}


print("Adding liveries")
code, j = add({"type": "MD11F", "title": "PAC house colours", "painter": "Ana Ruiz", "painter_link": "https://flightsim.to/profile/ana",
               "sim": "MSFS", "model": "TFDi MD-11", "version": "1.2", "registration": "n110pc", "notes": "Unzip into Community."},
              {"file": (io.BytesIO(ZIP), "PAC MD-11F (final) v1.2.zip"), "preview": (io.BytesIO(PNG), "nose.png", "image/png")})
check("a file livery is added", code == 200 and j.get("ok"), j)
md = j.get("livery", {})
check("the file name is cleaned up", (L.find(md.get("id")) or {}).get("file") == "PAC-MD-11F-final-v1.2.zip", L.find(md.get("id")))
check("the registration is upper-cased", md.get("registration") == "N110PC", md)
check("it has a preview", bool(md.get("preview")), md)
check("no half-upload is left behind", not list((DATA / "liveries").rglob("*.part")))

code, j = add({"type": "B77F", "painter": "Sam Lee", "url": "https://flightsim.to/file/12345/pac-777f"})
check("a link livery is added", code == 200, j)
link = j.get("livery", {})
check("a link livery gets the default name", link.get("title") == "PAC house colours", link)
check("and the type's add-on aircraft as its model", link.get("model") == A.FLEET["B77F"].get("sim_model", ""), link)
check("its host is shown", link.get("host") == "flightsim.to", link)

print("Refusing what doesn't fit")
for why, fields, files in [
    ("no painter", {"type": "MD11F", "url": "https://flightsim.to/x"}, None),
    ("unknown aircraft type", {"type": "A380F", "painter": "X", "url": "https://flightsim.to/x"}, None),
    ("neither file nor link", {"type": "MD11F", "painter": "X"}, None),
    ("a plain http link", {"type": "MD11F", "painter": "X", "url": "http://example.com/livery"}, None),
    ("a file that isn't an archive", {"type": "MD11F", "painter": "X"}, {"file": (io.BytesIO(b"hello"), "livery.zip")}),
    ("a .7z that is really a zip", {"type": "MD11F", "painter": "X"}, {"file": (io.BytesIO(ZIP), "livery.7z")}),
    ("an image as the livery", {"type": "MD11F", "painter": "X"}, {"file": (io.BytesIO(PNG), "livery.png")}),
]:
    code, j = add(fields, files)
    check(f"refuses {why}, with a reason", code == 400 and j.get("error"), (code, j))
check("refused uploads leave nothing behind", len(L.load()) == 2 and len(list((DATA / "liveries").iterdir())) == 1,
      [p.name for p in (DATA / "liveries").iterdir()])
code, j = add({"type": "B748F", "painter": "Kim", "sim": "X-Plane"}, {"file": (io.BytesIO(SEVENZ), "pac-748.7z")})
check("a real .7z is accepted", code == 200, j)
seven = j.get("livery", {})

print("What visitors and pilots see")
pub = guest.get("/api/fleet").get_json()
check("the Fleet page lists liveries for visitors", len(pub.get("liveries", [])) == 3, pub.get("liveries"))
check("visitors are asked to sign in for files", next(x for x in pub["liveries"] if x["id"] == md["id"]).get("needs_signin") is True)
check("the stored file name isn't shown", all("file" not in x for x in pub["liveries"]))
check("previews are public", guest.get(md["preview"]).status_code == 200)
r = guest.get(f"/api/fleet/liveries/{md['id']}/download")
check("visitors can't download files", r.status_code == 401 and r.get_json().get("signin"), r.status_code)
r = guest.get(f"/api/fleet/liveries/{link['id']}/download")
check("visitors can follow a link to the painter's page", r.status_code == 302 and r.headers["Location"].startswith("https://flightsim.to/"), r.status_code)
r = staff.get(f"/api/fleet/liveries/{md['id']}/download")
check("signed-in pilots download the file", r.status_code == 200 and r.data == ZIP, r.status_code)
check("as an attachment", "attachment" in r.headers.get("Content-Disposition", ""), r.headers.get("Content-Disposition"))
counts = {x["id"]: x["downloads"] for x in staff.get("/api/fleet/liveries").get_json()["liveries"]}
check("downloads are counted", counts.get(md["id"]) == 1 and counts.get(link["id"]) == 1, counts)
check("guests can't add liveries", guest.post("/api/staff/liveries", data={"type": "MD11F", "painter": "X", "url": "https://a.b/c"}).status_code == 401)

print("Editing and removing")
r = staff.post(f"/api/staff/liveries/{md['id']}", json={"version": "1.3", "notes": "Now with night lighting."})
e = r.get_json() or {}
check("text edits keep the file", r.status_code == 200 and e["livery"]["version"] == "1.3" and e["livery"]["kind"] == "file", e)
r = staff.post(f"/api/staff/liveries/{md['id']}", json={"painter": ""})
check("the painter can't be blanked", r.status_code == 400)
r = staff.post(f"/api/staff/liveries/{md['id']}", json={"url": "https://flightsim.to/file/999/pac-md11"})
e = r.get_json() or {}
check("a file livery can become a link", r.status_code == 200 and e["livery"]["kind"] == "link", e)
check("and its old file is deleted", not [p for p in (DATA / "liveries" / md["id"]).glob("*.zip")])
r = staff.post(f"/api/staff/liveries/{md['id']}", data={"file": (io.BytesIO(ZIP), "md11.zip")}, content_type="multipart/form-data")
e = r.get_json() or {}
check("and back to a file", r.status_code == 200 and e["livery"]["kind"] == "file" and not e["livery"]["url"], e)
r = staff.post(f"/api/staff/liveries/{md['id']}", json={"remove_preview": "1"})
check("the preview can be removed", r.status_code == 200 and not r.get_json()["livery"]["preview"])
r = staff.delete(f"/api/staff/liveries/{seven['id']}")
check("a livery can be removed", r.status_code == 200 and len(r.get_json()["liveries"]) == 2)
check("its folder goes with it", not (DATA / "liveries" / seven["id"]).exists())
check("removing it again says so", staff.delete(f"/api/staff/liveries/{seven['id']}").status_code == 404)

print("Backups and Discord")
check("the full backup includes liveries", "liveries.json" in A.USER_FILES and "liveries" in A.USER_DIRS)
st = A.settings()
st.update(discord_bot_enabled=True, discord_bot_token="test-token")
A.save_json(A.SETTINGS_PATH, st)
add({"type": "B738F", "painter": "Ana Ruiz", "painter_link": "https://flightsim.to/profile/ana", "registration": "N010PC",
     "url": "https://flightsim.to/file/1/pac-738"})
with A.db() as con:
    ev = con.execute("SELECT data FROM bot_events WHERE kind='livery' ORDER BY id DESC LIMIT 1").fetchone()
check("a new livery is announced to the Discord bot", ev is not None)
if ev:
    text = DB.livery_text(json.loads(ev[0]), "https://pac-va.com")
    check("the post credits the painter with their link", "[Ana Ruiz](<https://flightsim.to/profile/ana>)" in text, text)
    check("and points to the Fleet page", "https://pac-va.com/#fleet" in text, text)
    print("   " + text.replace("\n", "\n   "))

for _f in ("liveries.json",):
    (DATA / _f).unlink(missing_ok=True)
shutil.rmtree(DATA / "liveries", ignore_errors=True)
print("\nLIVERIES TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
