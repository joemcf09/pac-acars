"""Pagani Aviation Group: the link between PAC and Pagani Remote Aviation (PRA).

* A private, read-only feed for the group hub: pilots, PAC hours and recent flights, and the PAC flights that
  landed at Anchorage carrying freight for PRA's village strips ("handoffs").
* The PRA division: staff tick it on a pilot in Staff › Roster.
* Village freight: PAC flights into Anchorage carry a few pieces bound onward to PRA strips. They're picked when
  the flight is booked, printed on the cargo manifest, and handed to PRA through the feed once the PIREP is accepted.

The feed is off until staff switch it on, and it needs the group key (Staff › Site and rules › Pagani Aviation
Group). Names are shown to whoever holds the key, nothing else private ever is: no email, Discord, network IDs,
wallet or settings.
"""
from __future__ import annotations

import datetime as dt
import hmac
import json
import random
import secrets
import time

from flask import Blueprint, jsonify, request

bp = Blueprint("group", __name__)
C = {}  # shared context from app.py: db, settings, save_settings, FLEET, career

GATEWAY = "PANC"                 # where PAC freight meets PRA
HANDOFF_DAYS = 14                # how far back the feed looks for handoffs
FEED_CACHE_S = 60
RECENT_N = 10
FEED_PATH = "/api/group/v1/summary"
METAR_PATH = "/api/group/v1/metar"
METAR_MAX = 20

# PRA's strips (ids match the PRA site's data.js)
PRA_STRIPS = {
    "TYE": "Tyonek", "PASW": "Skwentna", "PATK": "Talkeetna", "PALJ": "Port Alsworth", "PANO": "Nondalton", "PAIL": "Iliamna",
    "4K0": "Pedro Bay", "PFKK": "Kokhanok", "PAMC": "McGrath", "PAFS": "Nikolai", "PAKN": "King Salmon", "PADL": "Dillingham",
}
VILLAGES = ["TYE", "PASW", "PALJ", "PANO", "4K0", "PFKK", "PAFS"]          # no shops of note: schools, clinics, stores
HUBS = ["PAIL", "PAMC", "PADL", "PAKN", "PATK"]                             # towns with a power plant, boat yard, election board

# (description, lb range, pcs range, shipper, consignee pattern, why, SHC, where it can go)
VILLAGE_FREIGHT = [
    ("Clinic restock: wound care and IV supplies", (90, 180), (2, 4), "Medical distributor, Louisville", "{v} clinic",
     "Quarterly order, too bulky for bypass mail.", ["PIL"], VILLAGES),
    ("Vaccines, insulated shipper", (20, 45), (1, 1), "Pharmaceutical wholesaler, Memphis", "{v} clinic",
     "Must stay 2–8 °C. Hand to the health aide.", ["PIL", "COL"], VILLAGES),
    ("Water-plant control board", (25, 45), (1, 1), "Controls manufacturer, Ohio", "{v} water plant",
     "The plant is running on manual control until it arrives.", ["AOG"], VILLAGES),
    ("School science lab kits", (120, 240), (2, 5), "Education supplier, Cincinnati", "{v} school",
     "Next term's science units.", [], VILLAGES),
    ("Boiler circulator pump", (40, 70), (1, 1), "HVAC supplier, Chicago", "{v} school",
     "The school is running on one pump going into winter.", ["AOG"], VILLAGES),
    ("Store restock: dry goods", (200, 420), (4, 8), "Grocery wholesaler, Seattle", "{v} store",
     "The last barge has gone; anything else comes by air.", [], VILLAGES),
    ("Snowmachine track and parts", (90, 160), (1, 3), "Powersports dealer, Minneapolis", "{v} resident (store will call)",
     "Freeze-up is coming and this is how people travel all winter.", [], VILLAGES + ["PAFS"]),
    ("Generator alternator", (180, 260), (1, 1), "Engine parts distributor", "{v} power plant",
     "A spare for the winter so one failure doesn't put the town in the dark.", ["HEA"], HUBS),
    ("Marine diesel injectors", (40, 80), (1, 2), "Engine parts distributor", "{v} boat yard",
     "Gets a tender back in the water before freeze-up.", ["AOG"], ["PADL", "PAKN", "PAIL"]),
    ("Election equipment, sealed", (30, 50), (1, 1), "Division of Elections", "{v} election board",
     "Replacement tabulator. Chain of custody: hand to the named official only.", ["SEC"], ["PAMC", "PADL", "PAIL", "PAFS"]),
    ("Radio-collar telemetry kit", (35, 70), (1, 2), "Wildlife electronics maker, Minnesota", "Wildlife survey team, {v}",
     "For the caribou count before the snow.", [], ["PAMC", "PALJ", "PAIL"]),
]


