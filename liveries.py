"""Liveries on the Fleet page: PAC paint schemes for each aircraft type, with credit to the painter.

A livery is either a file staff upload (a zip, 7z or rar, offered to signed-in pilots) or a link to where the painter
hosts it (flightsim.to, X-Plane.org and the like, open to everyone). Each can have a preview picture; without one the
Fleet page shows the type's photo. Everything lives in data/liveries.json and data/liveries/<id>/, so updates to PAC
never touch it and the full backup includes it.
"""
import os
import re
import secrets
import shutil
import time
from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, send_from_directory

bp = Blueprint("liveries", __name__)
C = {}

SIMS = ("MSFS", "X-Plane")
ARCHIVES = {".zip": (b"PK\x03\x04",), ".7z": (b"7z\xbc\xaf\x27\x1c",), ".rar": (b"Rar!\x1a\x07",)}
PREVIEWS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
PREVIEW_MAX = 15 * 1024 * 1024
TEXT_FIELDS = {"title": 80, "painter": 60, "model": 80, "version": 20, "registration": 12, "notes": 500}


def init(ctx):
    C.update(ctx)


def max_file_bytes():
    return int(os.environ.get("PAC_LIVERY_MAX_MB", "600")) * 1024 * 1024


def _store():
    return C["DATA"] / "liveries.json"


def _dir(lid=None):
    d = C["DATA"] / "liveries"
    return d / lid if lid else d


def load():
    data = C["load_json"](_store(), [])
    return data if isinstance(data, list) else []


def save(items):
    C["save_json"](_store(), items)


def find(lid):
    return next((x for x in load() if x.get("id") == lid), None)


def _clean_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    if not re.fullmatch(r"https://[^\s<>\"']{4,500}", u):
        raise ValueError("Links must start with https:// (for example a flightsim.to page).")
    return u


def _host(u):
    m = re.match(r"https://(?:www\.)?([^/:]+)", u or "")
    return m.group(1) if m else ""


def public(x, signed_in=False):
    """What the Fleet page sees. The stored file name stays private; downloads go through our own address."""
    out = {k: x.get(k, "") for k in ("id", "type", "title", "painter", "painter_link", "sim", "model", "version", "registration", "notes")}
    out.update(added=x.get("added"), updated=x.get("updated"), downloads=x.get("downloads", 0),
               kind="file" if x.get("file") else "link",
               size=x.get("size") if x.get("file") else None,
               host=_host(x.get("url")) if x.get("url") else "",
               url=x.get("url", "") if not x.get("file") else "",
               preview=f"/api/fleet/liveries/{x['id']}/preview?v={int(x.get('preview_at') or 0)}" if x.get("preview") else None,
               download=f"/api/fleet/liveries/{x['id']}/download")
    if x.get("file"):
        out["needs_signin"] = not signed_in
    return out


def listing(signed_in=False):
    items = sorted(load(), key=lambda x: (x.get("type", ""), -(x.get("added") or 0)))
    return [public(x, signed_in) for x in items if x.get("type") in C["FLEET"]]


def _fields(form, current=None):
    """Checks the text fields of a new or edited livery. Returns the cleaned values."""
    cur = current or {}
    out = {}
    for k, n in TEXT_FIELDS.items():
        if k in form:
            out[k] = C["clean_text"](form.get(k), n)
    if "type" in form or not current:
        t = (form.get("type") or "").strip().upper()
        if t not in C["FLEET"]:
            raise ValueError("Choose which aircraft type the livery is for.")
        out["type"] = t
    if "sim" in form or not current:
        s = (form.get("sim") or "").strip()
        if s not in SIMS:
            fleet_sim = C["FLEET"].get(out.get("type") or cur.get("type"), {}).get("sim", "MSFS")
            s = "X-Plane" if fleet_sim == "X-Plane" else "MSFS"
        out["sim"] = s
    if "painter_link" in form:
        out["painter_link"] = _clean_url(form.get("painter_link"))
    if "url" in form:
        out["url"] = _clean_url(form.get("url"))
    if "registration" in out:
        out["registration"] = out["registration"].upper()
    merged = {**cur, **out}
    if not merged.get("painter"):
        raise ValueError("Add the painter's name: credit is the point of this page.")
    if not merged.get("title"):
        out["title"] = "PAC house colours"
    if not merged.get("model"):
        out["model"] = C["FLEET"].get(merged["type"], {}).get("sim_model", "") or ""
    return out


def _archive_name(filename, head):
    """('PAC-MD11F-house-colours.zip', None) or (None, why)."""
    base = Path(filename or "").name
    ext = Path(base).suffix.lower()
    if ext not in ARCHIVES:
        return None, "Upload the livery as a .zip, .7z or .rar file."
    if not any(head.startswith(sig) for sig in ARCHIVES[ext]):
        return None, f"That file isn't a valid {ext} archive. Try zipping the livery folder again."
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(base).stem).strip("-._")[:80] or "livery"
    return stem + ext, None


def _save_file(lid, f):
    """Saves an uploaded archive. Returns (name, size) or raises ValueError."""
    head = f.stream.read(8)
    f.stream.seek(0)
    name, why = _archive_name(f.filename, head)
    if not name:
        raise ValueError(why)
    d = _dir(lid)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (name + ".part")          # never offer a half-uploaded file
    f.save(tmp)
    size = tmp.stat().st_size
    if size > max_file_bytes():
        tmp.unlink(missing_ok=True)
        raise ValueError(f"That file is over {max_file_bytes() // (1024 * 1024)} MB. Host it on flightsim.to or similar and add the link instead.")
    for old in d.glob("*"):
        if old.suffix.lower() in ARCHIVES and old.name != name:
            old.unlink()
    tmp.replace(d / name)
    return name, size