def init(ctx):
    C.update(ctx)


def migrate(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(pilots)")}
    if cols and "pra" not in cols:
        con.execute("ALTER TABLE pilots ADD COLUMN pra INTEGER DEFAULT 0")  # cleared to fly for Pagani Remote Aviation


# ---------------------------------------------------------------- village freight on flights into Anchorage
def onward_cargo(seed, payload_lbs=None):
    """2–5 pieces, about 150–1,000 lb in all, for PRA strips. Deterministic for a seed so reprints match."""
    rng = random.Random(f"{seed}|pra-onward")
    picks = rng.sample(VILLAGE_FREIGHT, rng.randint(2, 4))
    out, total = [], 0
    for i, (desc, lb, pcs, shipper, consignee, why, shc, where) in enumerate(picks):
        w = rng.randint(*lb) // 5 * 5
        if total + w > 1000:
            continue
        dest = rng.choice(where)
        total += w
        out.append({"ref": f"PRA-{rng.randrange(10000, 99999)}-{i + 1}", "desc": desc, "lb": w, "pcs": rng.randint(*pcs),
                    "dest": dest, "dest_name": PRA_STRIPS[dest], "shipper": shipper, "consignee": consignee.format(v=PRA_STRIPS[dest]),
                    "why": why, "shc": list(shc)})
    return out


def add_onward(d, booking):
    """Called from dispatch.generate: PAC flights into Anchorage carry village freight for PRA."""
    m = booking.get("mission") or {}
    if d.get("ferry") or (d.get("destination") or {}).get("icao") != GATEWAY or m.get("contract") or not d.get("positions"):
        return d
    items = onward_cargo(f"{d['flight']}|{booking.get('requested_at')}")
    pos = d["positions"][-1]
    for it in items:
        it["pos"], it["awb"] = pos["pos"], pos["awb"]   # consolidated in the last unit loaded
    d["onward"] = items
    return d


# ---------------------------------------------------------------- the feed
_cache = {"t": 0, "data": None}


def _key():
    s = C["settings"]()
    k = (s.get("group_feed_key") or "").strip()
    if not k:
        k = secrets.token_urlsafe(24)
        s["group_feed_key"] = k
        C["save_settings"](s)
    return k


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "X-Group-Key"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Max-Age"] = "600"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _date(ts):
    return dt.datetime.fromtimestamp(ts or 0, dt.timezone.utc).strftime("%Y-%m-%d") if ts else None


def _fleet_name(code):
    f = C["FLEET"].get(code) or {}
    return f.get("short") or f.get("name") or code


def _base_url():
    """This site's address as the outside world sees it (Caddy terminates HTTPS in front of waitress)."""
    url = ((C["site"]().get("public_url") if C.get("site") else "") or request.host_url).rstrip("/")
    host = request.host.split(":")[0]
    if url.startswith("http://") and host not in ("localhost", "127.0.0.1"):
        url = "https://" + url[len("http://"):]
    return url


def _divisions(row, flown_types):
    divs = ["PAC"]
    regional = {k for k, v in C["FLEET"].items() if (v.get("division") or "") == "PAC Regional"}
    if flown_types & regional:
        divs.append("PAC Regional")
    if row.get("pra"):
        divs.append("PRA")
    return divs


def build_feed():
    con = C["db"]()
    try:
        pilots = [dict(r) for r in con.execute("SELECT id, name, hub, status, joined, pra FROM pilots ORDER BY id")]
        out_pilots = []
        for p in pilots:
            if (p.get("status") or "Active") in ("Inactive", "Removed", "Suspended"):
                continue
            rows = [dict(r) for r in con.execute(
                """SELECT filed_at, flight_number, dep, arr, aircraft, block_min, landing_rate FROM pireps
                   WHERE pilot_id=? AND demo=0 AND review_status='Accepted' ORDER BY filed_at DESC""", (p["id"],))]
            car = C["career"](p["id"], con)
            types = {r["aircraft"] for r in rows if r["aircraft"]}
            rates = [r["landing_rate"] for r in rows if r["landing_rate"] is not None]
            out_pilots.append({
                "callsign": p["id"], "name": p["name"], "rank": car["rank"], "base": p.get("hub") or "",
                "status": "leave" if p.get("status") == "On leave" else "active", "joined": _date(p.get("joined")),
                "hours": car["pac_hours"], "flights": car["flights"],
                "landing_avg": round(sum(rates) / len(rates)) if rates else None,
                "divisions": _divisions(p, types),
                "types": sorted({_fleet_name(t) for t in types}),
                "recent": [{"date": _date(r["filed_at"]), "flight": r["flight_number"], "from": r["dep"], "to": r["arr"],
                            "aircraft": _fleet_name(r["aircraft"]), "block_min": round(r["block_min"] or 0),
                            "landing": round(r["landing_rate"]) if r["landing_rate"] is not None else None} for r in rows[:RECENT_N]],
            })
        since = time.time() - HANDOFF_DAYS * 86400
        handoffs = []
        for r in con.execute("""SELECT id, filed_at, flight_number, aircraft, registration, airframe, dep, arr, pilot_id, detail FROM pireps
                                WHERE demo=0 AND review_status='Accepted' AND arr=? AND filed_at>=? ORDER BY filed_at DESC""", (GATEWAY, since)):
            d = json.loads(r["detail"] or "{}")
            disp = d.get("dispatch") or {}
            if disp.get("operator") or disp.get("ferry"):
                continue  # partner crew hires and ferries carry nothing for PRA
            cargo = disp.get("onward")
            if cargo is None:  # booked before village freight existed: same pieces every time for this PIREP
                cargo = onward_cargo(f"pirep-{r['id']}")
            if not cargo:
                continue
            handoffs.append({
                "id": f"PAC-PIREP-{r['id']}", "flight": r["flight_number"], "pilot": r["pilot_id"],
                "aircraft": _fleet_name(r["aircraft"]), "reg": r["airframe"] or r["registration"] or "", "from": r["dep"],
                "arrived": dt.datetime.fromtimestamp(r["filed_at"], dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "cargo": [{k: c.get(k) for k in ("ref", "desc", "lb", "pcs", "dest", "shipper", "consignee", "why", "shc")} for c in cargo],
            })
    finally:
        con.close()
    return {"airline": {"code": "PAC", "name": "Pagani Air Cargo", "site": _base_url()},
            "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "version": 1, "pilots": out_pilots, "handoffs": handoffs}


def _refuse():
    """None when the caller may read the group feeds, otherwise the refusal to send."""
    s = C["settings"]()
    if not s.get("group_feed_enabled"):
        return _cors(jsonify({"error": "The group feed is switched off (Staff › Site and rules › Pagani Aviation Group)."})), 404
    given = request.headers.get("X-Group-Key") or ""
    if not given or not hmac.compare_digest(given.encode(), _key().encode()):
        return _cors(jsonify({"error": "Wrong or missing group key."})), 403
    return None


@bp.route(FEED_PATH, methods=["GET", "OPTIONS"])
def feed():
    if request.method == "OPTIONS":
        return _cors(jsonify({}))
    if (no := _refuse()):
        return no
    now = time.time()
    if not _cache["data"] or now - _cache["t"] > FEED_CACHE_S:
        _cache.update(t=now, data=build_feed())
    return _cors(jsonify(_cache["data"]))


@bp.route(METAR_PATH, methods=["GET", "OPTIONS"])
def metar():
    """Current METARs for PRA's go/no-go. aviationweather.gov can't be read from a browser on another site (no CORS),
    so PRA asks through PAC, which already reads it for its own briefings (cached for a few minutes in weather.py)."""
    if request.method == "OPTIONS":
        return _cors(jsonify({}))
    if (no := _refuse()):
        return no
    import weather
    ids = [i for i in (request.args.get("ids") or "").upper().split(",") if i][:METAR_MAX]
    if not ids:
        return _cors(jsonify({"error": "Ask for at least one station, e.g. ?ids=PAMR,PATK"})), 400
    try:
        got = weather.metars(ids)
    except weather.WeatherError as e:
        return _cors(jsonify({"error": str(e)})), 502
    return _cors(jsonify({"metars": {k: v["raw"] for k, v in got.items()},
                          "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}))


# ---------------------------------------------------------------- staff
@bp.get("/api/staff/group")
def staff_group():
    s = C["settings"]()
    return jsonify({"enabled": bool(s.get("group_feed_enabled")), "key": _key(), "url": _base_url() + FEED_PATH,
                    "hub_url": s.get("group_hub_url") or ""})


@bp.post("/api/staff/group")
def staff_group_save():
    b = request.json or {}
    s = C["settings"]()
    if "enabled" in b:
        s["group_feed_enabled"] = bool(b["enabled"])
    if "hub_url" in b:
        s["group_hub_url"] = str(b["hub_url"] or "").strip()[:200]
    if b.get("new_key"):
        s["group_feed_key"] = secrets.token_urlsafe(24)
    C["save_settings"](s)
    _cache.update(t=0, data=None)
    return staff_group()


def clear_cache():
    _cache.update(t=0, data=None)