def _save_preview(lid, f):
    if f.mimetype not in PREVIEWS:
        raise ValueError("The preview must be a PNG, JPEG or WebP picture.")
    data = f.read()
    if len(data) > PREVIEW_MAX:
        raise ValueError("The preview picture is over 15 MB. Choose a smaller one.")
    d = _dir(lid)
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("preview.*"):
        old.unlink()
    name = "preview" + PREVIEWS[f.mimetype]
    (d / name).write_bytes(data)
    return name


def _form():
    return request.form if request.files or request.form else (request.get_json(silent=True) or {})


# ---------------------------------------------------------------- everyone
@bp.get("/api/fleet/liveries")
def liveries_list():
    import auth
    import va
    return jsonify({"liveries": listing(bool(auth.current())), "discord_invite": (va.site().get("discord_invite") or "").strip(),
                    "max_mb": max_file_bytes() // (1024 * 1024)})


@bp.get("/api/fleet/liveries/<lid>/preview")
def livery_preview(lid):
    x = find(lid)
    if not x or not x.get("preview") or not (_dir(lid) / x["preview"]).exists():
        return jsonify({"error": "No preview."}), 404
    return send_from_directory(_dir(lid), x["preview"], max_age=86400)


@bp.get("/api/fleet/liveries/<lid>/download")
def livery_download(lid):
    """A link goes straight to the painter's page; a file is for signed-in PAC pilots."""
    import auth
    items = load()
    x = next((i for i in items if i.get("id") == lid), None)
    if not x:
        return jsonify({"error": "That livery has been removed."}), 404
    if x.get("file"):
        if not auth.current():
            return jsonify({"error": "Sign in to download PAC liveries.", "signin": True}), 401
        if not (_dir(lid) / x["file"]).exists():
            return jsonify({"error": "The livery file is missing on the server. Ask staff to upload it again."}), 404
    x["downloads"] = x.get("downloads", 0) + 1
    save(items)
    if x.get("file"):
        return send_from_directory(_dir(lid), x["file"], as_attachment=True)
    return redirect(x["url"], code=302)


# ---------------------------------------------------------------- staff
@bp.post("/api/staff/liveries")
def livery_add():
    form = _form()
    try:
        fields = _fields(form)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    upload = request.files.get("file")
    if not (upload and upload.filename) and not fields.get("url"):
        return jsonify({"error": "Upload the livery file or add a link to where it's hosted."}), 400
    lid = secrets.token_hex(5)
    x = {"id": lid, "painter_link": "", "url": "", "version": "", "registration": "", "notes": "", **fields,
         "added": time.time(), "updated": time.time(), "downloads": 0, "file": "", "size": 0, "preview": ""}
    try:
        if upload and upload.filename:
            x["file"], x["size"] = _save_file(lid, upload)
            x["url"] = ""
        pv = request.files.get("preview")
        if pv and pv.filename:
            x["preview"], x["preview_at"] = _save_preview(lid, pv), time.time()
    except ValueError as e:
        shutil.rmtree(_dir(lid), ignore_errors=True)
        return jsonify({"error": str(e)}), 400
    items = load()
    items.append(x)
    save(items)
    announce(x)
    return jsonify({"ok": True, "livery": public(x, True), "liveries": listing(True)})


@bp.post("/api/staff/liveries/<lid>")
def livery_edit(lid):
    items = load()
    x = next((i for i in items if i.get("id") == lid), None)
    if not x:
        return jsonify({"error": "That livery has been removed."}), 404
    form = _form()
    try:
        edits = _fields(form, x)
        upload, pv = request.files.get("file"), request.files.get("preview")
        if upload and upload.filename:
            edits["file"], edits["size"] = _save_file(lid, upload)
            edits["url"] = ""
        elif edits.get("url"):                  # switched from a file to a link
            for old in _dir(lid).glob("*") if _dir(lid).exists() else []:
                if old.suffix.lower() in ARCHIVES:
                    old.unlink()
            edits.update(file="", size=0)
        elif "url" in edits and not x.get("file"):
            return jsonify({"error": "Upload the livery file or add a link to where it's hosted."}), 400
        if pv and pv.filename:
            edits["preview"], edits["preview_at"] = _save_preview(lid, pv), time.time()
        elif str(form.get("remove_preview") or "") in ("1", "true"):
            for old in _dir(lid).glob("preview.*") if _dir(lid).exists() else []:
                old.unlink()
            edits["preview"] = ""
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    x.update(edits, updated=time.time())
    save(items)
    return jsonify({"ok": True, "livery": public(x, True), "liveries": listing(True)})


@bp.delete("/api/staff/liveries/<lid>")
def livery_delete(lid):
    items = load()
    if not any(i.get("id") == lid for i in items):
        return jsonify({"error": "That livery has been removed."}), 404
    save([i for i in items if i.get("id") != lid])
    shutil.rmtree(_dir(lid), ignore_errors=True)
    return jsonify({"ok": True, "liveries": listing(True)})


def announce(x):
    """Tells the Discord bot, which posts new liveries in the news channel."""
    try:
        import botlink
        a = C["FLEET"].get(x["type"], {})
        botlink.emit("livery", {"aircraft": a.get("name", x["type"]), "type": x["type"], "title": x.get("title", ""),
                                "painter": x.get("painter", ""), "painter_link": x.get("painter_link", ""), "sim": x.get("sim", ""),
                                "model": x.get("model", ""), "registration": x.get("registration", ""), "id": x["id"]})
    except Exception as e:
        print(f"Livery announcement not sent: {e}")
