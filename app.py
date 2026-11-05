"""Pagani Air Cargo ACARS - local server.

Run:  python app.py      then open http://localhost:5050
"""
from __future__ import annotations

import json
import threading
import os
import re

import pickle
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from performance_import import import_briefing
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from sim_sources import Telemetry, gc_distance_nm
from tracker import FlightRecorder, PHASES, zulu
import va
import analysis
import dispatch
import paperwork_release as releases
import discord_post  # noqa: E402  (flights to a Discord channel)
import mailer  # noqa: E402  (letters by email)
import online  # noqa: E402  (VATSIM and IVAO feeds)
import weather
import shutil
import economics
import acars_core

BASE = Path(__file__).parent
DATA = BASE / "data"
DB_PATH = DATA / "logbook.db"
SETTINGS_PATH = DATA / "settings.json"
BOOKING_PATH = DATA / "booking.json"
FLIGHT_STATE_PATH = DATA / "flight_state.pkl"
PROFILE_PATH = DATA / "profile.json"
PHOTO_EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

DEFAULT_PROFILE = {
    "rank": "Captain",
    "name": "Joseph Pagani",
    "title": "Founder, CEO and Senior Pilot",
    "pilot_id": "PAC0001",
    "callsign": "PAGANI",
    "base": "KCVG Cincinnati/Northern Kentucky (main hub)",
    "secondary_base": "LIMC Milan Malpensa",
    "member_since": "2026-01-01",
    "bio": "Founder of Pagani Air Cargo and the airline's senior line captain. Built the network around one idea: when a region needs relief, medicine or a critical part, a PAC freighter is already on its way. Flies the full fleet and personally checks out every new type before it enters service.",
    "photo": "/static/pilot-photo.jpg",
    "credentials": [
        {"label": "Pilot license", "value": "Airline Transport Pilot (ATPL / ATP)", "detail": "Multi-engine land, instrument", "expires": ""},
        {"label": "Medical", "value": "First class", "detail": "", "expires": ""},
        {"label": "Instrument rating", "value": "IR multi-engine, CAT IIIb", "detail": "Low-visibility operations approved", "expires": ""},
        {"label": "Long-range operations", "value": "ETOPS 180 / RVSM / NAT HLA", "detail": "Oceanic and polar routes", "expires": ""},
        {"label": "Dangerous goods", "value": "Category 10 (cargo aircraft)", "detail": "IATA DGR", "expires": ""},
        {"label": "Language proficiency", "value": "ICAO English level 6", "detail": "Italian native", "expires": ""},
        {"label": "Company role", "value": "Chief pilot and line check captain", "detail": "Type rating instructor, all fleets", "expires": ""},
    ],
    "type_ratings": [
        {"type": "B737", "fleet": "B738F", "name": "Boeing 737-800BCF / BDSF", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": ""},
        {"type": "B727", "fleet": "B722F", "name": "Boeing 727-200F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "Three-crew, flight engineer panel"},
        {"type": "A300", "fleet": "A306F", "name": "Airbus A300-600F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": ""},
        {"type": "B747", "fleet": "B748F", "name": "Boeing 747-8F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "Nose-door outsized cargo"},
        {"type": "B777", "fleet": "B77F", "name": "Boeing 777F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "ETOPS"},
        {"type": "MD11", "fleet": "MD11F", "name": "McDonnell Douglas MD-11F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": ""},
        {"type": "B737", "fleet": "B733F", "name": "Boeing 737-300SF", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "X-Plane, IXEG"},
        {"type": "B737", "fleet": "B732F", "name": "Boeing 737-200C Advanced", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "X-Plane, FlyJSim, gravel kit"},
        {"type": "B757", "fleet": "B752F", "name": "Boeing 757-200F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "X-Plane"},
        {"type": "B767", "fleet": "B763F", "name": "Boeing 767-300F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "X-Plane"},
        {"type": "B747", "fleet": "B742F", "name": "Boeing 747-200F", "role": "Captain", "issued": "", "prior_hours": 0, "status": "Active", "notes": "X-Plane, FELIS, three-crew"},
    ],
}

def load_json_file(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


app = Flask(__name__, static_folder=str(BASE / "static"), static_url_path="/static")

MISSIONS = {m["id"]: m for m in json.loads((DATA / "missions.json").read_text(encoding="utf-8"))}
_partners_file = json.loads((DATA / "partners.json").read_text(encoding="utf-8")) if (DATA / "partners.json").exists() else {"partners": {}}
PARTNERS = _partners_file["partners"]
ROUTES = {r["id"]: r for r in load_json_file(DATA / "routes.json", [])} if (DATA / "routes.json").exists() else {}
_ap = json.loads((DATA / "airports.json").read_text(encoding="utf-8"))
AIRPORTS = {r[0]: dict(zip(_ap["fields"], r)) for r in _ap["rows"]}
del _ap
CARGO_TYPES = ["General cargo", "Express parcels", "E-commerce parcels", "Mail", "Perishables", "Fresh flowers",
               "Seafood", "Pharmaceuticals (temperature controlled)", "Medical supplies", "Humanitarian relief",
               "Livestock", "Dangerous goods", "Automotive parts", "Aircraft spares (AOG)", "Electronics",
               "Oversized / heavy machinery", "Valuables", "Military logistics", "Ferry flight (no cargo)"]
FLEET = json.loads((DATA / "fleet.json").read_text(encoding="utf-8"))
FLEET_CUSTOM_PATH = DATA / "fleet_custom.json"   # your edits, kept apart so updates don't overwrite them
FLEET_PHOTO_DIR = DATA / "fleet_photos"
FLEET_TEXT = ("role", "division", "description", "engines", "crew", "main_deck", "sim", "sim_model", "name", "icao", "simbrief_type",
              "unlock_rank")
FLEET_NUM = ("max_payload_lbs", "mtow_lbs", "range_nm", "min_rwy_ft", "cruise_ktas", "mach", "tailstrike_pitch", "fuel_burn_pph",
             "maint_per_bh", "ownership_per_bh", "entered_service")
FLEET_EDITABLE = FLEET_TEXT + FLEET_NUM + ("registrations", "photo", "thumb", "retired")
FLEET_BASE_CODES = set(FLEET)
TYPE_DEFAULTS = {"sim": "MSFS", "sim_model": "", "role": "", "division": "PAC", "description": "", "engines": "", "crew": "2 (Captain, First Officer)",
                 "main_deck": "", "mach": 0.8, "entered_service": None, "registrations": [], "photo": "/static/pac-logo.png",
                 "thumb": "/static/pac-logo.png", "tailstrike_pitch": 11.0, "retired": False}
for _code, _edits in (json.loads(FLEET_CUSTOM_PATH.read_text(encoding="utf-8")) if FLEET_CUSTOM_PATH.exists() else {}).items():
    if _edits.get("deleted"):
        FLEET.pop(_code, None)
    elif _code in FLEET:
        FLEET[_code].update({k: v for k, v in _edits.items() if k in FLEET_EDITABLE})
    elif _edits.get("custom_type"):
        FLEET[_code] = {**TYPE_DEFAULTS, **{k: v for k, v in _edits.items() if k in FLEET_EDITABLE}, "custom_type": True}

# PAC's fleet divisions: a label for each type, used on the fleet page, flights, logbook and stats. Staff can move a
# type by setting its Division to one of these names in Staff › Fleet types; anything else falls back to the default below.
DIVISIONS = [
    {"name": "PAC Feeder", "short": "Feeder", "blurb": "737 freighters on short and medium sectors around PAC's hubs. Where most pilots start."},
    {"name": "PAC Mainline", "short": "Mainline", "blurb": "Medium widebodies and the 757 on the core network: A300-600F, 757-200F and 767-300F."},
    {"name": "PAC Heavy", "short": "Heavy", "blurb": "Long-haul widebodies on intercontinental and outsize work: MD-11F, 777F and the 747s."},
    {"name": "PAC Heritage", "short": "Heritage", "blurb": "Classic jets kept flying for the work they still do best: the 727s, the 737-200 and the 747-200."},
]
DIVISION_DEFAULT = {"B733F": "PAC Feeder", "B738F": "PAC Feeder",
                    "A306F": "PAC Mainline", "B752F": "PAC Mainline", "B763F": "PAC Mainline",
                    "MD11F": "PAC Heavy", "B77F": "PAC Heavy", "B744F": "PAC Heavy", "B748F": "PAC Heavy",
                    "B722F": "PAC Heritage", "R722F": "PAC Heritage", "B732F": "PAC Heritage", "B742F": "PAC Heritage"}


def fleet_division(code):
    a = FLEET.get(code) or {}
    d = str(a.get("division") or "").strip()
    if d in {x["name"] for x in DIVISIONS}:
        return d
    if code in DIVISION_DEFAULT:
        return DIVISION_DEFAULT[code]
    m = a.get("mtow_lbs") or 0           # a type staff added later: by size
    return "PAC Feeder" if m < 200_000 else "PAC Mainline" if m < 450_000 else "PAC Heavy"


def apply_divisions():
    for _k in FLEET:
        FLEET[_k]["division"] = fleet_division(_k)


apply_divisions()

DEFAULT_SETTINGS = {"pilot_name": "", "pilot_id": "PAC0001", "simbrief_username": "", "simbrief_userid": "",
                    "source": "MSFS", "demo_speedup": 60, "xplane_host": "127.0.0.1", "map_style": "dark", "allow_ground_reposition": True,
                    "enforce_ranks": False, "enforce_airframes": True,
                    "fuel_price_gal": economics.DEFAULT_FUEL_PRICE, "starting_capital": economics.DEFAULT_START_CAPITAL,
                    "vatsim_cid": "", "ivao_vid": "", "enforce_pilot_location": True, "require_type_ratings": False, "direct_entry_checkrides": True, "require_release_signature": True,
                    "discord_webhook": "", "discord_departures": True, "discord_arrivals": True,
                    "mail_from": "", "mail_from_name": "Pagani Air Cargo", "mail_reply_to": "", "smtp_host": "", "smtp_port": 587,
                    "smtp_security": "starttls", "smtp_user": "", "smtp_pass": "", "mail_auto_welcome": True, "mail_auto_decline": False,
                    "reuse_pilot_ids": False, "shop_enabled": True,
                    "live_map_public": False, "discord_bot_enabled": False, "discord_bot_token": "", "discord_guild": "",
                    "discord_ch_flights": "flight-log", "discord_ch_news": "announcements", "discord_ch_welcome": "welcome",
                    "filing_icao": "PGC",
                    "vatsim_partner_section": False, "ivao_partner_section": False,   # the VATSIM logo on the home page: only once VATSIM has accepted PAC     # the ICAO code pilots file under on VATSIM and IVAO (PAC belongs to Polar Air Cargo)
                    "discord_ch_dispatch": "dispatch", "discord_ch_notams": "notams", "discord_dispatch_missions": True, "discord_dispatch_partners": True,
                    "discord_dispatch_urgent": True, "discord_dispatch_per_hour": 4,
                    "discord_pilot_role": "PAC Pilot", "discord_staff_role": "PAC Staff", "discord_rank_roles": True,
                    "si_enabled": False, "si_va_key": "", "si_coupon": "", "si_dispatcher_freq": "118.94", "si_notes": ""}

# Each pilot gets their own flight session, so several pilots can fly at once. state is this request's session;
# SESSIONS holds them all, keyed by pilot ID.
SESSIONS = {}
SESSION_BLANK = {"thread": None, "recorder": None, "source_name": None, "remote": None, "remote_status": None, "remote_seen": 0,
                 "ofp_watch": None, "discord_dep_for": None}


def session(pid=None):
    """The flight session for a pilot (this request's pilot by default)."""
    pid = pid or va.current_pilot_id()
    return SESSIONS.setdefault(pid, dict(SESSION_BLANK))


class _CurrentSession(dict):
    """`state` keeps working as before, but points at the session of whoever is making the request."""
    def _s(self):
        return session()

    def __getitem__(self, k):
        return self._s()[k]

    def __setitem__(self, k, v):
        self._s()[k] = v

    def __contains__(self, k):
        return k in self._s()

    def get(self, k, default=None):
        return self._s().get(k, default)

    def update(self, *a, **kw):
        self._s().update(*a, **kw)

    def pop(self, k, *a):
        return self._s().pop(k, *a)


state = _CurrentSession()
REMOTE_TIMEOUT = 45  # seconds without a live update before the website shows the ACARS app as disconnected


# ---------------------------------------------------------------- storage
def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def settings():
    return {**DEFAULT_SETTINGS, **load_json(SETTINGS_PATH, {})}


SECRET_SETTINGS = ("discord_webhook", "smtp_pass", "si_va_key", "discord_bot_token", "group_feed_key")  # never sent to the browser


# Settings each pilot keeps for themselves; everything else in settings.json is the airline's, changed by staff.
PERSONAL_SETTINGS = ("simbrief_username", "simbrief_userid", "vatsim_cid", "ivao_vid", "map_style")
# ones that identify a person: another pilot never inherits the founder's
PERSONAL_IDS = ("simbrief_username", "simbrief_userid", "vatsim_cid", "ivao_vid")


def _pilot_prefs(pid, con=None):
    try:
        r = (con or db()).execute("SELECT simbrief, prefs FROM pilots WHERE id=?", (pid,)).fetchone()
    except Exception:
        return None, {}
    if not r:
        return None, {}
    try:
        prefs = json.loads(r["prefs"] or "{}")
    except (ValueError, TypeError):
        prefs = {}
    return (r["simbrief"] or "").strip(), prefs if isinstance(prefs, dict) else {}


def pilot_settings(st=None, pid=None):
    """Settings as one pilot sees them: the airline's, with their own SimBrief, VATSIM and IVAO details and map
    style. The founder's older single-pilot values still apply to the founder until changed."""
    st = dict(st or settings())
    pid = pid or va.current_pilot_id()
    simbrief, prefs = _pilot_prefs(pid)
    if pid != (st.get("pilot_id") or "PAC0001"):
        for k in PERSONAL_IDS:
            st[k] = ""
    for k in PERSONAL_SETTINGS:
        if k in prefs:
            st[k] = prefs[k]
    if simbrief:
        st["simbrief_username"], st["simbrief_userid"] = simbrief, ""
    return st


def public_settings(st=None):
    """Settings as the browser sees them: passwords and webhook addresses are secrets, so only whether they're set."""
    st = pilot_settings(st)
    st["discord_enabled"] = bool(st.get("discord_webhook"))
    st["mail_ready"] = mailer.config_ready(st)
    st["si_ready"] = bool(st.get("si_enabled") and (st.get("si_va_key") or "").strip())
    st["si_key_set"] = bool((st.get("si_va_key") or "").strip())
    st["discord_bot_token_set"] = bool((st.get("discord_bot_token") or "").strip())
    st["simbrief_api"] = bool(simbrief_api_key())   # one-click OFP generation (the key itself never leaves the server)
    for k in SECRET_SETTINGS:
        st.pop(k, None)
    return st


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS pireps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, filed_at REAL, mission_id TEXT, mission_title TEXT, category TEXT,
        flight_number TEXT, aircraft TEXT, registration TEXT, dep TEXT, arr TEXT, planned_arr TEXT,
        block_min REAL, flight_min REAL, distance_nm REAL, fuel_used_lbs REAL, payload_lbs REAL,
        landing_rate REAL, landing_g REAL, score INTEGER, grade TEXT, status TEXT, points INTEGER,
        demo INTEGER, source TEXT, remarks TEXT, detail TEXT)""")
    key = str(Path(DB_PATH).resolve())
    if key not in _MIGRATED:  # prepare each database file the first time it's opened (tests and restores switch files)
        _MIGRATED.add(key)
        va.migrate(con)
        # Each flight's row carries its whole recorded track, so finding flights by pilot or review status without an index
        # meant reading through every track. These indexes let the logbook, career, home page and boards jump straight there.
        con.execute("CREATE INDEX IF NOT EXISTS idx_pireps_pilot ON pireps(pilot_id, demo, review_status, filed_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_pireps_feed ON pireps(demo, review_status, filed_at)")
        import manual_pireps
        manual_pireps.migrate(con)
        import auth
        auth.migrate(con)
        import group
        group.migrate(con)
        import rotation_planner
        rotation_planner.migrate(con)
        import cargo_programs
        cargo_programs.migrate(con)
        con.commit()
    return con


_MIGRATED = set()


# ---------------------------------------------------------------- SimBrief
def xml_to_obj(el):
    children = list(el)
    if not children:
        return (el.text or "").strip()
    out = {}
    for c in children:
        v = xml_to_obj(c)
        if c.tag in out:
            if not isinstance(out[c.tag], list):
                out[c.tag] = [out[c.tag]]
            out[c.tag].append(v)
        else:
            out[c.tag] = v
    return out


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def first(v):
    return v[0] if isinstance(v, list) and v else v


def parse_ofp(raw: dict) -> dict:
    if "OFP" in raw:
        raw = raw["OFP"]
    gen, fuel, wts = raw.get("general", {}), raw.get("fuel", {}), raw.get("weights", {})
    units = (raw.get("params", {}).get("units") or "lbs").lower()
    k = 2.20462 if units.startswith("kg") else 1.0

    def apt(a):
        a = first(a) or {}
        if not a or not a.get("icao_code"):
            return None
        return {"icao": a.get("icao_code"), "name": a.get("name", ""), "lat": num(a.get("pos_lat")),
                "lon": num(a.get("pos_long")), "runway": a.get("plan_rwy", ""), "elevation": num(a.get("elevation"))}

    fixes = raw.get("navlog", {}).get("fix", []) if isinstance(raw.get("navlog"), dict) else []
    if isinstance(fixes, dict):
        fixes = [fixes]
    route_pts = [[num(f.get("pos_lat")), num(f.get("pos_long")), f.get("ident", "")] for f in fixes if f.get("pos_lat")]
    times = raw.get("times", {})
    ac = raw.get("aircraft", {})
    return {
        "briefing": import_briefing(raw),
        "request_id": raw.get("params", {}).get("request_id", ""),
        "generated": raw.get("params", {}).get("time_generated", ""),
        "airline": gen.get("icao_airline", ""), "flight_number": gen.get("flight_number", ""),
        "callsign": raw.get("atc", {}).get("callsign", ""),
        "origin": apt(raw.get("origin")), "destination": apt(raw.get("destination")), "alternate": apt(raw.get("alternate")),
        "route": gen.get("route", ""), "cruise_ft": num(gen.get("initial_altitude")), "cost_index": gen.get("costindex", ""),
        "distance_nm": num(gen.get("route_distance")) or num(gen.get("air_distance")),
        "aircraft_icao": ac.get("icaocode", ""), "aircraft_name": ac.get("name", ""), "registration": ac.get("reg", ""),
        "units": units,
        "block_fuel_lbs": round(num(fuel.get("plan_ramp")) * k), "trip_fuel_lbs": round(num(fuel.get("enroute_burn")) * k),
        "reserve_fuel_lbs": round(num(fuel.get("reserve")) * k), "taxi_fuel_lbs": round(num(fuel.get("taxi")) * k),
        "payload_lbs": round(num(wts.get("payload")) * k), "cargo_lbs": round(num(wts.get("cargo")) * k),
        "zfw_lbs": round(num(wts.get("est_zfw")) * k), "tow_lbs": round(num(wts.get("est_tow")) * k),
        "ldw_lbs": round(num(wts.get("est_ldw")) * k),
        "est_block_min": round(num(times.get("est_block")) / 60), "est_enroute_min": round(num(times.get("est_time_enroute")) / 60),
        "route_points": route_pts,
    }


def fetch_simbrief(s) -> dict:
    if s.get("simbrief_userid"):
        q = {"userid": s["simbrief_userid"]}
    elif s.get("simbrief_username"):
        q = {"username": s["simbrief_username"]}
    else:
        raise ValueError("Add your SimBrief username or pilot ID in Settings first.")
    q["json"] = "1"
    url = "https://www.simbrief.com/api/xml.fetcher.php?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "PAC-ACARS/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            msg = body.get("fetch", {}).get("status", "")
        except Exception:
            msg = ""
        raise ValueError(msg or f"SimBrief returned HTTP {e.code}. Check your username or pilot ID.")
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach SimBrief: {e.reason}")


# ---------------------------------------------------------------- SimBrief API (generate an OFP from PAC)
# The airline's SimBrief API key lives in data/simbrief_api_key (or the PAC_SIMBRIEF_API_KEY environment variable).
# It is only ever used here to sign requests; it is never sent to a browser.
SB_OFP_ID = re.compile(r"^[0-9]{10}_[A-Za-z0-9]{10}$")


def simbrief_api_key():
    k = os.environ.get("PAC_SIMBRIEF_API_KEY", "").strip()
    if not k:
        try:
            k = (DATA / "simbrief_api_key").read_text(encoding="utf-8").strip()
        except OSError:
            k = ""
    return k


def fetch_simbrief_ofp_id(ofp_id) -> dict:
    """The OFP SimBrief generated through the API, by its id."""
    if not SB_OFP_ID.match(str(ofp_id or "")):
        raise ValueError("That isn't a SimBrief plan id.")
    url = f"https://www.simbrief.com/ofp/flightplans/xml/{ofp_id}.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "PAC-ACARS/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return xml_to_obj(ET.fromstring(r.read()))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError("SimBrief hasn't finished that plan. If you closed the SimBrief window early, generate it again.")
        raise ValueError(f"SimBrief returned HTTP {e.code}.")
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach SimBrief: {e.reason}")


def validate_ofp(ofp, mission, aircraft_code):
    errors, warnings = [], []
    if not ofp.get("origin") or not ofp.get("destination"):
        errors.append("This OFP has no origin or destination. Generate a full flight plan in SimBrief.")
        return errors, warnings
    if ofp["origin"]["icao"] != mission["origin"]["icao"]:
        errors.append(f"Your SimBrief plan departs {ofp['origin']['icao']}, but this flight departs {mission['origin']['icao']}. Plan it again with \"Open SimBrief with this mission\".")
    if ofp["destination"]["icao"] != mission["destination"]["icao"]:
        errors.append(f"Your SimBrief plan arrives at {ofp['destination']['icao']}, but this flight goes to {mission['destination']['icao']}. Plan it again with \"Open SimBrief with this mission\".")
    ac = FLEET.get(aircraft_code)
    if ac:
        if ofp.get("aircraft_icao") and ofp["aircraft_icao"] not in (ac["icao"], ac["simbrief_type"]):
            warnings.append(f"OFP aircraft is {ofp['aircraft_icao']}, you selected the {ac['name']}.")
        if ofp.get("payload_lbs", 0) > ac["max_payload_lbs"]:
            errors.append(f"Your plan carries {ofp['payload_lbs']:,} lb, more than the {ac['name']}'s limit of {ac['max_payload_lbs']:,} lb. Check the aircraft picked in step 1, or lower the payload in SimBrief.")
    if ac and ac["max_payload_lbs"] < mission["payload_lbs"]:
        warnings.append(f"The {ac['name']} carries up to {ac['max_payload_lbs']:,} lb, so this is a partial load of the {mission['payload_lbs']:,} lb mission cargo.")
    elif ofp.get("payload_lbs") and ofp["payload_lbs"] < mission["payload_lbs"] * 0.9:
        warnings.append(f"OFP payload {ofp['payload_lbs']:,} lb is below the mission load of {mission['payload_lbs']:,} lb.")
    return errors, warnings


# ---------------------------------------------------------------- PIREP
def landing_weight_check(code, weight):
    """(landing weight, MLW) when both are known and the weight is believable; otherwise (None, None).
    MLW comes from the published limits PAC's paperwork uses; types without one aren't checked."""
    lim = dispatch.LIMITS.get(code)
    mtow = (FLEET.get(code) or {}).get("mtow_lbs") or 0
    try:
        w = float(weight or 0)
    except (TypeError, ValueError):
        return None, None
    if not lim or not mtow or not (mtow * 0.35 < w < mtow * 1.3):   # no data, or a sim that doesn't report weight sensibly
        return None, None
    return w, lim[1]


def build_pirep(booking, rec: FlightRecorder):
    m, ofp = booking["mission"], booking.get("ofp") or {}
    o, f = rec.oooi, rec.fuel
    block_min = ((o["in"] or rec.last.t) - (o["out"] or rec.start_t)) / 60
    flight_min = ((o["on"] - o["off"]) / 60) if (o["on"] and o["off"]) else 0
    fuel_used = (f["out"] or f["start"] or 0) - (f["in"] if f["in"] is not None else rec.last.fuel_lbs)
    trip_burn = (f["off"] - f["on"]) if (f["off"] is not None and f["on"] is not None) else None
    items = []  # (label, delta)

    for e in rec.events:
        if e["penalty"]:
            items.append((e["text"].title(), -e["penalty"]))

    land = rec.landing or {}
    rate = land.get("rate_fpm")
    crashed = False
    if rate is not None:
        if rate < -1000:
            crashed = True
            items.append((f"Landing {rate} fpm: structural damage", -100))
        elif rate < -600:
            items.append((f"Hard landing {rate} fpm: inspection required", -35))
        elif rate < -400:
            items.append((f"Heavy landing {rate} fpm", -15))
        elif rate < -250:
            items.append((f"Firm landing {rate} fpm", -5))
        elif rate >= -100:
            items.append((f"Butter landing {rate} fpm", 0))
        else:
            items.append((f"Smooth landing {rate} fpm", 0))
    g = land.get("g")
    if g and g > 2.5:
        items.append((f"Landing load {g} G", -20))
    elif g and g > 1.8:
        items.append((f"Landing load {g} G", -10))

    if trip_burn is not None and ofp.get("trip_fuel_lbs"):
        var = (trip_burn - ofp["trip_fuel_lbs"]) / ofp["trip_fuel_lbs"] * 100
        # only burning MORE than planned costs points: a shortcut from ATC or a better routing that saves fuel never does
        if var > 25:
            items.append((f"Trip fuel {var:+.0f}% against plan", -10))
        elif var > 15:
            items.append((f"Trip fuel {var:+.0f}% against plan", -5))
        elif var < -15:
            items.append((f"Trip fuel {var:+.0f}% against plan (fuel saved, e.g. a shortcut)", 0))
        else:
            items.append((f"Trip fuel {var:+.0f}% against plan", 0))
    if f["on"] is not None and ofp.get("reserve_fuel_lbs") and f["on"] < ofp["reserve_fuel_lbs"]:
        items.append(("Landed below final reserve fuel", -15))

    # landing weight against the type's maximum landing weight (the sim's gross weight at touchdown)
    ldw, mlw = landing_weight_check(booking["aircraft"], (getattr(rec, "weights", None) or {}).get("landing"))
    if ldw and mlw and ldw > mlw * 1.005:          # half a percent of grace for how sims round weights
        over = ldw - mlw
        items.append((f"Overweight landing: {over:,.0f} lb over the {mlw:,.0f} lb MLW, inspection required", -20 if over > mlw * 0.05 else -10))

    # arrival airport
    last = rec.last
    dest = rec.dest
    d_dest = gc_distance_nm(last.lat, last.lon, dest["lat"], dest["lon"])
    arr_icao, status = dest["icao"], "Delivered"
    dd = getattr(rec, "declared_diversion", None)
    dd_ap = AIRPORTS.get(dd["icao"]) if dd else None
    if d_dest > 5 and dd_ap and gc_distance_nm(last.lat, last.lon, dd_ap["lat"], dd_ap["lon"]) <= 5:
        arr_icao, status = dd_ap["icao"], "Diverted"
        items.append((f"Diverted to {dd_ap['icao']} ({dd['reason'].lower()}), declared to dispatch at {zulu(dd['t'])}", -10))
    elif d_dest > 5:
        alt = rec.alternate
        if alt and gc_distance_nm(last.lat, last.lon, alt["lat"], alt["lon"]) <= 5:
            arr_icao, status = alt["icao"], "Diverted"
            items.append((f"Diverted to alternate {alt['icao']}", -20))
        else:
            arr_icao, status = "UNKNOWN", "Failed"
            items.append((f"Parked {d_dest:.0f} nm from {dest['icao']}", -40))

    target = ofp.get("est_block_min") or m["target_block_min"]
    excused = sum(d["minutes"] for d in (getattr(rec, "reported_delays", None) or []) if d["reason"] in EXCUSED_DELAYS)
    if status == "Delivered" and target:
        ratio = max(0.0, block_min - excused) / target
        if excused and block_min / target > (1.25 if m["priority"] in ("Critical", "High") else 1.35) and ratio <= (1.25 if m["priority"] in ("Critical", "High") else 1.35):
            items.append((f"Late, but {excused} min of delay reported to dispatch ({', '.join(sorted({EXCUSED_DELAYS[d['reason']] for d in rec.reported_delays}))})", 0))
        urgent = m["priority"] in ("Critical", "High")
        if urgent and ratio <= 1.10:
            items.append(("On-time delivery bonus", 5))
        elif ratio > (1.25 if urgent else 1.35):
            items.append((f"Late delivery: {block_min - target:+.0f} min against plan", -10 if urgent else -5))
            status = "Delivered late"

    score = max(0, min(100, 100 + sum(d for _, d in items)))
    if crashed:
        status, score = "Failed", 0
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
    points = 0 if status == "Failed" else round(m["reward"] * score / 100)
    p = {
        "mission_id": m["id"], "mission_title": m["title"], "category": m["category"],
        "flight_number": booking["flight_number"], "aircraft": booking["aircraft"],
        "aircraft_name": FLEET.get(booking["aircraft"], {}).get("name", booking["aircraft"]),
        "registration": booking.get("partner_reg") or ofp.get("registration", ""), "dep": rec.origin["icao"], "arr": arr_icao,
        "planned_arr": dest["icao"], "block_min": round(block_min, 1), "flight_min": round(flight_min, 1),
        "target_block_min": target, "distance_nm": round(rec.distance_nm), "fuel_used_lbs": round(fuel_used),
        "trip_burn_lbs": round(trip_burn) if trip_burn is not None else None,
        "planned_trip_lbs": ofp.get("trip_fuel_lbs"),
        # Cargo delivered is the mission consignment (capped by what the aircraft can carry);
        # any extra planned in SimBrief is recorded as loaded but not counted as delivered.
        "payload_lbs": min(ofp.get("payload_lbs") or m["payload_lbs"], m["payload_lbs"],
                           FLEET.get(booking["aircraft"], {}).get("max_payload_lbs", m["payload_lbs"])),
        "loaded_lbs": ofp.get("payload_lbs") or None,
        "mission_payload_lbs": m["payload_lbs"],
        "landing_weight_lbs": round(ldw) if ldw else None, "mlw_lbs": mlw,
        "landing_rate": rate, "landing_g": g, "bounces": rec.bounces, "max_alt": round(rec.max_alt),
        "score": score, "grade": grade, "status": status, "points": points, "breakdown": items,
        "oooi": rec.oooi, "demo": state["source_name"] == "Demo", "source": state["source_name"],
        "airframe": booking.get("airframe"),
    }
    series = getattr(rec, "landing_series", None)
    if series and rec.landing:
        near = va.nearest_airport(rec.landing["lat"], rec.landing["lon"], within=4)
        tries = [x for x in [dest["icao"], (rec.alternate or {}).get("icao"), near] if x]
        p["landing_analysis"] = analysis.analyze_landing(series, getattr(rec, "landing_touchdown_t", o["on"]), rate, g, tries, DATA, gc_distance_nm)
    tseries = getattr(rec, "takeoff_series", None)
    if tseries:
        orig = rec.origin["icao"]
        near_o = va.nearest_airport(tseries[0][5], tseries[0][6], within=4)
        tl = FLEET.get(booking["aircraft"], {}).get("tailstrike_pitch")
        p["takeoff_analysis"] = analysis.analyze_takeoff(tseries, o["off"], [x for x in [orig, near_o] if x], DATA, tl)
    lw = getattr(rec, "landing_wx", None)
    if lw:
        la = p.get("landing_analysis") or {}
        comp = weather.components(lw.get("wind"), la.get("runway_heading"))
        la["wind"] = {"station": lw["station"], "raw": lw["raw"], "text": weather.wind_text(lw.get("wind")), "category": lw.get("category"),
                      **(comp or {})}
        p["landing_analysis"] = la
    ta = p.get("takeoff_analysis") or {}
    if ta.get("tail_strike"):
        p["breakdown"].append((f"Tail strike: {ta['max_pitch_ground']}° pitch on the ground (limit {ta['tail_limit']}°)", -25))
        p["score"] = max(0, min(100, 100 + sum(x[1] for x in p["breakdown"])))
        p["grade"] = "A" if p["score"] >= 90 else "B" if p["score"] >= 80 else "C" if p["score"] >= 70 else "D" if p["score"] >= 60 else "F"
    p["integrity"] = {"paused_air_min": round(getattr(rec, "paused_air_s", 0) / 60, 1), "accel_s": round(getattr(rec, "accel_s", 0)),
                      "max_rate": getattr(rec, "max_rate", 1.0)}
    p = va.enrich_pirep(p, booking, rec)
    m_ = booking["mission"]
    dist = gc_distance_nm(m_["origin"]["lat"], m_["origin"]["lon"], m_["destination"]["lat"], m_["destination"]["lon"])
    p["economics"] = economics.flight_economics(p, booking, FLEET, settings(), dist)
    m_ = booking["mission"]
    rank_ = va.career(va.current_pilot_id())["rank"]
    if p.get("demo") or m_.get("training"):
        p["pay"] = None
    elif m_.get("contract"):
        p["pay"] = va.contract_pay(p.get("block_min"), rank_, m_.get("contract_bonus"), m_.get("contract_rate_mult") or va.CONTRACT_RATE_MULT)
    else:
        p["pay"] = va.flight_pay(p.get("block_min"), rank_, p["economics"]["profit"])
        if m_.get("ferry_bonus"):
            p["pay"]["ferry_bonus"] = m_["ferry_bonus"]
            p["pay"]["total"] += m_["ferry_bonus"]
    if p.get("pay"):
        va.add_skill(p["pay"], p)
    if m_.get("job"):
        p["job"] = {k: m_.get(k) for k in ("job_kind", "contract", "contract_bonus", "contract_rate_mult", "ferry_bonus", "job_type")}
        if m_.get("operator"):
            p["job"]["operator_name"] = m_["operator"]["name"]
    if m_.get("training"):
        p['economics'] = economics._result(0, {}, ['Company-funded training: no commercial revenue or pilot pay.'], 0)
        p['payload_lbs'] = 0
        if m_['training']['mode'] == 'dedicated':
            p['registration'] = 'TRAINING'
    return p


# ---------------------------------------------------------------- logbook repair
LANDING_PREFIXES = ("Landing ", "Hard landing", "Heavy landing", "Firm landing", "Smooth landing", "Butter landing")


def landing_items(rate):
    if rate < -1000:
        return [(f"Landing {rate} fpm: structural damage", -100)]
    if rate < -600:
        return [(f"Hard landing {rate} fpm: inspection required", -35)]
    if rate < -400:
        return [(f"Heavy landing {rate} fpm", -15)]
    if rate < -250:
        return [(f"Firm landing {rate} fpm", -5)]
    if rate >= -100:
        return [(f"Butter landing {rate} fpm", 0)]
    return [(f"Smooth landing {rate} fpm", 0)]


def repair_logbook():
    """Fixes PIREPs filed by version 1, which had two telemetry bugs:
    MSFS vertical speed was multiplied by 60 (inflating landing rates), and failed
    SimConnect reads came through as 0 and were flagged as position jumps.
    A read glitch shows up as a pair of identical jumps (away and back); a real
    slew does not come back, so only paired jumps are removed."""
    import re
    with db() as con:
        for row in con.execute("SELECT id, mission_id, source, landing_rate, status, detail FROM pireps").fetchall():
            try:
                d = json.loads(row["detail"] or "{}")
            except (TypeError, ValueError):
                continue  # no usable detail: nothing to repair, and never stop the website starting
            if not d or d.get("v", 1) >= 2:
                continue
            items = [list(x) for x in d.get("breakdown", [])]
            notes = []
            rate = row["landing_rate"]
            if row["source"] == "MSFS" and rate is not None:
                rate = round(rate / 60)
                items = [x for x in items if not x[0].startswith(LANDING_PREFIXES)] + [list(x) for x in landing_items(rate)]
                if d.get("landing"):
                    d["landing"]["rate_fpm"] = rate
                notes.append("landing rate corrected")
            jumps = sorted([e for e in d.get("events", []) if e.get("kind") == "slew" and "POSITION JUMP" in e.get("text", "")], key=lambda e: e["t"])
            dist = lambda e: float(re.findall(r"([\d.]+)NM", e["text"])[0])
            removed, i = 0, 0
            while i < len(jumps) - 1:
                a, b = jumps[i], jumps[i + 1]
                if b["t"] - a["t"] <= 10 and abs(dist(a) - dist(b)) <= max(2.0, dist(a) * 0.01):
                    a["penalty"] = b["penalty"] = 0
                    removed += 2
                    i += 2
                else:
                    i += 1
            for _ in range(removed):
                for x in items:
                    if x[0].startswith("Position Jump"):
                        items.remove(x)
                        break
            if removed:
                notes.append(f"{removed} false position-jump flags removed")
            status = "Delivered"
            labels = " ".join(x[0] for x in items)
            if "Late delivery" in labels:
                status = "Delivered late"
            if "Diverted to alternate" in labels:
                status = "Diverted"
            if any(x[0].startswith("Parked ") for x in items):
                status = "Failed"
            score = max(0, min(100, 100 + sum(x[1] for x in items)))
            if any("structural damage" in x[0] for x in items):
                status, score = "Failed", 0
            if notes:
                items.append([f"Corrected by ACARS update: {', '.join(notes)}", 0])
            grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
            reward = (MISSIONS.get(row["mission_id"]) or va.live_mission(row["mission_id"], True) or ROUTES.get(row["mission_id"]) or va.TOUR_LEGS.get(row["mission_id"]) or {}).get("reward", 0)
            points = 0 if status == "Failed" else round(reward * score / 100)
            d["breakdown"], d["v"] = items, 2
            con.execute("UPDATE pireps SET landing_rate=?, score=?, grade=?, status=?, points=?, detail=? WHERE id=?",
                        (rate, score, grade, status, points, json.dumps(d), row["id"]))


# ---------------------------------------------------------------- network and charters
STATION_CITY = {}
for _r in ROUTES.values():
    for _a in (_r["origin"], _r["destination"]):
        STATION_CITY[_a["icao"]] = _a["city"]


def airport_obj(icao):
    a = AIRPORTS.get((icao or "").strip().upper())
    if not a:
        return None
    return {"icao": a["icao"], "name": a["name"], "city": STATION_CITY.get(a["icao"], a["city"]), "country": a["country"], "lat": a["lat"],
            "lon": a["lon"], "rwy_ft": a["rwy_ft"], "elev_ft": a["elev_ft"]}


def resolve_mission(body):
    booked = load_booking()
    if booked and booked['mission'].get('training') and body.get('mission_id') == booked['mission']['id']:
        return booked['mission']
    if body.get('training') is not None:
        return va.training.resolve(va, body['training'])
    if body.get("charter"):
        return build_charter(body["charter"])[0]
    m = va.live_mission(body.get("mission_id")) or MISSIONS.get(body.get("mission_id")) or ROUTES.get(body.get("mission_id")) or va.TOUR_LEGS.get(body.get("mission_id"))
    if not m and str(body.get("mission_id", "")).startswith("TR-"):  # a type-rating checkride
        m = va.checkride_mission(va.current_pilot_id(), body.get("mission_id"))
    if not m and body.get("mission_id"):
        m, _st = va.urgent_by_id(body.get("mission_id"))
    if not m and body.get("mission_id"):
        m, _st = va.job_by_id(body.get("mission_id"))
    if not m:
        raise ValueError("Choose a mission, a scheduled route or build a charter first.")
    return m


def build_charter(spec):
    o, d = airport_obj(spec.get("origin")), airport_obj(spec.get("destination"))
    if not o:
        raise ValueError("Choose a departure airport from the list.")
    if not d:
        raise ValueError("Choose an arrival airport from the list.")
    if o["icao"] == d["icao"]:
        raise ValueError("Departure and arrival must be different airports.")
    ac_code = spec.get("aircraft")
    ac = FLEET.get(ac_code)
    if not ac:
        raise ValueError("Choose an aircraft from the fleet.")
    payload = int(num(spec.get("payload_lbs")))
    ferry = str(spec.get("cargo") or "").startswith("Ferry")
    if ferry:
        payload = 0
    elif payload <= 0:
        raise ValueError("Enter the cargo weight in pounds, or choose a ferry flight.")
    if payload > ac["max_payload_lbs"]:
        raise ValueError(f"The {ac['name']} carries up to {ac['max_payload_lbs']:,} lb. Reduce the load or pick a bigger aircraft.")
    prio = spec.get("priority") if spec.get("priority") in ("Standard", "High", "Critical") else "Standard"
    fn = "".join(ch for ch in str(spec.get("flight_number") or "").upper() if ch.isalnum())[:7]
    if not fn:
        fn = f"PAC{8000 + int(time.time() * 1000) % 1000}"
    elif fn.isdigit():
        fn = "PAC" + fn
    cargo = clean_text(spec.get("cargo"), 80) or "General cargo"
    dist = gc_distance_nm(o["lat"], o["lon"], d["lat"], d["lon"])
    block = round(45 + dist / ac["cruise_ktas"] * 60 * 1.05)
    mult = {"Standard": 1.0, "High": 1.15, "Critical": 1.3}[prio]
    reward = int(round((dist * (0.05 if ferry else 0.14) + payload / 1000 * 1.2) * mult * 0.85 / 10) * 10)
    warnings = []
    if dist > ac["range_nm"]:
        warnings.append(f"{dist:,.0f} nm is beyond the {ac['name']}'s typical range of {ac['range_nm']:,} nm. Plan a lighter load or a fuel stop.")
    for a in (o, d):
        if a["rwy_ft"] and a["rwy_ft"] < ac["min_rwy_ft"]:
            warnings.append(f"{a['icao']}'s longest runway is {a['rwy_ft']:,} ft; the {ac['name']} normally needs {ac['min_rwy_ft']:,} ft. Check performance.")
    spec_out = {"origin": o["icao"], "destination": d["icao"], "aircraft": ac_code, "payload_lbs": payload,
                "cargo": cargo, "priority": prio, "flight_number": fn}
    mission = {
        "id": fn, "title": f"{'Ferry' if ferry else 'Charter'} {o['city'] or o['icao']} to {d['city'] or d['icao']}", "category": "Ferry" if ferry else "Charter",
        "priority": prio, "origin": o, "destination": d, "aircraft": [ac_code], "cargo": cargo, "payload_lbs": payload,
        "target_block_min": block, "reward": reward, "distance_nm": round(dist), "charter": spec_out,
        "briefing": (f"Customer charter, {dist:,.0f} nm {o['icao']} to {d['icao']} on the {ac['name']}. "
                     f"{cargo}, {payload:,} lb. Runways: {o['icao']} {o['rwy_ft']:,} ft, {d['icao']} {d['rwy_ft']:,} ft."),
    }
    import charter_customers
    charter_customers.apply(mission, spec)
    return mission, warnings


@app.post("/api/charter/quote")
def charter_quote():
    try:
        m, warnings = build_charter(request.json or {})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"mission": m, "warnings": warnings})


@app.get("/api/airports/search")
def airport_search():
    q = (request.args.get("q") or "").strip().upper()
    if len(q) < 2:
        return jsonify([])
    exact, pre, other = [], [], []
    for a in AIRPORTS.values():
        if a["icao"] == q or a["iata"] == q:
            exact.append(a)
        elif a["icao"].startswith(q):
            pre.append(a)
        elif len(q) >= 3 and (q in a["name"].upper() or q in (a["city"] or "").upper()):
            other.append(a)
    size = {"L": 0, "M": 1, "S": 2}
    pre.sort(key=lambda a: (size[a["size"]], a["icao"]))
    other.sort(key=lambda a: (size[a["size"]], a["icao"]))
    res = (exact + pre + other)[:12]
    return jsonify([{k: a[k] for k in ("icao", "iata", "name", "city", "country", "rwy_ft", "size")} for a in res])


# ---------------------------------------------------------------- fleet
def fleet_stats():
    with db() as con:
        rows = con.execute("SELECT aircraft, COUNT(*) n, SUM(block_min) b, SUM(payload_lbs) c, AVG(landing_rate) l, MAX(filed_at) last "
                           "FROM pireps WHERE demo=0 AND review_status='Accepted' GROUP BY aircraft").fetchall()
    out = {code: {"flights": 0, "block_hours": 0.0, "cargo_lbs": 0, "avg_landing": None, "last_flown": None,
                  "routes": sum(1 for r in ROUTES.values() if code in r["aircraft"])} for code in FLEET}
    for r in rows:
        if r["aircraft"] in out:
            out[r["aircraft"]].update(flights=r["n"], block_hours=round((r["b"] or 0) / 60, 1), cargo_lbs=r["c"] or 0,
                                      avg_landing=round(r["l"]) if r["l"] is not None else None, last_flown=r["last"])
    return out


def save_fleet_custom(code, edits):
    custom = load_json(FLEET_CUSTOM_PATH, {})
    custom.setdefault(code, {}).update(edits)
    save_json(FLEET_CUSTOM_PATH, custom)
    FLEET.setdefault(code, dict(TYPE_DEFAULTS)).update(edits)
    apply_divisions()


def _type_counts():
    with db() as con:
        af = {r[0]: r[1] for r in con.execute("SELECT type, COUNT(*) FROM airframes GROUP BY type")}
        pr = {r[0]: r[1] for r in con.execute("SELECT aircraft, COUNT(*) FROM pireps GROUP BY aircraft")}
    return af, pr


@app.get("/api/staff/fleet-types")
def staff_fleet_types():
    af, pr = _type_counts()
    return jsonify({"types": [{"code": k, **v, "airframes": af.get(k, 0), "pireps": pr.get(k, 0), "base": k in FLEET_BASE_CODES,
                               "unlock_rank_effective": va.type_unlock_rank(k)} for k, v in FLEET.items()],
                    "ranks": [r["name"] for r in va.RANKS], "text_fields": FLEET_TEXT, "num_fields": FLEET_NUM})


@app.post("/api/staff/fleet-types")
def staff_fleet_type_save():
    b = request.json or {}
    code = str(b.get("code") or "").strip().upper()
    is_new = code not in FLEET
    if not re.fullmatch(r"[A-Z0-9]{3,6}", code):
        return jsonify({"error": "The type code needs 3 to 6 letters or digits, for example B744F."}), 400
    edits = {}
    for k in FLEET_TEXT:
        if k in b:
            edits[k] = clean_text(b[k], 1500 if k == "description" else 120)
    for k in FLEET_NUM:
        if k in b and str(b[k]).strip() != "":
            try:
                edits[k] = float(b[k]) if k in ("mach", "tailstrike_pitch") else int(float(b[k]))
            except (TypeError, ValueError):
                return jsonify({"error": f"{k.replace('_', ' ')} must be a number."}), 400
    if edits.get("unlock_rank") and edits["unlock_rank"] not in [r["name"] for r in va.RANKS]:
        edits["unlock_rank"] = ""
    if is_new:
        missing = [k for k in ("name", "icao", "simbrief_type", "max_payload_lbs", "mtow_lbs", "range_nm", "min_rwy_ft", "cruise_ktas")
                   if not edits.get(k)]
        if missing:
            return jsonify({"error": "A new type needs: " + ", ".join(m.replace("_", " ") for m in missing) + "."}), 400
        pl = edits["max_payload_lbs"]
        edits.setdefault("fuel_burn_pph", round(4000 + pl * 0.07))
        edits.setdefault("maint_per_bh", round(1200 + pl * 0.012))
        edits.setdefault("ownership_per_bh", round(1000 + pl * 0.03))
        edits["custom_type"] = True
        edits["retired"] = False
    save_fleet_custom(code, edits)
    return jsonify({"ok": True, "code": code, "type": FLEET[code], "new": is_new})


@app.post("/api/staff/fleet-types/<code>/retire")
def staff_fleet_type_retire(code):
    if code not in FLEET:
        return jsonify({"error": "Unknown aircraft type."}), 404
    retired = bool((request.json or {}).get("retired", True))
    save_fleet_custom(code, {"retired": retired})
    return jsonify({"ok": True, "retired": retired})


@app.delete("/api/staff/fleet-types/<code>")
def staff_fleet_type_delete(code):
    if code not in FLEET:
        return jsonify({"error": "Unknown aircraft type."}), 404
    af, pr = _type_counts()
    if af.get(code):
        return jsonify({"error": f"Remove its {af[code]} airframes in Staff › Airframes first, or retire the type instead."}), 409
    if pr.get(code):
        return jsonify({"error": f"{pr[code]} logbook flights use this type, so it can't be deleted. Retire it instead: it stays in the logbook but can't be booked."}), 409
    custom = load_json(FLEET_CUSTOM_PATH, {})
    if code in FLEET_BASE_CODES:
        custom[code] = {"deleted": True}
    else:
        custom.pop(code, None)
    save_json(FLEET_CUSTOM_PATH, custom)
    FLEET.pop(code, None)
    return jsonify({"ok": True})


@app.get("/api/fleet")
def get_fleet():
    import auth
    import liveries
    return jsonify({"fleet": FLEET, "stats": fleet_stats(), "liveries": liveries.listing(bool(auth.current())),
                    "discord_invite": (va.site().get("discord_invite") or "").strip(),
                    "livery_max_mb": liveries.max_file_bytes() // (1024 * 1024)})


@app.post("/api/fleet/<code>")
def edit_fleet(code):
    if code not in FLEET:
        return jsonify({"error": "Unknown aircraft."}), 404
    body = request.json or {}
    edits = {k: clean_text(body[k], 1500 if k == "description" else 160) for k in ("role", "division", "description", "engines", "crew", "main_deck", "sim_model") if k in body}
    if body.get("sim") in ("MSFS", "X-Plane", "MSFS and X-Plane"):
        edits["sim"] = body["sim"]
    if "registrations" in body:
        regs = body["registrations"] if isinstance(body["registrations"], list) else str(body["registrations"]).replace(",", " ").split()
        edits["registrations"] = [clean_text(r, 12).upper() for r in regs if clean_text(r)][:40]
    save_fleet_custom(code, edits)
    return jsonify(FLEET[code])


@app.post("/api/fleet/<code>/photo")
def fleet_photo(code):
    if code not in FLEET:
        return jsonify({"error": "Unknown aircraft."}), 404
    f = request.files.get("photo")
    if not f or f.mimetype not in PHOTO_EXTS:
        return jsonify({"error": "Choose a PNG, JPEG or WebP image."}), 400
    data = f.read()
    if len(data) > 15 * 1024 * 1024:
        return jsonify({"error": "That image is over 15 MB. Choose a smaller one."}), 400
    FLEET_PHOTO_DIR.mkdir(exist_ok=True)
    for old in FLEET_PHOTO_DIR.glob(f"{code}.*"):
        old.unlink()
    (FLEET_PHOTO_DIR / f"{code}{PHOTO_EXTS[f.mimetype]}").write_bytes(data)
    url = f"/api/fleet/{code}/photo?v={int(time.time())}"
    save_fleet_custom(code, {"photo": url, "thumb": url})
    return jsonify(FLEET[code])


@app.get("/api/fleet/<code>/photo")
def fleet_photo_get(code):
    for f in FLEET_PHOTO_DIR.glob(f"{code}.*") if FLEET_PHOTO_DIR.exists() else []:
        return send_from_directory(FLEET_PHOTO_DIR, f.name, max_age=0)
    return send_from_directory(Path(app.static_folder) / "fleet", f"{code}.jpg")


@app.delete("/api/fleet/<code>/photo")
def fleet_photo_reset(code):
    if code not in FLEET:
        return jsonify({"error": "Unknown aircraft."}), 404
    for old in FLEET_PHOTO_DIR.glob(f"{code}.*") if FLEET_PHOTO_DIR.exists() else []:
        old.unlink()
    save_fleet_custom(code, {"photo": f"/static/fleet/{code}.jpg", "thumb": f"/static/fleet/{code}_thumb.jpg"})
    return jsonify(FLEET[code])


# ---------------------------------------------------------------- profile
PROFILES_DIR = DATA / "profiles"   # every other pilot's profile and photo; the founder's stay in profile.json


def founder_pid():
    return load_json(SETTINGS_PATH, {}).get("pilot_id") or "PAC0001"


def _profile_pid(pid=None):
    pid = str(pid or va.current_pilot_id() or founder_pid()).upper()
    return pid if re.fullmatch(r"[A-Z0-9_-]{1,20}", pid) else founder_pid()


def _pilot_row(pid):
    try:
        with db() as con:
            r = con.execute("SELECT * FROM pilots WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None
    except Exception:
        return None


def load_profile(pid=None):
    """A pilot's profile: the founder's is the airline's public face (profile.json); every other pilot has their own,
    starting from their pilot record."""
    pid = _profile_pid(pid)
    if pid == founder_pid():
        p = load_json(PROFILE_PATH, None)
        if p is None:
            p = json.loads(json.dumps(DEFAULT_PROFILE))
            p["pilot_id"] = pid
        p = dict(p)
        try:
            p["rank"] = va.career(pid)["rank"]
        except Exception:
            pass  # Preserve the last saved label if career data is unavailable.
        return p
    row = _pilot_row(pid) or {}
    p = load_json(PROFILES_DIR / f"{pid}.json", None) or {
        "title": "PAC line pilot", "callsign": "PAGANI", "bio": "", "credentials": [], "type_ratings": [],
        "base": row.get("hub") or "", "secondary_base": "", "photo": "/static/pilot-photo-default.svg",
        "member_since": time.strftime("%Y-%m-%d", time.gmtime(row["joined"])) if row.get("joined") else ""}
    try:
        rank = va.career(pid)["rank"]
    except Exception:
        rank = p.get("rank") or ""
    # who a pilot is and what they're qualified on come from their record, ratings and staff, never from the pilot
    p.update(pilot_id=pid, name=row.get("name") or p.get("name") or pid, rank=rank, callsign=AIRLINE_CALLSIGN,
             title=p.get("title") or "PAC line pilot", base=row.get("hub") or p.get("base") or "",
             member_since=time.strftime("%Y-%m-%d", time.gmtime(row["joined"])) if row.get("joined") else p.get("member_since", ""),
             type_ratings=pilot_type_ratings(pid))
    return p


def with_flair(p):
    """A profile plus what the pilot bought in the PAC shop (patches, crew-badge frame). Never saved into the profile."""
    try:
        import shop
        flair = shop.flair(p.get("pilot_id"))
        import cargo_experience
        con = db()
        try:
            flair["campaign_awards"] = cargo_experience.awards(con, p.get("pilot_id"))
        finally:
            con.close()
        return {**p, "flair": flair}
    except Exception:
        return p


AIRLINE_CALLSIGN = "PAGANI"


def filing_icao(st=None):
    """The three-letter code PAC flights are filed under on VATSIM and IVAO. PAC stays the airline's own prefix on the
    website (PAC9613); on the networks the same flight is PGC9613, spoken "Pagani 9613" (CALLSIGN PAGANI in remarks)."""
    code = str((st or settings()).get("filing_icao") or "").strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else "PGC"


def partner_tail(m, ac):
    """The partner airline's registration for a contract flight: one of its real tails for that type, always the same
    for the same flight and type (the browser picks it the same way). None when PAC has no list for that type."""
    op = (m.get("operator") or {}).get("key")
    regs = ((PARTNERS.get(op) or {}).get("registrations") or {}).get(ac) or []
    if not m.get("contract") or not regs:
        return None
    return regs[sum(ord(ch) for ch in f"{m['id']}|{ac}") % len(regs)]


def site_flight_number(ofp, mission_id):
    """The flight number PAC shows for a booking. A SimBrief plan filed under PAC's network code still shows as PAC."""
    if not (ofp and ofp.get("flight_number")):
        return mission_id
    airline = str(ofp.get("airline") or "").upper()
    if not airline or airline == filing_icao():
        airline = "PAC"
    return f"{airline}{ofp.get('flight_number')}"


def atc_callsign(booking):
    """What the pilot files on VATSIM or IVAO for this booking: a partner's own code, otherwise PAC's network code."""
    m = booking.get("mission") or {}
    digits = "".join(ch for ch in str(booking.get("flight_number") or m.get("id") or "") if ch.isdigit())
    op = m.get("operator") or {}
    return f"{op.get('code') or filing_icao()}{digits}"
RATING_SOURCES = {"rank": "Unlocked by rank", "checkride": "Type checkride", "staff": "Granted by staff", "line checkride": "Line checkride",
                  "flown": "Flown with PAC", "legacy": "Flown with PAC"}


def pilot_type_ratings(pid):
    """A pilot's type ratings as PAC records them: earned on a checkride, granted by staff, or flown before ratings."""
    try:
        rated = va.type_ratings(pid)
        if not settings().get("require_type_ratings"):
            # rank alone qualifies a pilot: the license lists every family their rank has unlocked
            for t in va.career(pid)["unlocked"]:
                rated.setdefault(va.rating_family(t), {"source": "rank", "date": None})
    except Exception:
        return []
    rows = []
    for fam, how in rated.items():
        types = [t for t in va.family_types(fam) if t in FLEET] or [fam]
        lead = FLEET.get(types[0], {})
        rows.append({"type": (fam if len(types) > 1 else lead.get("icao")) or fam, "fleet": types[0] if types[0] in FLEET else "",
                     "name": " / ".join(FLEET[t]["name"] for t in types if t in FLEET) or fam, "role": "Captain",
                     "issued": time.strftime("%Y-%m-%d", time.gmtime(how["date"])) if how.get("date") else "",
                     "prior_hours": 0, "status": "Active",
                     "notes": RATING_SOURCES.get(str(how.get("source") or ""), str(how.get("source") or "").replace("_", " ").capitalize())})
    return sorted(rows, key=lambda r: r["type"])


def save_profile_for(pid, p):
    if pid == founder_pid():
        save_json(PROFILE_PATH, p)
    else:
        PROFILES_DIR.mkdir(exist_ok=True)
        save_json(PROFILES_DIR / f"{pid}.json", p)


def _photo_glob(pid):
    return DATA.glob("pilot_photo.*") if pid == founder_pid() else PROFILES_DIR.glob(f"{pid}-photo.*")


def clean_text(v, n=300):
    return str(v or "").strip()[:n]


def sanitize_profile(body):
    out = {k: clean_text(body.get(k), 2000 if k == "bio" else 200) for k in
           ("rank", "name", "title", "pilot_id", "callsign", "base", "secondary_base", "member_since", "bio", "photo")}
    out["credentials"] = [{k: clean_text(c.get(k)) for k in ("label", "value", "detail", "expires")}
                          for c in (body.get("credentials") or [])[:40] if clean_text(c.get("label")) or clean_text(c.get("value"))]
    out["type_ratings"] = []
    for r in (body.get("type_ratings") or [])[:40]:
        if not clean_text(r.get("type")) and not clean_text(r.get("name")):
            continue
        row = {k: clean_text(r.get(k)) for k in ("type", "fleet", "name", "role", "issued", "status", "notes")}
        row["prior_hours"] = max(0.0, num(r.get("prior_hours")))
        out["type_ratings"].append(row)
    return out


def profile_stats(pid=None, recent_n=5):
    now = time.time()
    with db() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, aircraft, block_min, flight_min, landing_rate, score, status, filed_at, payload_lbs, points, distance_nm, "
            "flight_number, mission_title, dep, arr, grade, "
            "CASE WHEN category IN ('Checkride', 'Type checkride') THEN COALESCE(json_extract(detail, '$.type_checkride.passed'), "
            "json_extract(detail, '$.checkride.passed'), 1) ELSE 1 END AS ck_ok "
            "FROM pireps WHERE demo=0 AND review_status='Accepted' AND pilot_id=? ORDER BY filed_at DESC", (pid or va.current_pilot_id(),))]
    by_ac = {}
    for r in rows:
        if not r.pop("ck_ok", 1):      # a checkride that didn't pass: no hours or landings on the rating (as for rank and pay)
            continue
        a = by_ac.setdefault(r["aircraft"], {"flights": 0, "block_hours": 0.0, "landings_90d": 0, "last_flown": None})
        a["flights"] += 1
        a["block_hours"] += (r["block_min"] or 0) / 60
        a["last_flown"] = max(a["last_flown"] or 0, r["filed_at"])
        if now - r["filed_at"] <= 90 * 86400 and r["status"] != "Failed":
            a["landings_90d"] += 1
    for a in by_ac.values():
        a["block_hours"] = round(a["block_hours"], 1)
    ok = [r for r in rows if r["status"] != "Failed"]
    totals = {
        "flights": len(rows), "block_hours": round(sum(r["block_min"] or 0 for r in rows) / 60, 1),
        "distance_nm": round(sum(r["distance_nm"] or 0 for r in rows)),
        "cargo_lbs": sum(r["payload_lbs"] or 0 for r in ok), "points": sum(r["points"] or 0 for r in rows),
        "avg_landing": round(sum(r["landing_rate"] or 0 for r in rows) / len(rows)) if rows else None,
        "avg_score": round(sum(r["score"] for r in rows) / len(rows)) if rows else None,
        "on_time": sum(1 for r in rows if r["status"] == "Delivered"),
        "best_landing": max((r["landing_rate"] for r in rows if r["landing_rate"] is not None), default=None),
    }
    recent = [{k: r[k] for k in ("id", "flight_number", "mission_title", "dep", "arr", "aircraft", "block_min", "grade", "filed_at",
                                 "landing_rate", "score")} for r in rows[:recent_n]]
    return {"by_aircraft": by_ac, "totals": totals, "recent": recent}


def with_rating_families(p):
    """Each type rating covers a whole family (one rating flies the 757 and the 767), so the license counts hours and
    landings on every type in it, not just the first."""
    rows = []
    for r in p.get("type_ratings") or []:
        fleets = [r["fleet"]] if r.get("fleet") else []
        if r.get("fleet") and " / " in (r.get("name") or ""):   # a family row ("Boeing 757-200F / Boeing 767-300F"); a single-type row stays as it is
            fleets = [t for t in va.family_types(va.rating_family(r["fleet"])) if t in FLEET] or fleets
        rows.append({**r, "fleets": fleets})
    return {**p, "type_ratings": rows}


@app.get("/api/profile")
def get_profile():
    return jsonify({"profile": with_rating_families(with_flair(load_profile())), "stats": profile_stats()})


@app.post("/api/profile")
def save_profile():
    """Pilots may correct their own roster name and personal profile; ID, rank and ratings remain protected.
    The founder also manages the airline's public profile fields."""
    pid = _profile_pid()
    p = sanitize_profile(request.json or {})
    old = load_profile(pid)
    if not p["photo"]:
        p["photo"] = old.get("photo") or DEFAULT_PROFILE["photo"]
    if pid != founder_pid():
        # A signed-in pilot may correct their own roster name. Identity, rank, ratings and base remain staff-controlled.
        name = " ".join(p["name"].split())
        if not 2 <= len(name) <= 80 or any(ord(ch) < 32 or ch in "<>&" for ch in name):
            return jsonify({"error": "Enter a full name of 2 to 80 characters without symbols <, > or &."}), 400
        with db() as con:
            if not con.execute("SELECT 1 FROM pilots WHERE id=?", (pid,)).fetchone():
                return jsonify({"error": "Your pilot record was not found."}), 404
            con.execute("UPDATE pilots SET name=? WHERE id=?", (name, pid))
        p = {**old, "name": name, "bio": p["bio"], "secondary_base": p["secondary_base"], "photo": p["photo"]}
        save_profile_for(pid, p)
        p = load_profile(pid)
        return jsonify({"profile": with_rating_families(with_flair(p)), "settings": public_settings(), "stats": profile_stats()})
    if not p["name"]:
        return jsonify({"error": "Your name can't be empty."}), 400
    p["pilot_id"] = pid                      # the founder's ID is changed in Staff, never from the profile
    p["callsign"] = AIRLINE_CALLSIGN
    p["rank"] = old.get("rank", "")  # Rank changes belong in the staff career controls.
    save_profile_for(pid, p)
    st = settings()
    st["pilot_name"] = f"{p['rank']} {p['name']}".strip() if p["rank"] else p["name"]
    save_json(SETTINGS_PATH, st)
    return jsonify({"profile": with_rating_families(with_flair(p)), "settings": public_settings(st), "stats": profile_stats()})


# ---------------------------------------------------------------- the pilots: roster and other pilots' profiles
# For signed-in PAC pilots only (like other pilots' photos). Nothing private is shown: no email, Discord, VATSIM or
# IVAO details, wallet or settings; just what a crew room would know about a colleague.
@app.get("/api/pilots")
def pilots_roster():
    with db() as con:
        rows = [dict(r) for r in con.execute("SELECT id, name, hub, status, joined, staff, country, location FROM pilots ORDER BY id")]
        last = {r[0]: r[1] for r in con.execute(
            "SELECT pilot_id, MAX(filed_at) FROM pireps WHERE demo=0 AND review_status='Accepted' GROUP BY pilot_id")}
    out = []
    for r in rows:
        car = va.career(r["id"])
        prof = load_profile(r["id"])
        out.append({"pilot_id": r["id"], "name": r["name"], "rank": car["rank"], "hours": car["hours"], "flights": car["flights"],
                    "avg_score": car.get("avg_score"), "base": r["hub"] or "", "location": r["location"] or va.pilot_location(r["id"]),
                    "country": r["country"] or "", "status": r["status"] or "Active", "staff": bool(r["staff"]),
                    "joined": r["joined"], "last_flight": last.get(r["id"]), "photo": prof.get("photo") or "/static/pilot-photo-default.svg"})
    return jsonify({"pilots": out})


@app.get("/api/pilots/<pid>")
def pilot_page(pid):
    pid = str(pid or "").upper()
    with db() as con:
        row = con.execute("SELECT id, name, hub, status, joined, staff, country, location FROM pilots WHERE id=?", (pid,)).fetchone()
    if not row:
        return jsonify({"error": "There's no PAC pilot with that ID."}), 404
    row = dict(row)
    prof = with_rating_families(with_flair(load_profile(pid)))
    keep = ("pilot_id", "name", "rank", "title", "callsign", "base", "secondary_base", "member_since", "bio", "photo",
            "credentials", "type_ratings", "flair")
    car = va.career(pid)
    st = va.stats(pid)
    return jsonify({
        "profile": {k: prof.get(k) for k in keep},
        "career": {k: car.get(k) for k in ("rank", "rank_index", "appointed", "hours", "pac_hours", "transfer_hours", "avg_score",
                                           "flights", "checkride", "next")},
        "stats": profile_stats(pid, recent_n=10),
        "map": {"routes": st["routes"], "airports": st["airports"]},
        "collection": {k: st["collection"][k] for k in ("airports", "countries", "continents")},
        "awards": [b for b in va.badges(pid) if b.get("earned")],
        "status": row["status"] or "Active", "staff": bool(row["staff"]), "country": row["country"] or "",
        "location": row["location"] or va.pilot_location(pid), "joined": row["joined"],
        "you": pid == va.current_pilot_id(),
    })


@app.post("/api/profile/photo")
def upload_photo():
    f = request.files.get("photo")
    if not f or f.mimetype not in PHOTO_EXTS:
        return jsonify({"error": "Choose a PNG, JPEG or WebP image."}), 400
    data = f.read()
    if len(data) > 8 * 1024 * 1024:
        return jsonify({"error": "That image is over 8 MB. Choose a smaller one."}), 400
    pid = _profile_pid()
    for old in list(_photo_glob(pid)):
        old.unlink()
    if pid == founder_pid():
        (DATA / f"pilot_photo{PHOTO_EXTS[f.mimetype]}").write_bytes(data)
        url = f"/api/profile/photo?v={int(time.time())}"
    else:
        PROFILES_DIR.mkdir(exist_ok=True)
        (PROFILES_DIR / f"{pid}-photo{PHOTO_EXTS[f.mimetype]}").write_bytes(data)
        url = f"/api/profile/photo?pilot={pid}&v={int(time.time())}"
    p = load_profile(pid)
    p["photo"] = url
    save_profile_for(pid, p)
    return jsonify({"photo": p["photo"]})


@app.get("/api/profile/photo")
def serve_photo():
    """The founder's photo is public (it's on the home page); other pilots' photos are for members."""
    import auth
    pid = str(request.args.get("pilot") or "").upper() or founder_pid()
    if pid != founder_pid():
        if not auth.current():
            return jsonify({"error": "Please sign in.", "signin": True}), 401
        pid = _profile_pid(pid)
    for f in _photo_glob(pid):
        return send_from_directory(f.parent, f.name, max_age=0)
    if pid != founder_pid():
        return send_from_directory(app.static_folder, "pilot-photo-default.svg")
    return send_from_directory(app.static_folder, "pilot-photo.jpg")


@app.delete("/api/profile/photo")
def reset_photo():
    pid = _profile_pid()
    for old in list(_photo_glob(pid)):
        old.unlink()
    p = load_profile(pid)
    p["photo"] = DEFAULT_PROFILE["photo"] if pid == founder_pid() else "/static/pilot-photo-default.svg"
    save_profile_for(pid, p)
    return jsonify({"photo": p["photo"]})


# ---------------------------------------------------------------- routes
@app.after_request
def no_stale_app_files(resp):
    if request.path in ("/", "/dispatch") or request.path.endswith(("/app.js", "/app.css", "/theme-loadsheet.css", "index.html", "dispatch.html")):
        resp.headers["Cache-Control"] = "no-cache"  # always revalidate, so an update shows up on the next load
    elif request.path.startswith("/static/") and request.args.get("v") and resp.status_code == 200:
        # versioned files (style.css?v=20261102): every change gets a new ?v=, so browsers can keep them for a week
        # instead of asking the server about each one on every page load
        resp.headers["Cache-Control"] = "public, max-age=604800"
    elif request.path.startswith(("/static/fonts/", "/static/ranks/", "/static/partners/", "/static/vendor/")) and resp.status_code == 200:
        resp.headers["Cache-Control"] = "public, max-age=604800"   # fonts, map library, rank insignia and partner logos rarely change
    return resp


@app.errorhandler(Exception)
def api_error(e):
    from werkzeug.exceptions import HTTPException
    import traceback
    if isinstance(e, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"error": f"{e.code} {e.name}: {request.path}"}), e.code
        return e
    traceback.print_exc()
    msg = f"Server error in {request.path}: {type(e).__name__}: {e}. Details are in the ACARS console window."
    if request.path.startswith("/api/"):
        return jsonify({"error": msg}), 500
    return msg, 500


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


ACADEMY_DIR = Path(app.static_folder) / "academy"


@app.get("/academy")
def academy_redirect():
    """PAC Academy: the 737-800 lessons and PAC's startup flow (a public page)."""
    from flask import redirect
    return redirect("/academy/", code=301)


@app.get("/static/academy/")
def academy_old_address():
    """The Academy's first address: forward to the real one."""
    from flask import redirect
    return redirect("/academy/", code=301)


@app.get("/academy/")
def academy_page():
    return send_from_directory(ACADEMY_DIR, "index.html")


@app.get("/academy/<path:name>")
def academy_file(name):
    return send_from_directory(ACADEMY_DIR, name, max_age=86400)


SITE_URL = "https://pac-va.com"


@app.get("/robots.txt")
def robots_txt():
    """Search engines may read the public pages; the API and dispatch paperwork are not for indexing."""
    body = f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /dispatch\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    return app.response_class(body, mimetype="text/plain", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sitemap.xml")
def sitemap_xml():
    today = time.strftime("%Y-%m-%d", time.gmtime())
    urls = [("/", "daily", "1.0"), ("/academy/", "monthly", "0.8")]
    items = "".join(f"<url><loc>{SITE_URL}{u}</loc><lastmod>{today}</lastmod><changefreq>{c}</changefreq><priority>{pr}</priority></url>"
                    for u, c, pr in urls)
    body = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>\n'
    return app.response_class(body, mimetype="application/xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/bootstrap")
def bootstrap():
    import auth
    if not auth.current():  # visitors: what the public pages need, nothing personal
        prof = load_profile(founder_pid())
        return jsonify({"guest": True, "missions": [], "partners": PARTNERS, "fleet": FLEET, "divisions": DIVISIONS, "settings": {}, "phases": PHASES, "booking": None,
                        "routes": [], "cargo_types": CARGO_TYPES, "airframes": va.airframes(), "tour_legs": [], "tours": va.TOURS,
                        "featured": va.featured_routes(), "active_events": va.active_events(), "career": None, "ranks": va.ranks_effective(),
                        "checkride_id": va.CHECKRIDE_ID, "tour_progress": None, "rotations": va.ROTATIONS, "rotation_progress": None, "live_public": bool(settings().get("live_map_public")),
                        "profile": {k: prof.get(k) for k in ("name", "first_name", "last_name", "title", "photo", "pilot_id", "bio", "rank") if k in prof}})
    pid = va.current_pilot_id()
    failed = []

    def part(name, fn, default):
        """One section of the start-up data. If it fails, log why and send the rest, so one bad record can't blank the site."""
        try:
            return fn()
        except Exception:
            import traceback
            print(f"bootstrap: {name} failed for {pid}\n{traceback.format_exc()}", flush=True)
            failed.append(name)
            return default

    out = {"ofp_watch": part("ofp_watch", ofp_watch_status, None), "missions": part("missions", va.mission_board, []),
           "partners": PARTNERS, "fleet": FLEET, "divisions": DIVISIONS, "settings": public_settings(), "phases": PHASES,
           "booking": part("booking", load_booking, None), "routes": list(ROUTES.values()), "cargo_types": CARGO_TYPES,
           "profile": part("profile", lambda: with_rating_families(with_flair(load_profile())), {}), "airframes": part("airframes", va.airframes, []),
           "tour_legs": list(va.TOUR_LEGS.values()), "tours": va.TOURS, "featured": part("featured", va.featured_routes, []),
           "active_events": part("events", va.active_events, []), "career": part("career", lambda: va.career(pid), {}),
           "ranks": va.ranks_effective(), "checkride_id": va.CHECKRIDE_ID,
           "tour_progress": part("tours", lambda: va.tour_progress(pid), {}),
           "rotations": va.ROTATIONS, "rotation_progress": part("rotations", lambda: va.rotation_progress(pid), {})}
    if failed:
        out["partial"] = failed
    return jsonify(out)


STAFF_ONLY_SETTINGS = ("discord_webhook", "discord_departures", "discord_arrivals",  # changed through their own staff pages only
                       "mail_from", "mail_from_name", "mail_reply_to", "smtp_host", "smtp_port", "smtp_security",
                       "smtp_user", "smtp_pass", "mail_auto_welcome", "mail_auto_decline")


@app.post("/api/settings")
def save_settings():
    """A pilot's own settings go on their pilot record. The airline's settings (rules, economics, the founder's
    pilot ID…) are for staff only."""
    import auth
    b = request.json or {}
    pid = va.current_pilot_id()
    airline = [k for k in DEFAULT_SETTINGS if k in b and k not in PERSONAL_SETTINGS and k not in STAFF_ONLY_SETTINGS]
    if airline and not auth.is_staff():
        return jsonify({"error": "That's for staff only."}), 403
    with db() as con:
        _, prefs = _pilot_prefs(pid, con)
        for k in PERSONAL_SETTINGS:
            if k == "simbrief_username" or k not in b:
                continue
            v = clean_text(b[k], 60)
            if k in ("vatsim_cid", "ivao_vid", "simbrief_userid"):
                v = re.sub(r"\D", "", v)
            if k == "map_style" and v not in ("dark", "light", "street", "satellite", "offline"):
                v = "dark"
            prefs[k] = v
        con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(prefs), pid))
        if "simbrief_username" in b:      # SimBrief is per pilot, so it lives on the pilot's record
            con.execute("UPDATE pilots SET simbrief=? WHERE id=?", (clean_text(b["simbrief_username"], 60), pid))
    if airline:
        s = settings()
        for k in airline:
            if k in ("si_va_key", "discord_bot_token") and not str(b[k] or "").strip():
                continue                      # a blank key box means "keep the saved key"
            s[k] = str(b[k]).strip() if k in ("si_va_key", "si_coupon", "si_dispatcher_freq", "discord_bot_token", "discord_guild") else b[k]
        save_json(SETTINGS_PATH, s)
        if PROFILE_PATH.exists() and "pilot_id" in airline:
            p = load_json(PROFILE_PATH, {})
            p["pilot_id"] = s["pilot_id"]
            save_json(PROFILE_PATH, p)
    return jsonify(public_settings())


@app.post("/api/simbrief/apicode")
def simbrief_apicode():
    """Signs one SimBrief API request (SimBrief's own scheme: md5 of the key and the request) so the pilot's browser
    can open SimBrief's generator window. Returns the plan id SimBrief will save it under."""
    import hashlib
    key = simbrief_api_key()
    if not key:
        return jsonify({"error": "One-click OFP generation isn't set up on this site."}), 404
    b = request.json or {}
    orig, dest, typ = (str(b.get(k) or "").strip().upper() for k in ("orig", "dest", "type"))
    out = str(b.get("outputpage") or "")[:200]
    try:
        ts = int(b.get("timestamp"))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing timestamp."}), 400
    if not (re.fullmatch(r"[A-Z0-9]{3,4}", orig) and re.fullmatch(r"[A-Z0-9]{3,4}", dest) and re.fullmatch(r"[A-Z0-9]{2,8}", typ)):
        return jsonify({"error": "Check the departure, arrival and aircraft type."}), 400
    if abs(ts - time.time()) > 3600:
        return jsonify({"error": "Your computer's clock looks wrong. Fix the time and try again."}), 400
    code = hashlib.md5((key + orig + dest + typ + str(ts) + out).encode("utf-8")).hexdigest()
    ofp_id = f"{ts}_{hashlib.md5((orig + dest + typ).encode('utf-8')).hexdigest().upper()[:10]}"
    return jsonify({"apicode": code, "ofp_id": ofp_id})


@app.post("/api/ofp/import")
def import_ofp():
    body = request.json or {}
    try:
        mission = resolve_mission(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        if body.get("raw"):
            text = body["raw"].strip()
            raw = json.loads(text) if text.startswith("{") else xml_to_obj(ET.fromstring(text))
        elif body.get("ofp_id"):      # generated from PAC through the SimBrief API
            raw = fetch_simbrief_ofp_id(body["ofp_id"])
        else:
            raw = fetch_simbrief(simbrief_settings())
        ofp = parse_ofp(raw)
    except (ValueError, ET.ParseError) as e:
        return jsonify({"error": str(e)}), 400
    ac_code = body.get("aircraft")
    if not mission.get("charter") and ofp.get("aircraft_icao"):
        cur = FLEET.get(ac_code)
        if not cur or ofp["aircraft_icao"] not in (cur["icao"], cur["simbrief_type"]):
            # the plan is for another type this flight allows (e.g. the 767 on the 757/767 checkride): use that one
            match = next((a for a in mission.get("aircraft") or [] if FLEET.get(a) and ofp["aircraft_icao"] in (FLEET[a]["icao"], FLEET[a]["simbrief_type"])), None)
            if match:
                ac_code = match
    errors, warnings = validate_ofp(ofp, mission, ac_code)
    return jsonify({"ofp": ofp, "errors": errors, "warnings": warnings, "aircraft": ac_code})


@app.post("/api/booking")
@releases.serialized
def create_booking():
    if load_booking():
        return jsonify({"error": "You already hold a mission. Cancel it or fly it before requesting another."}), 409
    body = request.json or {}
    if body.get('training') is not None:
        try:return jsonify(va.training.book(va, body['training'], body.get('ofp'), globals()))
        except ValueError as e:return jsonify({'error':str(e)}),409
    try:
        m = resolve_mission(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    ac = body.get("aircraft")
    if m.get("charter"):
        ac = m["aircraft"][0]
    if ac not in FLEET:
        return jsonify({"error": "Pick an aircraft from the fleet."}), 400
    if FLEET[ac].get("retired"):
        return jsonify({"error": f"The {FLEET[ac]['name']} has been retired from the PAC fleet."}), 400
    err, frame = va.check_booking(m, ac, (body.get("airframe") or "").upper() or None, settings())
    if err:
        return jsonify({"error": err}), 400
    ofp = body.get("ofp")
    fn = site_flight_number(ofp, m["id"])
    booking = {"mission": m, "aircraft": ac, "ofp": ofp, "flight_number": fn, "requested_at": time.time(),
               "airframe": frame["reg"] if frame else None, "partner_reg": partner_tail(m, ac)}
    # the preliminary load sheet the pilot reviewed: same units, positions and waybills on the release
    booking["manifest_seed"] = manifest_seed_ok(body.get("manifest_seed")) or prelim_seed(m, ac)
    booking["dispatch"] = dispatch.generate(booking, FLEET, dispatch_pilot())
    # PAC stands at PAC's hubs: where to start, and where to expect to park on arrival
    _reg = booking.get("airframe")
    booking["dep_stand"] = va.assign_stand(m["origin"]["icao"], ac, fn, "dep", _reg)
    booking["arr_stand"] = va.assign_stand(m["destination"]["icao"], ac, fn, "arr", _reg)
    if m.get("urgent"):
        va.set_urgent_status(m["id"], "booked")
    if m.get("job"):
        va.set_job_status(m["id"], "booked")
    if m.get("live"):
        va.set_live_status(m["id"], "booked")
    save_booking(booking)
    start_ofp_watch(booking)
    return jsonify(booking)


RANK_ABBR = {"Captain": "Capt.", "First Officer": "F/O", "Senior First Officer": "SFO", "Second Officer": "S/O"}


def dispatch_pilot():
    prof = load_profile(va.current_pilot_id())
    car = va.career(va.current_pilot_id())
    return {"name": " ".join(x for x in [RANK_ABBR.get(prof.get("rank"), prof.get("rank", "")), prof.get("name", "")] if x),
            "id": va.current_pilot_id(), "rank": car["rank"]}


import image_delivery
image_delivery.register(app, DATA, FLEET_PHOTO_DIR, FLEET)
import partner_photos  # noqa: E402  (Wikimedia Commons photos of partner aircraft for landing cards, credited)
PARTNER_PHOTOS = partner_photos.register(app, DATA, PARTNERS, FLEET)

@app.get("/gallery/<path:name>")
def gallery_file(name):
    return send_from_directory(DATA / "gallery", name, max_age=86400)


@app.get("/dispatch")
def dispatch_page():
    return send_from_directory(app.static_folder, "dispatch.html")


@app.get("/api/dispatch")
@releases.serialized
def dispatch_current():
    booking = load_booking()
    if not booking:
        return jsonify({"error": "No flight is booked. Request a flight from the mission board first."}), 404
    if not booking.get("dispatch"):
        booking["legacy_release"] = True
        booking["dispatch"] = dispatch.generate(booking, FLEET, dispatch_pilot())
        save_booking(booking)
    d = dict(booking["dispatch"])
    d["defects"] = va.open_items(booking["airframe"]) if booking.get("airframe") else []
    d["paper"] = dispatch.paperwork(d, FLEET, booking, va.active_notams(), va.career(va.current_pilot_id())["rank"], AIRPORTS,
                                    dow_override=(learned_dow(booking["aircraft"]) or {}).get("dow"))
    if releases.valid_signature(booking):
        frozen_paper = (booking["dispatch"].get("signed_snapshot") or {}).get("paper")
        if frozen_paper:
            d["paper"] = __import__("copy").deepcopy(frozen_paper)
    d["paper"]["atc_callsign"] = atc_callsign(booking)
    d["navlog"] = (booking.get("ofp") or {}).get("route_points") or []  # SimBrief waypoints, for the navigation log
    d["dep_stand"], d["arr_stand"] = booking.get("dep_stand"), booking.get("arr_stand")
    d["simbrief_request_id"] = (booking.get("ofp") or {}).get("request_id") or ""      # for Navigraph Charts
    ac = FLEET.get(booking["aircraft"], {})
    d["perf"] = {"burn_pph": ac.get("fuel_burn_pph"), "ktas": ac.get("cruise_ktas")}
    d["signed"] = booking.get("signed") if releases.valid_signature(booking) else None
    d["revision"] = releases.revision(booking)
    d["requested_at"] = booking.get("requested_at")
    d["release_amended"] = bool(booking.get("release_amended"))
    d["signature_required"] = signature_required(booking)
    return jsonify(d)


@app.get('/load-planner')
def load_planner_page():
    return send_from_directory(app.static_folder, 'load-planner.html')


@app.get('/load-planner-727')
def load_planner_727_page():
    return send_from_directory(app.static_folder, 'load-planner-727.html')


@app.route('/api/load-plan', methods=['GET', 'POST'])
@releases.serialized
def load_plan_api():
    import load_planner
    booking = load_booking()
    if not booking:
        return jsonify(error='Book a supported freighter flight first.'), 404
    if booking.get('aircraft') not in ('B738F', 'B722F'):
        return jsonify(error='This planner supports B738F and B722F flights only.'), 400
    if not booking.get('dispatch'):
        return jsonify(error='Open your dispatch release first.'), 409
    changed = False
    if request.method == 'POST':
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error='A load plan is required.'), 400
        if releases.started(booking) or remote_active():
            return jsonify(error='Tracking has started. Load planning is locked.'), 409
        if body.get('requested_at') != booking.get('requested_at') or body.get('revision') != releases.revision(booking):
            return jsonify(error='Your release changed. Reload this page before editing.'), 409
        try:
            updated = load_planner.rearrange(booking, body.get('assignments'))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if updated is not None:
            booking['dispatch'] = updated
            releases.invalidate(booking)
            save_booking(booking)
            changed = True
    result = load_planner.describe(booking, releases.revision(booking))
    result['signed'] = releases.valid_signature(booking)
    result['changed'] = changed
    response = jsonify(result)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def signature_required(booking):
    """New releases (with shipments) need the captain's signature before ACARS starts, while the rule is on."""
    return bool(settings().get("require_release_signature", True)) and not booking.get("legacy_release") and (booking.get("dispatch") or {}).get("version", 1) >= 2


def void_signature(booking):
    releases.invalidate(booking)


@app.post("/api/dispatch/sign")
@releases.serialized
def dispatch_sign():
    booking = load_booking()
    if not booking:
        return jsonify({"error": "No flight is booked."}), 404
    error, code = releases.sign(booking, request.get_json(silent=True), dispatch_pilot())
    if error:
        return jsonify({"error": error}), code
    booking["dispatch"]["signed_snapshot"]["paper"] = dispatch.paperwork(booking["dispatch"], FLEET, booking, va.active_notams(), va.career(va.current_pilot_id())["rank"], AIRPORTS,
                                                                         dow_override=(learned_dow(booking["aircraft"]) or {}).get("dow"))
    save_booking(booking)
    response = jsonify({"ok": True, "signed": booking["signed"]})
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@app.get("/api/dispatch/pirep/<int:pid>")
def dispatch_pirep(pid):
    with db() as con:
        r = con.execute("SELECT detail FROM pireps WHERE id=?", (pid,)).fetchone()
    d = json.loads(r["detail"] or "{}") if r else {}
    if not d.get("dispatch"):
        return jsonify({"error": "This flight was filed before dispatch paperwork existed."}), 404
    out = dict(d["dispatch"])
    frozen = out.get("signed_snapshot") or {}
    out["paper"] = frozen.get("paper") or dispatch.paperwork(out, FLEET, None, [], d.get("pilot_rank"), AIRPORTS)
    out["navlog"] = (d.get("ofp") or {}).get("route_points") or []
    ac = FLEET.get(out.get("aircraft"), {})
    out["perf"] = {"burn_pph": ac.get("fuel_burn_pph"), "ktas": ac.get("cruise_ktas")}
    return jsonify(out)


@app.delete("/api/booking")
@releases.serialized
def cancel_booking():
    stop_tracking()
    _b = load_booking() or {}
    state.update(remote=None, remote_status=None)
    clear_checkpoint()
    va.release_airframe(_b.get("airframe"))
    if (_b.get("mission") or {}).get("job"):
        va.set_job_status(_b["mission"]["id"], "open")
    if (_b.get("mission") or {}).get("live"):
        va.set_live_status(_b["mission"]["id"], "open" if time.time() < (_b["mission"].get("expires") or 0) else "expired")
    if (_b.get("mission") or {}).get("urgent"):
        _um, _st = va.urgent_by_id(_b["mission"]["id"])
        va.set_urgent_status(_b["mission"]["id"], "open" if _um and time.time() < _um["expires"] else "expired")
    clear_booking()
    clear_flight_state()
    state["recorder"] = None
    return jsonify({"ok": True})


# ---------------------------------------------------------------- bookings (one per pilot)
def _booking_pid(pid=None):
    return pid or va.current_pilot_id()


def load_booking(pid=None):
    """The flight this pilot has booked, or None."""
    try:
        with db() as con:
            r = con.execute("SELECT data FROM bookings WHERE pilot_id=?", (_booking_pid(pid),)).fetchone()
        return json.loads(r["data"]) if r else None
    except Exception:
        return None


def save_booking(booking, pid=None):
    pid = _booking_pid(pid)
    with db() as con:
        con.execute("INSERT OR REPLACE INTO bookings (pilot_id, data, requested_at) VALUES (?,?,?)",
                    (pid, json.dumps(booking), booking.get("requested_at") or time.time()))
    if "SI" in globals():
        SI.notify(pid, "flight booked or changed")   # the pilot's SayIntentions crew learn about it


def clear_booking(pid=None):
    pid = _booking_pid(pid)
    with db() as con:
        con.execute("DELETE FROM bookings WHERE pilot_id=?", (pid,))
    if "SI" in globals():
        SI.notify(pid, "flight finished or canceled")


def all_bookings():
    """Every pilot's booked flight: [(pilot_id, booking)]. Used by the staff overview and the live map."""
    with db() as con:
        return [(r["pilot_id"], json.loads(r["data"])) for r in con.execute("SELECT pilot_id, data FROM bookings")]


def migrate_booking_file():
    """PAC used to keep one booking for the whole site. Move it to the pilot who made it, once."""
    if not BOOKING_PATH.exists():
        return
    b = load_json(BOOKING_PATH, None)
    if b:
        pid = b.get("pilot_id") or settings().get("pilot_id") or "PAC0001"
        with db() as con:
            if not con.execute("SELECT 1 FROM bookings WHERE pilot_id=?", (pid,)).fetchone():
                con.execute("INSERT INTO bookings (pilot_id, data, requested_at) VALUES (?,?,?)",
                            (pid, json.dumps(b), b.get("requested_at") or time.time()))
        print(f"  Moved the booked flight {b.get('flight_number', '')} to {pid}.")
    BOOKING_PATH.rename(BOOKING_PATH.with_suffix(".json.moved"))


def remote_active():
    """A flight is being tracked by the PAC ACARS app (not yet handed over for filing)."""
    return bool(state.get("remote"))


def stop_tracking():
    """Tracking runs in the PAC ACARS app; nothing runs on the website any more."""
    state["thread"] = None


def flight_state_path(pid=None):
    """Each pilot's in-progress flight is kept separately, so a restart resumes everyone's."""
    d = DATA / "flights"
    d.mkdir(exist_ok=True)
    return d / f"{re.sub(r'[^A-Za-z0-9_-]', '_', pid or va.current_pilot_id())}.pkl"


def save_flight_state(rec, pid=None):
    """Keeps an in-progress flight on disk so a server or sim restart can resume it."""
    try:
        path = flight_state_path(pid)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump({"recorder": rec, "source": session(pid).get("source_name")}, fh)
        os.replace(tmp, path)
    except Exception as e:
        print("Could not save flight state:", e)


def clear_flight_state(pid=None):
    flight_state_path(pid).unlink(missing_ok=True)


BACKUP_DIR = DATA / "backups"
BACKUP_KEEP = 14


def backup_data(reason="startup"):
    """Copies the logbook database (safely, with SQLite's backup API) and the settings files into data/backups."""
    import sqlite3 as _sq
    if not DB_PATH.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"{stamp}-{reason}"
    dest.mkdir(parents=True, exist_ok=True)
    src = _sq.connect(DB_PATH)
    dst = _sq.connect(dest / "logbook.db")
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    for f in ("profile.json", "settings.json", "fleet_custom.json", "site.json", "booking.json", "secret_key", "stand_positions.json",
              "liveries.json"):
        if (DATA / f).exists():
            shutil.copy2(DATA / f, dest / f)
    for f in DATA.glob("pilot_photo.*"):
        shutil.copy2(f, dest / f.name)
    for d in ("fleet_photos",):
        if (DATA / d).exists():
            shutil.copytree(DATA / d, dest / d, dirs_exist_ok=True)
    for f in DATA.glob("pilot_photo.*"):
        shutil.copy2(f, dest / f.name)
    olds = sorted([p for p in BACKUP_DIR.iterdir() if p.is_dir()], key=lambda p: p.name)
    for old in olds[:-BACKUP_KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    (dest / "backup-complete.json").write_text(json.dumps({"completed_at": time.time()}), encoding="utf-8")
    return dest


# ---------------------------------------------------------------- full backup and restore (download / upload)
USER_FILES = ("logbook.db", "settings.json", "profile.json", "site.json", "fleet_custom.json", "booking.json", "secret_key",
              "flight_checkpoint.json", "stand_positions.json", "liveries.json")
USER_DIRS = ("fleet_photos", "gallery", "downloads", "flights", "acars-builds", "profiles", "liveries", "network_logos")
BACKUP_MARK = "pac-backup.json"


def full_backup_zip(path):
    """Everything that's yours, in one zip: logbook, settings, profile and photo, home-page text, fleet edits and photos,
    gallery and the sign-in key. The logbook is copied with SQLite's backup API, so it's safe while the site runs."""
    import sqlite3 as _sq
    import tempfile
    import zipfile
    files = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if DB_PATH.exists():
            tmp = Path(tempfile.mkdtemp(dir=str(DATA))) / "logbook.db"
            src, dst = _sq.connect(DB_PATH), _sq.connect(tmp)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            z.write(tmp, "logbook.db")
            files.append("logbook.db")
            shutil.rmtree(tmp.parent, ignore_errors=True)
        for f in USER_FILES[1:]:
            if (DATA / f).exists():
                z.write(DATA / f, f)
                files.append(f)
        for f in DATA.glob("pilot_photo.*"):
            z.write(f, f.name)
            files.append(f.name)
        for d in USER_DIRS:
            for f in (DATA / d).rglob("*") if (DATA / d).exists() else []:
                if f.is_file():
                    z.write(f, f"{d}/{f.relative_to(DATA / d).as_posix()}")
                    files.append(f"{d}/…")
        z.writestr(BACKUP_MARK, json.dumps({"airline": "Pagani Air Cargo", "created": time.time(), "files": sorted(set(files))}, indent=2))
    return path


@app.get("/api/staff/backup/download")
def backup_download():
    import tempfile
    out = Path(tempfile.gettempdir()) / f"PAC-backup-{time.strftime('%Y-%m-%d-%H%M')}.zip"
    full_backup_zip(out)
    return send_file(out, as_attachment=True, download_name=out.name, mimetype="application/zip")


def _safe_member(name):
    """Only the files a backup may contain, and never a path that escapes data/."""
    if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
        return False
    return (name in USER_FILES or name.startswith("pilot_photo.")
            or any(name.startswith(d + "/") and not name.endswith("/") for d in USER_DIRS))


@app.post("/api/staff/backup/restore")
def backup_restore():
    """Puts a full backup back. The current data is backed up first, so a restore can itself be undone."""
    import sqlite3 as _sq
    import tempfile
    import zipfile
    f = request.files.get("backup")
    if not f:
        return jsonify({"error": "Choose a PAC backup file (.zip)."}), 400
    work = DATA / "restore-tmp"              # beside the data, so moving files into place always works
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    tmpdir = work
    zpath = tmpdir / "backup.zip"
    f.save(zpath)
    try:
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            if BACKUP_MARK not in names or "logbook.db" not in names:
                return jsonify({"error": "That isn't a PAC backup (made with Download a full backup)."}), 400
            z.extract("logbook.db", tmpdir)
            try:
                con = _sq.connect(tmpdir / "logbook.db")
                ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and con.execute("SELECT COUNT(*) FROM pilots").fetchone()
                con.close()
            except Exception:
                ok = False
            if not ok:
                return jsonify({"error": "The logbook in this backup is damaged, so nothing was changed."}), 400
            before = backup_data("before-restore")  # the current state, in case you want it back
            for d in USER_DIRS:
                if any(n.startswith(d + "/") for n in names) and (DATA / d).exists():
                    shutil.rmtree(DATA / d)
            if any(n.startswith("pilot_photo.") for n in names):
                for old in DATA.glob("pilot_photo.*"):
                    old.unlink()
            restored = 0
            for n in names:
                if n == "logbook.db" or not _safe_member(n):
                    continue
                target = DATA / n
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored += 1
            # the logbook last, in one step
            shutil.move(str(tmpdir / "logbook.db"), str(DB_PATH))
            restored += 1
    except zipfile.BadZipFile:
        return jsonify({"error": "That file isn't a zip."}), 400
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    app.secret_key = _secret_key() if "_secret_key" in globals() else app.secret_key
    state.update(recorder=None, remote=None, remote_status=None)
    return jsonify({"ok": True, "restored": restored, "safety_backup": before.name if before else None})


def list_backups():
    if not BACKUP_DIR.exists():
        return []
    out = []
    for p in sorted([p for p in BACKUP_DIR.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True):
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        out.append({"name": p.name, "size_kb": round(size / 1024), "path": str(p)})
    return out


@app.get("/api/staff/backups")
def staff_backups():
    return jsonify({"folder": str(BACKUP_DIR), "keep": BACKUP_KEEP, "backups": list_backups()})


@app.post("/api/staff/backups")
def staff_backup_now():
    d = backup_data("manual")
    return jsonify({"ok": bool(d), "folder": str(BACKUP_DIR), "backups": list_backups()})


def restore_flight_state():
    """At startup, bring back every pilot's in-progress flight."""
    if FLIGHT_STATE_PATH.exists():                      # the old single-pilot file
        try:
            pid0 = settings().get("pilot_id") or "PAC0001"
            FLIGHT_STATE_PATH.replace(flight_state_path(pid0))
        except Exception:
            pass
    for pid, booking in all_bookings():
        path = flight_state_path(pid)
        if not path.exists():
            continue
        try:
            with open(path, "rb") as fh:
                saved = pickle.load(fh)
            rec = saved["recorder"]
            if rec.booking.get("requested_at") == booking.get("requested_at"):
                session(pid).update(recorder=rec, source_name=saved.get("source"))
                print(f"  Restored {booking['flight_number']} for {pid}, ready to file.")
            else:
                path.unlink(missing_ok=True)
        except Exception as e:
            print("Could not restore the saved flight:", e)


@app.get("/api/pireps/<int:pid>/approach")
def pirep_approach(pid):
    """The final approach of a filed flight against the ideal 3-degree glidepath (for the approach chart)."""
    import analysis
    with db() as con:
        r = con.execute("SELECT detail, pilot_id FROM pireps WHERE id=?", (pid,)).fetchone()
    if not r:
        return jsonify({"error": "Flight not found."}), 404
    d = json.loads(r["detail"] or "{}")
    ap = analysis.approach_profile(d.get("profile"), d.get("landing_analysis"), gc_distance_nm)
    if not ap:
        return jsonify({"approach": None, "why": "This flight has no approach to chart (no runway was identified, or it didn't land)."})
    return jsonify({"approach": ap})


@app.get("/api/traffic")
def live_traffic():
    """Live VATSIM or IVAO traffic inside the map area (south,west,north,east), for the ACARS map."""
    net = request.args.get("net", "VATSIM").upper()
    if net not in ("VATSIM", "IVAO"):
        return jsonify({"error": "Choose VATSIM or IVAO."}), 400
    try:
        s_, w, n, e = (float(x) for x in request.args.get("bbox", "").split(","))
    except ValueError:
        return jsonify({"error": "Give the map area as south,west,north,east."}), 400
    try:
        planes = online.traffic(net, s_, w, n, e)
    except Exception as ex:
        return jsonify({"error": f"The {net} feed didn't answer ({ex.__class__.__name__}). Try again in a minute."}), 503
    return jsonify({"net": net, "count": len(planes), "planes": planes})


# ---------------------------------------------------------------- email
@app.get("/api/staff/mail")
def staff_mail():
    s_ = settings()
    return jsonify({"mail_from": s_.get("mail_from", ""), "mail_from_name": s_.get("mail_from_name", ""), "mail_reply_to": s_.get("mail_reply_to", ""),
                    "smtp_host": s_.get("smtp_host", ""), "smtp_port": s_.get("smtp_port", 587), "smtp_security": s_.get("smtp_security", "starttls"),
                    "smtp_user": s_.get("smtp_user", ""), "password_set": bool(s_.get("smtp_pass")), "ready": mailer.config_ready(s_),
                    "auto_welcome": s_.get("mail_auto_welcome", True), "auto_decline": s_.get("mail_auto_decline", False), **mailer.status})


@app.post("/api/staff/mail")
def staff_mail_save():
    b = request.json or {}
    st = load_json(SETTINGS_PATH, {})
    if "mail_from" in b:
        addr = str(b["mail_from"] or "").strip()
        if addr and not mailer.valid_email(addr):
            return jsonify({"error": "That isn't a valid email address."}), 400
        st["mail_from"] = addr
        if addr and b.get("autofill", True) and not str(b.get("smtp_host") or "").strip():
            st.update(mailer.guess(addr))        # fill in the server settings for a well-known provider
    for k in ("mail_from_name", "mail_reply_to", "smtp_host", "smtp_user", "smtp_security"):
        if k in b and str(b[k] or "").strip() != "":
            st[k] = str(b[k]).strip()
    if "smtp_port" in b:
        try:
            st["smtp_port"] = max(1, min(65535, int(b["smtp_port"])))
        except (TypeError, ValueError):
            return jsonify({"error": "The port must be a number, usually 587 or 465."}), 400
    if b.get("smtp_pass"):                        # blank means "keep the one already saved"
        st["smtp_pass"] = mailer.clean_password(b["smtp_pass"])   # app passwords are shown with spaces; they aren't part of it
    if b.get("clear_password"):
        st["smtp_pass"] = ""
    for k in ("auto_welcome", "auto_decline"):
        if k in b:
            st[f"mail_{k}"] = bool(b[k])
    save_json(SETTINGS_PATH, st)
    return staff_mail()


@app.post("/api/staff/mail/test")
def staff_mail_test():
    s_ = settings()
    to = str((request.get_json(silent=True) or {}).get("to") or s_.get("mail_from") or "").strip()
    if not mailer.valid_email(to):
        return jsonify({"error": f"{to or 'That'} isn't a valid email address."}), 400
    mailer.status.pop("suggest", None)
    ok, err = mailer.send(s_, to, "PAC email test", "This is a test from Pagani Air Cargo. Your airline's email account is working.\n\nPAC Operations Control",
                          "<p>This is a test from <b>Pagani Air Cargo</b>. Your airline's email account is working.</p><p>PAC Operations Control</p>", wait=True)
    if ok and mailer.status.get("suggest"):       # the fallback port worked: save it as the setting
        sug = mailer.status.pop("suggest")
        save_json(SETTINGS_PATH, {**load_json(SETTINGS_PATH, {}), **sug})
        return jsonify({"ok": True, "to": to, "changed": sug})
    return (jsonify({"ok": True, "to": to}) if ok else (jsonify({"error": err}), 502))


@app.post("/api/staff/mail/diagnose")
def staff_mail_diagnose():
    return jsonify(mailer.diagnose(settings()))


@app.post("/api/staff/letter/send")
def staff_letter_send():
    """Send a letter that staff have on screen (any edits they made are kept)."""
    b = request.json or {}
    to, subject, text = str(b.get("to") or "").strip(), str(b.get("subject") or "").strip(), str(b.get("text") or "")
    if not (to and subject and text):
        return jsonify({"error": "The letter needs an address, a subject and a message."}), 400
    ok, err = mailer.send(settings(), to, subject, text, b.get("html"), wait=True)
    return (jsonify({"ok": True, "to": to}) if ok else (jsonify({"error": err}), 502))


# ---------------------------------------------------------------- Discord
@app.get("/api/staff/discord")
def staff_discord():
    s = settings()
    url = s.get("discord_webhook") or ""
    return jsonify({"webhook_set": bool(url), "webhook_hint": ("…" + url[-6:]) if url else "", "departures": s.get("discord_departures", True),
                    "arrivals": s.get("discord_arrivals", True), **discord_post.status})


@app.post("/api/staff/discord")
def staff_discord_save():
    b = request.json or {}
    st = load_json(SETTINGS_PATH, {})
    if "webhook" in b:
        url = str(b["webhook"] or "").strip()
        if url and not discord_post.valid_webhook(url):
            return jsonify({"error": "That isn't a Discord webhook address. In Discord: channel settings › Integrations › Webhooks › Copy Webhook URL."}), 400
        st["discord_webhook"] = url
    for k in ("departures", "arrivals"):
        if k in b:
            st[f"discord_{k}"] = bool(b[k])
    save_json(SETTINGS_PATH, st)
    return staff_discord()


@app.post("/api/staff/discord/test")
def staff_discord_test():
    url = settings().get("discord_webhook")
    if not url:
        return jsonify({"error": "Add a webhook address first."}), 400
    ok, err = discord_post.post(url, {"content": "✅ Pagani Air Cargo is connected. Departures and arrivals will appear here."}, wait=True)
    return (jsonify({"ok": True}) if ok else (jsonify({"error": err}), 502))


@app.post("/api/discord/share")
def discord_share():
    """Posts a landing card or monthly recap image (a PNG made in the browser) to the Discord channel."""
    import base64
    url = settings().get("discord_webhook")
    if not url:
        return jsonify({"error": "Discord isn't set up. Staff › Site and rules › Discord."}), 400
    b = request.json or {}
    data = str(b.get("image") or "")
    if not data.startswith("data:image/png;base64,"):
        return jsonify({"error": "No image to post."}), 400
    try:
        png = base64.b64decode(data.split(",", 1)[1], validate=True)
    except Exception:
        return jsonify({"error": "The image couldn't be read."}), 400
    if len(png) > 7_500_000:
        return jsonify({"error": "The image is too large for Discord."}), 400
    text = str(b.get("text") or "")[:300]
    name = re.sub(r"[^\w.-]", "_", str(b.get("filename") or "pac.png"))[:60]
    discord_post.post(url, {"content": text}, image=png, filename=name if name.endswith(".png") else name + ".png")
    return jsonify({"ok": True})


# ---------------------------------------------------------------- flight planning helper
CEILING_FL = {"B738F": 370, "B732F": 350, "B733F": 370, "B722F": 350, "A306F": 350, "MD11F": 370, "B752F": 390,
              "B763F": 390, "B77F": 410, "B742F": 350, "B748F": 410}


def initial_course(a, b):
    import math
    la1, la2, dl = math.radians(a["lat"]), math.radians(b["lat"]), math.radians(b["lon"] - a["lon"])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def suggest_cruise(ac_code, dist, course):
    """Highest level for the direction of flight (odd levels eastbound, even westbound; ICAO RVSM),
    no higher than suits the distance and the aircraft's ceiling."""
    ceiling = FLEET.get(ac_code, {}).get("ceiling_fl") or CEILING_FL.get(ac_code, 370)
    cap = min(ceiling, int((100 + dist * 0.6) // 10 * 10))
    east = course < 180
    levels = [fl for fl in range(90, 420, 10) if (fl // 10) % 2 == (1 if east else 0)]
    cands = [fl for fl in levels if fl <= cap] or [levels[0]]
    fl = cands[-1]
    why = (f"{'eastbound' if east else 'westbound'} ({round(course):03d}°): {'odd' if east else 'even'} levels; "
           f"the {FLEET.get(ac_code, {}).get('name', ac_code)} tops out around FL{ceiling}")
    if cap < ceiling:
        why += f"; a {round(dist)} nm leg doesn't need more than about FL{cap}"
    if dist > 3000:
        why += "; plan step climbs as the fuel burns off"
    return fl, why


def runway_ends(icao, min_ft):
    import analysis
    out = []
    for r in analysis.runways(DATA).get(icao, []):
        length = r[10] or 0
        if length < min_ft:
            continue
        out.append({"id": r[0], "hdg": r[3], "length_ft": length})
        out.append({"id": r[5], "hdg": r[8], "length_ft": length})
    return out


def pick_runway(icao, min_ft, wx):
    """The runway end with the most headwind (among those long enough), from the METAR wind."""
    import math
    ends = runway_ends(icao, min_ft)
    if not ends:
        return {"icao": icao, "note": "No runway data for this airport."}
    w = (wx or {}).get("wind") or {}
    spd, wdir = w.get("spd") or 0, w.get("dir")
    if wdir is None or spd < 3:
        best = max(ends, key=lambda e: e["length_ft"])
        return {"icao": icao, "runway": best["id"], "length_ft": best["length_ft"], "wind": wx.get("wind_text") if wx else None,
                "note": "Calm or variable wind: expect the longest runway, or the one in the ATIS." if wx else
                        "No current weather: expect the longest runway, or check the ATIS."}
    def comp(e):
        a = math.radians(wdir - e["hdg"])
        return spd * math.cos(a), spd * math.sin(a)
    best = max(ends, key=lambda e: (round(comp(e)[0]), e["length_ft"]))
    head, cross = comp(best)
    return {"icao": icao, "runway": best["id"], "length_ft": best["length_ft"], "wind": wx.get("wind_text"),
            "headwind_kt": round(head), "crosswind_kt": round(abs(cross)), "cross_from": "right" if cross > 0 else "left",
            "gust_kt": w.get("gust")}


def suggest_alternate(dest, min_ft):
    cands = []
    for icao, a in AIRPORTS.items():
        if icao == dest["icao"] or (a.get("rwy_ft") or 0) < min_ft or a.get("size") not in ("L", "M"):
            continue
        d = gc_distance_nm(dest["lat"], dest["lon"], a["lat"], a["lon"])
        if 40 <= d <= 250:
            cands.append((0 if a.get("size") == "L" else 1, d, icao, a))
    if not cands:
        return None
    _s, d, icao, a = min(cands)
    return {"icao": icao, "name": a["name"], "city": a.get("city"), "distance_nm": round(d), "rwy_ft": a.get("rwy_ft")}


def plan_estimate(m, ac_code):
    """Cruise level, alternate and fuel estimate for a mission on one type (no weather needed)."""
    ac = FLEET[ac_code]
    o, d = m["origin"], m["destination"]
    dist = gc_distance_nm(o["lat"], o["lon"], d["lat"], d["lon"])
    course = initial_course(o, d)
    fl, why = suggest_cruise(ac_code, dist, course)
    altn = suggest_alternate(d, ac.get("min_rwy_ft") or 6000)
    block = economics.planned_block(ac, dist)
    burn = ac.get("fuel_burn_pph") or 5000
    trip = round(burn * max(0.3, (block - 25) / 60) * 1.05)  # climb burns more than cruise
    contingency = round(trip * 0.05)
    altn_fuel = round(burn * ((altn["distance_nm"] if altn else 150) / max(300, ac.get("cruise_ktas") or 450) + 0.25))
    reserve = round(burn * 0.5 * 0.85)  # 30 minutes holding
    taxi = round(burn * 0.08)
    fuel = {"trip": trip, "contingency": contingency, "alternate": altn_fuel, "final_reserve": reserve, "taxi": taxi,
            "block": trip + contingency + altn_fuel + reserve + taxi, "est_block_min": round(block)}
    return {"distance": dist, "course": course, "cruise_fl": fl, "cruise_why": why, "alternate": altn, "fuel": fuel}


def prelim_seed(m, ac_code):
    """Today's preliminary load sheet for this pilot, flight and type. Booking without one uses the same seed,
    so the release always shows the load the flight page showed."""
    return f"PRE|{m['id']}|{ac_code}|{va.current_pilot_id() or 'guest'}|{int(time.time() // 86400)}"


_DOW_CACHE = {}


def learned_dow(code):
    """The dry operating weight of this type in the SimBrief profiles PAC pilots actually fly: the median of
    (zero fuel weight - payload) over the last 25 filed flights with an OFP. Needs 3 flights; cached for 10 minutes.
    Returns {"dow": lb, "flights": n} or None (then the published-limits estimate applies)."""
    hit = _DOW_CACHE.get(code)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    mtow = (FLEET.get(code) or {}).get("mtow_lbs") or 0
    vals = []
    try:
        with db() as con:
            rows = con.execute("SELECT json_extract(detail, '$.ofp.zfw_lbs') AS zfw, json_extract(detail, '$.ofp.payload_lbs') AS pl "
                               "FROM pireps WHERE aircraft=? AND demo=0 AND detail IS NOT NULL ORDER BY filed_at DESC LIMIT 60", (code,)).fetchall()
        for r in rows:
            try:
                zfw, pl = float(r["zfw"] or 0), float(r["pl"] or 0)
            except (TypeError, ValueError):
                continue
            dow = zfw - pl
            if zfw > 0 and mtow and mtow * 0.3 < dow < mtow * 0.85:   # skip broken or foreign plans
                vals.append(dow)
            if len(vals) >= 25:
                break
    except Exception:
        vals = []
    out = None
    if len(vals) >= 3:
        vals.sort()
        mid = len(vals) // 2
        out = {"dow": round(vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2), "flights": len(vals)}
    _DOW_CACHE[code] = (time.time(), out)
    return out


def manifest_seed_ok(seed):
    """A preliminary load sheet's seed, as handed back by the browser: short plain text only."""
    seed = str(seed or "")
    return seed if seed.startswith("PRE|") and len(seed) <= 120 and seed.isprintable() else None


@app.post("/api/plan/loadsheet")
def plan_loadsheet():
    """The preliminary load sheet, before SimBrief: units and positions, weights against the limits, fuel, balance and DG.
    Nothing is saved. Requesting the flight with the same seed keeps these units, positions and waybills on the release."""
    b = request.json or {}
    try:
        m = resolve_mission(b)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    ac_code = m["aircraft"][0] if m.get("charter") else (b.get("aircraft") or m["aircraft"][0])
    ac = FLEET.get(ac_code)
    if not ac:
        return jsonify({"error": "Choose an aircraft."}), 400
    est = plan_estimate(m, ac_code)
    f = est["fuel"]
    seed = manifest_seed_ok(b.get("seed")) or prelim_seed(m, ac_code)
    airframe = (b.get("airframe") or "").upper() or None
    fake = {"mission": m, "aircraft": ac_code, "ofp": None, "flight_number": m["id"], "requested_at": time.time(),
            "airframe": airframe, "manifest_seed": seed}
    try:
        d = dispatch.generate(fake, FLEET, dispatch_pilot())
    except Exception as e:  # never break the flight page over the paperwork
        return jsonify({"error": f"The load sheet could not be built: {e}"}), 500
    # fuel from the planning estimate (the release takes SimBrief's figures later)
    d["fuel"] = {"block_fuel_lbs": f["block"], "taxi_fuel_lbs": f["taxi"], "trip_fuel_lbs": f["trip"],
                 "reserve_fuel_lbs": f["final_reserve"]}   # the minimum release fuel adds its own alternate allowance
    d["block_min"] = f["est_block_min"]
    learned = learned_dow(ac_code)
    paper = dispatch.paperwork(d, FLEET, None, [], None, AIRPORTS, dow_override=(learned or {}).get("dow"))
    ls, lim = paper["loadsheet"], paper["limits"]
    checks = [
        {"name": "Zero fuel weight", "value": ls["zfw"], "limit": lim["mzfw"], "code": "MZFW"},
        {"name": "Take-off weight", "value": ls["tow"], "limit": lim["mtow"], "code": "MTOW"},
        {"name": "Landing weight", "value": ls["law"], "limit": lim["mlw"], "code": "MLW"},
        {"name": "Payload", "value": ls["payload"], "limit": lim["max_payload"], "code": "MAX PL"},
    ]
    for c in checks:
        c["margin"] = c["limit"] - c["value"]
        c["ok"] = c["margin"] >= 0
    keep = ("ferry", "aircraft", "aircraft_name", "icao", "tail", "origin", "destination", "deck", "positions", "dg", "shc",
            "totals", "shipments", "onward", "international", "block_min")
    out = {k: d.get(k) for k in keep}
    out.update({"seed": seed, "mission_id": m["id"], "loadsheet": ls, "limits": lim, "checks": checks,
                "min_release_fuel": paper["min_release_fuel"], "fuel": f, "cruise_fl": est["cruise_fl"],
                "alternate": est["alternate"], "payload_requested": m.get("payload_lbs") or 0,
                "erg": paper["erg"], "ok": all(c["ok"] for c in checks),
                "dow_source": {"kind": "learned", "flights": learned["flights"]} if learned else {"kind": "estimate"}})
    return jsonify(out)


@app.post("/api/plan/helper")
def plan_helper():
    """Planning help for a flight: cruise level, fuel estimate, likely runways and an alternate."""
    b = request.json or {}
    try:
        m = resolve_mission(b)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    ac_code = b.get("aircraft") or (m.get("aircraft") or [None])[0]
    ac = FLEET.get(ac_code)
    if not ac:
        return jsonify({"error": "Choose an aircraft."}), 400
    o, d = m["origin"], m["destination"]
    est = plan_estimate(m, ac_code)
    dist, course, fl, why, altn, fuel = est["distance"], est["course"], est["cruise_fl"], est["cruise_why"], est["alternate"], est["fuel"]
    ids = [o["icao"], d["icao"]]
    try:
        got = weather.metars(ids)
    except Exception:
        got = {}
    wx = {}
    for i in ids:
        rep = got.get(i)  # weather.metars returns decoded reports (a raw METAR string is accepted too)
        dec = weather.decode_metar(rep) if isinstance(rep, str) else (dict(rep) if isinstance(rep, dict) else None)
        if dec:
            dec["wind_text"] = weather.wind_text(dec.get("wind"))
            wx[i] = dec
    min_ft = ac.get("min_rwy_ft") or 6000
    return jsonify({"distance_nm": round(dist), "course": round(course), "cruise_fl": fl, "cruise_why": why,
                    "fuel": fuel, "alternate": altn, "weather_ok": bool(wx),
                    "departure": pick_runway(o["icao"], min_ft, wx.get(o["icao"])),
                    "arrival": pick_runway(d["icao"], min_ft, wx.get(d["icao"]))})


# ---------------------------------------------------------------- automatic OFP
OFP_WATCH_MIN = 90


def start_ofp_watch(booking):
    """Booked without a SimBrief plan: keep checking SimBrief and attach the plan when it's generated."""
    s = settings()
    if booking.get("ofp") or not (s.get("simbrief_username") or s.get("simbrief_userid")):
        return
    state["ofp_watch"] = {"requested_at": booking.get("requested_at"), "flight": booking["flight_number"],
                          "until": time.time() + OFP_WATCH_MIN * 60, "checks": 0, "last_error": None}


def ofp_watch_status():
    w = state.get("ofp_watch")
    return {k: w[k] for k in ("flight", "until", "checks", "last_error")} if w else None


def simbrief_settings(pid=None):
    """SimBrief details for one pilot: their own, never another pilot's."""
    return pilot_settings(pid=pid or va.current_pilot_id())


@releases.serialized
def check_ofp_watch(pid=None):
    """One check for one pilot: fetch the latest SimBrief plan and attach it if it's a new plan for their flight."""
    sess = session(pid)
    w = sess.get("ofp_watch")
    if not w:
        return None
    booking = load_booking(pid)
    underway = bool(sess.get("remote")) and (sess.get("remote_status") or {}).get("phase") not in (None, "PREFLIGHT")
    if not booking or booking.get("requested_at") != w["requested_at"] or booking.get("ofp") or time.time() > w["until"] or underway or releases.started(booking):
        sess["ofp_watch"] = None
        return None
    try:
        ofp = parse_ofp(fetch_simbrief(simbrief_settings(pid)))
    except Exception as e:  # not generated yet, or SimBrief unreachable: try again next time
        w["last_error"] = str(e)
        return None
    w["checks"] += 1
    try:
        generated = float(ofp.get("generated") or 0)
    except (TypeError, ValueError):
        generated = 0
    if generated and generated < (booking.get("requested_at") or 0) - 600:
        w["last_error"] = "The latest SimBrief plan is older than this booking."
        return None
    errors, _warnings = validate_ofp(ofp, booking["mission"], booking["aircraft"])
    if errors:
        w["last_error"] = " ".join(errors)
        return None
    booking["ofp"] = ofp
    booking["legacy_release"] = booking.get("legacy_release", (booking.get("dispatch") or {}).get("version", 1) < 2)
    booking["dispatch"] = dispatch.generate(booking, FLEET, dispatch_pilot())  # fuel and weights from the plan
    void_signature(booking)
    save_booking(booking, pid)
    sess["ofp_watch"] = None
    print(f"SimBrief plan {ofp.get('request_id')} attached to {booking['flight_number']} automatically.")
    return ofp


def ofp_watcher():
    """Checks SimBrief for every pilot who is waiting for a plan."""
    while True:
        time.sleep(45)
        for pid in [p for p, sess in list(SESSIONS.items()) if sess.get("ofp_watch")]:
            try:
                check_ofp_watch(pid)
            except Exception as e:
                print("OFP watch:", e)


@app.post("/api/ofp/watch")
def ofp_watch_api():
    """Start or stop watching SimBrief for the booked flight's plan."""
    b = request.json or {}
    booking = load_booking()
    if b.get("on") is False or not booking:
        state["ofp_watch"] = None
        return jsonify({"ok": True, "watch": None})
    s = settings()
    if not (s.get("simbrief_username") or s.get("simbrief_userid")):
        return jsonify({"error": "Add your SimBrief username or pilot ID in Settings first."}), 400
    start_ofp_watch(booking)
    return jsonify({"ok": True, "watch": ofp_watch_status()})


# ---------------------------------------------------------------- PAC ACARS app
CHECKPOINT_PATH = DATA / "flight_checkpoint.json"


def checkpoint_meta(booking=None):
    """The in-progress flight the ACARS app saved here, if it belongs to the current booking."""
    booking = booking or load_booking()
    cp = load_json(CHECKPOINT_PATH, None)
    if not booking or not cp or cp.get("requested_at") != booking.get("requested_at"):
        return None
    return {k: cp.get(k) for k in ("flight", "phase", "saved_at", "source")}


def clear_checkpoint():
    CHECKPOINT_PATH.unlink(missing_ok=True)


ACARS_BUILD_DIR = DATA / "acars-builds"      # kept with your data, so updates never remove the installer


def acars_downloads():
    """The newest PAC ACARS build: uploaded through Staff (data/acars-builds), or placed in static/downloads by
    build_acars.bat when PAC runs on the same PC you build on."""
    ACARS_BUILD_DIR.mkdir(exist_ok=True)
    found = {}
    for folder, url_for in ((ACARS_BUILD_DIR, lambda n: f"/api/acars/build/{n}"),
                            (Path(app.static_folder) / "downloads", lambda n: f"/static/downloads/{n}")):
        for f in folder.glob("PAC-ACARS-*"):
            m = re.fullmatch(r"PAC-ACARS-(?:Setup-)?(\d+\.\d+\.\d+)(-portable)?\.(exe|zip)", f.name)
            if not m:
                continue
            v = tuple(int(x) for x in m.group(1).split("."))
            kind = "portable" if m.group(2) else "installer"
            found.setdefault(v, {}).setdefault(kind, {"url": url_for(f.name), "size_mb": round(f.stat().st_size / 1_048_576, 1),
                                                      "file": f.name, "uploaded": f.stat().st_mtime})
    if not found:
        return None
    v = max(found)
    return {"version": ".".join(map(str, v)), **found[v]}


def acars_installer_info():
    """The newest installer, for PAC ACARS's built-in update (1.1+). None when only a portable zip is published."""
    d = acars_downloads() or {}
    inst = d.get("installer")
    if not inst:
        return None
    url = inst["url"]
    # Staff can serve installers from a host that skips Cloudflare (data/site.json "download_host", e.g.
    # https://dl.pac-va.com): the update then downloads straight from this server, much faster.
    host = str(va.site().get("download_host") or "").strip().rstrip("/")
    if host.startswith("https://") and url.startswith("/api/acars/build/"):
        url = host + url
    return {"version": d.get("version"), "url": url, "size_mb": inst["size_mb"], "file": inst["file"]}


@app.get("/api/acars/build/<path:name>")
def acars_build_file(name):
    """Download the PAC ACARS build. Members only, like the rest of the Downloads page."""
    if not re.fullmatch(r"PAC-ACARS-(?:Setup-)?\d+\.\d+\.\d+(-portable)?\.(exe|zip)", name):
        return jsonify({"error": "No such build."}), 404
    return send_from_directory(ACARS_BUILD_DIR, name, as_attachment=True)


_BUILD_LOOSE = re.compile(r"pac[\s_-]*acars[\s_-]*(setup[\s_-]*)?v?(\d+\.\d+\.\d+)[\s_-]*(portable)?.*\.(exe|zip)", re.I)


def acars_build_name(filename, head=b""):
    """Work out the proper name for an uploaded PAC ACARS build, forgiving the renaming browsers and Windows do
    ("PAC-ACARS-Setup-1.0.0 (1).exe", "pac-acars-1.0.0-portable - Copy.zip"). Returns (name, None) or (None, why)."""
    base = Path(filename or "").name.strip()
    low = base.lower()
    if low in ("pac acars.exe", "pac_acars.exe", "pac-acars.exe"):
        return None, ("That's the program itself from the dist folder, which can't run without the files beside it. "
                      "Upload the portable zip or the installer from the static\\downloads folder of your PAC on "
                      "Windows instead, named like PAC-ACARS-1.0.0-portable.zip or PAC-ACARS-Setup-1.0.0.exe.")
    m = _BUILD_LOOSE.fullmatch(base)
    if not m:
        return None, (f"\u201c{base}\u201d doesn't look like a PAC ACARS build. build_acars.bat saves it in the "
                      "static\\downloads folder of your PAC on Windows, named like PAC-ACARS-1.0.0-portable.zip "
                      "or PAC-ACARS-Setup-1.0.0.exe.")
    setup, version, portable, ext = m.group(1), m.group(2), m.group(3), m.group(4).lower()
    if ext == "exe" and head[:2] != b"MZ":
        return None, "That file isn't a Windows program, so it can't be the PAC ACARS installer."
    if ext == "zip" and head[:4] != b"PK\x03\x04":
        return None, "That file isn't a valid zip, so it can't be the PAC ACARS portable build. Try building it again."
    if ext == "exe":
        return f"PAC-ACARS-Setup-{version}.exe", None
    return f"PAC-ACARS-{version}-portable.zip", None


@app.post("/api/staff/acars/build")
def acars_build_upload():
    """Staff upload a PAC ACARS build made by build_acars.bat on Windows."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Choose the PAC ACARS installer or portable zip."}), 400
    head = f.stream.read(4)
    f.stream.seek(0)
    name, why = acars_build_name(f.filename, head)
    if not name:
        return jsonify({"error": why}), 400
    ACARS_BUILD_DIR.mkdir(exist_ok=True)
    tmp = ACARS_BUILD_DIR / (name + ".part")      # never leave a half-uploaded file where pilots can download it
    f.save(tmp)
    tmp.replace(ACARS_BUILD_DIR / name)
    return jsonify({"ok": True, "file": name, "acars": acars_downloads()})


@app.delete("/api/staff/acars/build/<path:name>")
def acars_build_delete(name):
    if not re.fullmatch(r"PAC-ACARS-(?:Setup-)?\d+\.\d+\.\d+(-portable)?\.(exe|zip)", name):
        return jsonify({"error": "No such build."}), 404
    (ACARS_BUILD_DIR / name).unlink(missing_ok=True)
    return jsonify({"ok": True, "acars": acars_downloads()})


@app.get("/api/acars/app/download")
def acars_download_info():
    return jsonify(acars_downloads() or {"version": None})


ACARS_APP_SETTINGS = ("source", "xplane_host", "demo_speedup", "allow_ground_reposition", "vatsim_cid", "ivao_vid")


@app.get("/api/acars/app/hello")
def acars_app_hello():
    """What the ACARS app needs to start: the booked flight, a few settings and company NOTAMs."""
    s = pilot_settings()
    booking = load_booking()
    ac = FLEET.get((booking or {}).get("aircraft"), {})
    return jsonify({"airline": "Pagani Air Cargo", "pilot": dispatch_pilot(), "booking": booking,
                    "aircraft": {"name": ac.get("name"), "sim": ac.get("sim"), "icao": ac.get("icao"),
                                 "mtow_lbs": ac.get("mtow_lbs"), "max_payload_lbs": ac.get("max_payload_lbs")} if booking else None,
                    "settings": {k: s.get(k) for k in ACARS_APP_SETTINGS}, "notams": [n["title"] for n in va.active_notams()[:3]],
                    "remote": state.get("remote"),
                    "latest_app": (acars_downloads() or {}).get("version"), "latest_installer": acars_installer_info(),
                    "discord_app_id": str(va.site().get("discord_app_id") or "").strip() or None,
                    "checkpoint": checkpoint_meta(booking),
                    "ofp_watch": ofp_watch_status()})


@app.post("/api/acars/app/start")
@releases.serialized
def acars_app_start():
    booking = load_booking()
    if not booking:
        return jsonify({"error": "No flight is booked. Book one on the PAC website first."}), 400
    b = request.json or {}
    if b.get("requested_at") and b["requested_at"] != booking.get("requested_at"):
        return jsonify({"error": "The booking has changed on the website. Reload the flight in the ACARS app."}), 409
    source = str(b.get("source") or "MSFS")[:20]
    if signature_required(booking) and not releases.valid_signature(booking) and not (b.get("resume") is True and releases.started(booking)):
        why = "Your release was amended when the SimBrief plan arrived, so it needs your signature again." if booking.get("release_amended") else \
              "The captain signs the dispatch release before the flight starts."
        return jsonify({"error": f"{why} Open the Dispatch release on the PAC website (My bids or ACARS), review it and press Sign release. Then start again.",
                        "needs_signature": True}), 409
    releases.mark_started(booking)
    save_booking(booking)
    state.update(remote={"source": source, "started": time.time(), "requested_at": booking.get("requested_at"),
                         "flight": booking["flight_number"]}, remote_status=None, remote_seen=time.time(), recorder=None, source_name=source)
    clear_flight_state()
    ac_sim = FLEET.get(booking["aircraft"], {}).get("sim", "")
    warning = (f"PAC flies the {FLEET[booking['aircraft']]['name']} in {ac_sim}, but ACARS is connecting to {source}. Tracking works either way."
               if source in ("MSFS", "X-Plane") and ac_sim and source not in ac_sim else None)
    return jsonify({"ok": True, "warning": warning})


LIVE_STALE_S = 120          # a flight drops off the live map if PAC ACARS hasn't reported for two minutes


def _thin(track, n=160):
    """Every few points of a flight's track, enough to draw its path."""
    pts = [p for p in (track or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    step = max(1, len(pts) // n)
    out = [[p[0], p[1]] for p in pts[::step]]
    if pts and out[-1] != [pts[-1][0], pts[-1][1]]:
        out.append([pts[-1][0], pts[-1][1]])
    return out


def live_flights(member=True):
    """Everyone flying for PAC right now, from what their PAC ACARS reports."""
    now, out = time.time(), []
    names = {}
    try:
        with db() as con:
            names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM pilots")}
    except Exception:
        pass
    for pid, sess in list(SESSIONS.items()):
        st = sess.get("remote_status") or {}
        live = st.get("live") or {}
        if not sess.get("remote") or now - (sess.get("remote_seen") or 0) > LIVE_STALE_S or live.get("lat") is None:
            continue
        b = load_booking(pid) or {}
        m = b.get("mission") or {}
        ac = FLEET.get(b.get("aircraft"), {})
        f = {"flight": b.get("flight_number") or (sess.get("remote") or {}).get("flight") or "", "aircraft": ac.get("icao") or b.get("aircraft") or "",
             "aircraft_name": ac.get("name", ""), "dep": (m.get("origin") or {}).get("icao"), "arr": (m.get("destination") or {}).get("icao"),
             "lat": round(live["lat"], 4), "lon": round(live["lon"], 4), "alt_ft": round(live.get("alt_ft") or 0),
             "gs": round(live.get("gs") or 0), "hdg": round(live.get("hdg") or 0), "on_ground": bool(live.get("on_ground")),
             "phase": st.get("phase"), "phase_label": st.get("phase_label") or "", "dtg_nm": st.get("dtg_nm"),
             "track": _thin(st.get("track")), "seen": round(now - (sess.get("remote_seen") or now))}
        dest = AIRPORTS.get(f["arr"] or "")
        if dest:
            f["arr_pos"] = [dest["lat"], dest["lon"]]
        if member:
            f.update(pilot_id=pid, pilot=names.get(pid, pid), reg=b.get("airframe"), mission=m.get("title", ""),
                     cargo=m.get("cargo", ""))
        out.append(f)
    return sorted(out, key=lambda x: x["flight"])


@app.get("/api/live")
def live_map():
    """The live map. Members always see it, with pilots' names; visitors only if staff have made it public."""
    import auth
    member = bool(auth.current())
    if not member and not settings().get("live_map_public"):
        return jsonify({"error": "Please sign in.", "signin": True}), 401
    return jsonify({"flights": live_flights(member), "time": time.time()})


def readopt_remote(st):
    """The website keeps who is flying in memory, so a website restart (an update, a reboot) used to forget a flight that
    PAC ACARS was still tracking: it fell off the live map and the app showed an error. PAC ACARS carries on sending
    updates, so when one arrives for this pilot's booking that PAC ACARS started, the website takes the flight back on."""
    booking = load_booking()
    if not booking or not releases.started(booking) or state.get("recorder") or not st.get("phase"):
        return False
    cp = load_json(CHECKPOINT_PATH, {}) or {}
    source = cp.get("source") if cp.get("requested_at") == booking.get("requested_at") else None
    state.update(remote={"source": source or state.get("source_name") or "ACARS app",
                         "started": (booking.get("release_start") or {}).get("at") or time.time(),
                         "requested_at": booking.get("requested_at"), "flight": booking["flight_number"], "readopted": True},
                 remote_seen=time.time())
    if source:
        state["source_name"] = source
    if (st.get("oooi") or {}).get("off"):       # already airborne before the restart: its departure was posted to Discord then
        state["discord_dep_for"] = booking.get("requested_at")
    print(f"  Picked up {booking['flight_number']} again from PAC ACARS after a restart.")
    return True


@app.post("/api/acars/app/live")
def acars_app_live():
    st = (request.json or {}).get("status") or {}
    if not remote_active() and not readopt_remote(st):
        return jsonify({"error": "No flight is registered from the ACARS app. Start tracking again."}), 409
    st.pop("booking", None)
    state.update(remote_status=st, remote_seen=time.time())
    discord_departure(st)
    return jsonify({"ok": True})


def discord_departure(st):
    """Posts the departure to Discord once per flight, as the takeoff roll begins."""
    s = settings()
    if not (s.get("discord_webhook") and s.get("discord_departures", True)):
        return
    if st.get("phase") not in ("TAKEOFF", "TAKEOFF_ROLL", "INITIAL_CLIMB", "CLIMB", "CRUISE"):
        return
    booking = load_booking()
    if not booking or state.get("discord_dep_for") == booking.get("requested_at") or (state.get("remote") or {}).get("source") == "Demo":
        return
    state["discord_dep_for"] = booking.get("requested_at")
    b = {**booking, "aircraft_name": FLEET.get(booking["aircraft"], {}).get("name"), "pilot_name": display_pilot_name()}
    discord_post.post(s["discord_webhook"], discord_post.departure_embed(b, st))


def display_pilot_name():
    try:
        pid = va.current_pilot_id()
        with db() as con:
            r = con.execute("SELECT name FROM pilots WHERE id=?", (pid,)).fetchone()
        return f"Capt. {r['name']} ({pid})" if r else pid
    except Exception:
        return None


@app.post("/api/acars/app/complete")
def acars_app_complete():
    """The ACARS app hands over the finished flight record; the website scores it."""
    booking = load_booking()
    b = request.json or {}
    if not booking:
        return jsonify({"error": "The booking no longer exists on the website."}), 400
    if b.get("requested_at") and b["requested_at"] != booking.get("requested_at"):
        return jsonify({"error": "This flight record belongs to a different booking."}), 409
    try:
        rec = FlightRecorder.from_export(booking, b.get("record") or {})
    except Exception as e:
        return jsonify({"error": f"The flight record could not be read: {e}"}), 400
    if not rec.last:
        return jsonify({"error": "The flight record is empty."}), 400
    rec.allow_reposition = bool(settings().get("allow_ground_reposition", True))
    source = (state.get("remote") or {}).get("source") or b.get("source") or "ACARS app"
    state.update(recorder=rec, source_name=source, remote=None, remote_status=None)
    save_flight_state(rec)
    if rec.complete:
        clear_checkpoint()
    if not rec.complete and not (b.get("force") and rec.oooi["on"]):
        return jsonify({"ok": True, "draft": None})
    return jsonify({"ok": True, "draft": build_pirep(booking, rec)})


@app.post("/api/acars/app/checkpoint")
def acars_app_checkpoint_save():
    """The ACARS app saves the flight in progress here every minute, so any copy of the app can resume it."""
    booking = load_booking()
    b = request.json or {}
    if not booking or b.get("requested_at") != booking.get("requested_at"):
        return jsonify({"error": "This flight record belongs to a different booking."}), 409
    rec = b.get("record") or {}
    if rec.get("complete"):
        return jsonify({"ok": True})
    save_json(CHECKPOINT_PATH, {"requested_at": booking.get("requested_at"), "flight": booking["flight_number"], "phase": rec.get("phase"),
                                "saved_at": time.time(), "source": str(b.get("source") or "")[:20], "record": rec})
    return jsonify({"ok": True})


@app.get("/api/acars/app/checkpoint")
def acars_app_checkpoint_get():
    booking = load_booking()
    cp = load_json(CHECKPOINT_PATH, None)
    if not booking or not cp or cp.get("requested_at") != booking.get("requested_at"):
        return jsonify({"error": "No saved flight on the website for this booking."}), 404
    return jsonify(cp)


@app.post("/api/acars/app/ofp")
@releases.serialized
def acars_app_ofp():
    """The ACARS app fetches the latest SimBrief OFP for the booked flight (or sends one as 'raw')."""
    booking = load_booking()
    if not booking:
        return jsonify({"error": "No flight is booked."}), 400
    if remote_active() and (state.get("remote_status") or {}).get("phase") not in (None, "PREFLIGHT"):
        return jsonify({"error": "The flight is already under way. Import the OFP before pushback."}), 409
    b = request.json or {}
    try:
        if b.get("raw"):
            text = b["raw"].strip()
            raw = json.loads(text) if text.startswith("{") else xml_to_obj(ET.fromstring(text))
        else:
            raw = fetch_simbrief(simbrief_settings())
        ofp = parse_ofp(raw)
    except (ValueError, ET.ParseError) as e:
        return jsonify({"error": str(e)}), 400
    errors, warnings = validate_ofp(ofp, booking["mission"], booking["aircraft"])
    if errors:
        return jsonify({"error": " ".join(errors), "warnings": warnings}), 400
    if releases.started(booking):
        return jsonify({"error": "This flight has started. Finish or cancel it before replacing its flight plan."}), 409
    booking["ofp"] = ofp
    booking["legacy_release"] = booking.get("legacy_release", (booking.get("dispatch") or {}).get("version", 1) < 2)
    booking["dispatch"] = dispatch.generate(booking, FLEET, dispatch_pilot())  # fuel and weights from the new plan
    void_signature(booking)
    save_booking(booking)
    return jsonify({"ok": True, "ofp": ofp, "warnings": warnings})


@app.post("/api/acars/app/abort")
@releases.serialized
def acars_app_abort():
    booking = load_booking()
    if booking and booking.pop("release_start", None):
        save_booking(booking)
    state.update(remote=None, remote_status=None)
    clear_checkpoint()
    return jsonify({"ok": True})


@app.post("/api/acars/stop")
@releases.serialized
def acars_stop():
    booking = load_booking()
    if booking and booking.pop("release_start", None):
        save_booking(booking)
    stop_tracking()
    clear_flight_state()
    state.update(recorder=None, remote=None, remote_status=None)
    clear_checkpoint()
    return jsonify({"ok": True})


@app.get("/api/acars/status")
def acars_status():
    rec = state.get("recorder")
    if not rec and remote_active():
        st = dict(state.get("remote_status") or {})
        fresh = time.time() - (state.get("remote_seen") or 0) < REMOTE_TIMEOUT
        st.update({"remote": True, "tracking": True, "connected": fresh and bool(st.get("connected")), "source": state["remote"]["source"],
                   "error": None if fresh else "No update from the PAC ACARS app for a while. Is it still running?",
                   "booking": load_booking(), "resumable": False})
        st.setdefault("messages", [])
        return jsonify(st)
    if not rec:
        return jsonify({"tracking": False, "booking": load_booking()})
    # a flight record handed over by the PAC ACARS app, waiting to be filed
    st = rec.status()
    st.update({"handed_over": True, "tracking": False, "connected": False, "error": None, "source": state.get("source_name"),
               "glitches_filtered": getattr(rec, "glitches", 0)})
    return jsonify(st)


@app.get("/api/pirep/draft")
def pirep_draft():
    rec, booking = state.get("recorder"), load_booking()
    if not rec or not booking or not rec.last:
        return jsonify({"error": "No tracked flight to report."}), 400
    if not rec.complete and not (request.args.get("force") == "1" and rec.oooi["on"]):
        return jsonify({"error": "Park at the stand, set the parking brake and shut down all engines to go on block."}), 400
    return jsonify(build_pirep(booking, rec))


@app.post("/api/pirep")
def file_pirep():
    rec, booking = state.get("recorder"), load_booking()
    if not rec or not booking or not rec.last:
        return jsonify({"error": "No tracked flight to report."}), 400
    if not rec.complete and not ((request.json or {}).get("force") and rec.oooi["on"]):
        return jsonify({"error": "The flight is not on block yet."}), 400
    stop_tracking()
    p = build_pirep(booking, rec)
    if not rec.complete:   # "File anyway": the aircraft landed but never went on block. Staff check it.
        p["flags"] = list(p.get("flags") or []) + ["Filed without going on block (File anyway)"]
        p["review_status"] = "Pending"
    pid_ = va.current_pilot_id()
    before_rank = va.career(pid_)["rank"]
    before_badges = {b["id"] for b in va.badges(pid_) if b["earned"]}
    remarks = (request.json or {}).get("remarks", "")[:2000]
    detail = {"v": 2, "breakdown": p["breakdown"], "oooi": p["oooi"], "events": rec.events, "messages": rec.messages,
              "track": rec.track, "timeline": rec.timeline, "landing": rec.landing, "ofp": booking.get("ofp"),
              "trip_burn_lbs": p["trip_burn_lbs"], "planned_trip_lbs": p["planned_trip_lbs"],
              "target_block_min": p["target_block_min"], "max_alt": p["max_alt"], "bounces": p["bounces"],
              "bonuses": p["bonuses"], "base_points": p["base_points"], "checkride": p.get("checkride"),
              "type_checkride": p.get("type_checkride"), "training": p.get("training"),
              "loaded_lbs": p.get("loaded_lbs"), "mission_payload_lbs": p.get("mission_payload_lbs"),
              "landing_weight_lbs": p.get("landing_weight_lbs"), "mlw_lbs": p.get("mlw_lbs"),
              "profile": getattr(rec, "profile", []), "landing_analysis": p.get("landing_analysis"), "dispatch": booking.get("dispatch"),
              "aircraft_name": p.get("aircraft_name"), "pilot_rank": va.career(va.current_pilot_id())["rank"],
              "takeoff_analysis": p.get("takeoff_analysis"), "economics": p.get("economics"), "integrity": p.get("integrity"),
              "online": p.get("online"), "urgent": p.get("urgent"), "job": p.get("job")}
    with db() as con:
        cur = con.execute("""INSERT INTO pireps (filed_at, mission_id, mission_title, category, flight_number, aircraft,
            registration, dep, arr, planned_arr, block_min, flight_min, distance_nm, fuel_used_lbs, payload_lbs,
            landing_rate, landing_g, score, grade, status, points, demo, source, remarks, detail,
            pilot_id, review_status, flags, bonus_points, airframe, revenue, cost, profit)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (time.time(), p["mission_id"], p["mission_title"], p["category"], p["flight_number"],
                           p["aircraft"], p["registration"], p["dep"], p["arr"], p["planned_arr"], p["block_min"],
                           p["flight_min"], p["distance_nm"], p["fuel_used_lbs"], p["payload_lbs"], p["landing_rate"],
                           p["landing_g"], p["score"], p["grade"], p["status"], p["points"], int(p["demo"]),
                           p["source"], remarks, json.dumps(detail),
                           va.current_pilot_id(), p["review_status"], json.dumps(p["flags"]), p["bonus_points"], p.get("airframe"),
                           p["economics"]["revenue"], p["economics"]["total_cost"], p["economics"]["profit"]))
        pid = cur.lastrowid
    p["paid"] = va.after_file(p, booking, rec, pid)
    car = va.career(pid_)
    new_badges = [b for b in va.badges(pid_) if b["earned"] and b["id"] not in before_badges]
    ranks = [r["name"] for r in va.RANKS]
    p["unlocked"] = {"rank": {"from": before_rank, "to": car["rank"], "insignia": va.RANKS[ranks.index(car["rank"])]["insignia"],
                              "unlocks": va.ranks_effective()[ranks.index(car["rank"])]["unlocks"]}
                     if car["rank"] != before_rank and ranks.index(car["rank"]) > ranks.index(before_rank) else None,
                     "badges": new_badges}
    clear_booking()
    clear_flight_state()
    state["recorder"] = None
    s_ = settings()
    if s_.get("discord_webhook") and s_.get("discord_arrivals", True) and not p.get("demo"):
        discord_post.post(s_["discord_webhook"], discord_post.arrival_embed({**p, "arr": p.get("arr") or booking["mission"]["destination"]["icao"]},
                                                                            display_pilot_name()))
    return jsonify({"id": pid, **p})


BOARD_STATUS = {"PREFLIGHT": "BOARDING", "PUSHBACK": "PUSHBACK", "TAXI_OUT": "TAXIING", "TAKEOFF": "DEPARTING",
                "INITIAL_CLIMB": "DEPARTED", "CLIMB": "CLIMBING", "CRUISE": "EN ROUTE", "DESCENT": "DESCENDING",
                "APPROACH": "APPROACH", "GO_AROUND": "GO AROUND", "LANDING": "LANDED", "TAXI_IN": "TAXIING IN", "ARRIVED": "AT GATE"}


@app.get("/api/weather")
def weather_api():
    ids = [x for x in (request.args.get("ids") or "").split(",") if x][:10]
    try:
        m = weather.metars(ids)
        out = {i.upper(): {"metar": m.get(i.upper())} for i in ids}
        if request.args.get("taf"):
            for i in list(out)[:4]:
                try:
                    out[i]["taf"] = weather.taf(i)
                except weather.WeatherError:
                    out[i]["taf"] = None
        return jsonify(out)
    except weather.WeatherError as e:
        return jsonify({"error": str(e)}), 503


@app.get("/api/weather/network")
def weather_network():
    ids = sorted({r["origin"]["icao"] for r in ROUTES.values()} | {r["destination"]["icao"] for r in ROUTES.values()})
    try:
        m = weather.metars(ids)
        return jsonify({k: v["category"] for k, v in m.items()})
    except weather.WeatherError as e:
        return jsonify({"error": str(e)}), 503




@app.get("/api/airframes/<reg>")
def airframe_history(reg):
    reg = reg.upper()
    frame = next((a for a in va.airframes() if a["reg"] == reg), None)
    if not frame:
        return jsonify({"error": "Airframe not found."}), 404
    with db() as con:
        rows = [dict(r) for r in con.execute(
            """SELECT p.id, p.filed_at, p.flight_number, p.dep, p.arr, p.block_min, p.flight_min, p.landing_rate, p.grade, p.status,
               p.profit, r.name pilot FROM pireps p LEFT JOIN pilots r ON r.id=p.pilot_id
               WHERE p.airframe=? AND p.demo=0 ORDER BY p.filed_at""", (reg,))]
    pts = {}
    for r in rows:
        for ic in (r["dep"], r["arr"]):
            a = AIRPORTS.get(ic)
            if a:
                pts[ic] = [a["lat"], a["lon"]]
    return jsonify({"airframe": frame, "flights": rows, "airports": pts, "fleet": FLEET.get(frame["type"], {}).get("name"),
                    "profit": sum(r["profit"] or 0 for r in rows)})


@app.get("/api/jobs")
def jobs_list():
    return jsonify(va.jobs_today())


@app.get("/api/urgent")
def urgent_list():
    return jsonify(va.urgent_missions())


@app.get("/api/economics/estimate")
def economics_estimate():
    body = request.args
    try:
        m = resolve_mission({"mission_id": body.get("mission_id")}) if body.get("mission_id") else None
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not m:
        return jsonify({"error": "Unknown mission."}), 400
    code = body.get("aircraft") or m["aircraft"][0]
    if code not in FLEET:
        return jsonify({"error": "Unknown aircraft."}), 400
    dist = gc_distance_nm(m["origin"]["lat"], m["origin"]["lon"], m["destination"]["lat"], m["destination"]["lon"])
    return jsonify(economics.estimate(m, code, FLEET, settings(), dist))


@app.post("/api/economics/estimate")
def economics_estimate_post():
    b = request.json or {}
    try:
        m = resolve_mission(b)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    code = (m["aircraft"][0] if m.get("charter") else b.get("aircraft")) or m["aircraft"][0]
    ofp = b.get("ofp") or {}
    dist = gc_distance_nm(m["origin"]["lat"], m["origin"]["lon"], m["destination"]["lat"], m["destination"]["lon"])
    return jsonify(economics.estimate(m, code, FLEET, settings(), dist, payload_lbs=ofp.get("payload_lbs"),
                                      block_min=ofp.get("est_block_min"), trip_fuel_lbs=ofp.get("trip_fuel_lbs")))


@app.get("/api/finance")
def finance():
    import datetime as _dt
    s = settings()
    start = float(s.get("starting_capital") or economics.DEFAULT_START_CAPITAL)
    with db() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, filed_at, flight_number, mission_title, category, aircraft, dep, arr, block_min, revenue, cost, profit, detail "
            "FROM pireps WHERE demo=0 AND review_status='Accepted' AND revenue IS NOT NULL ORDER BY filed_at")]
    cash, timeline, by_type, by_route, by_cat, cost_split, months = start, [], {}, {}, {}, {}, {}
    for r in rows:
        d = json.loads(r.pop("detail") or "{}")
        cash += r["profit"]
        timeline.append([r["filed_at"], round(cash)])
        bh = (r["block_min"] or 0) / 60
        for bucket, key in ((by_type, r["aircraft"]), (by_route, f"{r['dep']}-{r['arr']}"), (by_cat, r["category"] or "Other")):
            b = bucket.setdefault(key, {"flights": 0, "revenue": 0, "cost": 0, "profit": 0, "block_h": 0})
            b["flights"] += 1; b["revenue"] += r["revenue"]; b["cost"] += r["cost"]; b["profit"] += r["profit"]; b["block_h"] += bh
        for k, v in ((d.get("economics") or {}).get("costs") or {}).items():
            cost_split[k] = cost_split.get(k, 0) + v
        mo = _dt.datetime.fromtimestamp(r["filed_at"], _dt.timezone.utc).strftime("%Y-%m")
        mb = months.setdefault(mo, {"revenue": 0, "cost": 0, "profit": 0, "flights": 0})
        mb["revenue"] += r["revenue"]; mb["cost"] += r["cost"]; mb["profit"] += r["profit"]; mb["flights"] += 1
    with db() as con:
        shares = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE kind='profit_share'").fetchone()[0]
    cash -= shares
    this_month = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m")
    tot = {"revenue": sum(r["revenue"] for r in rows), "cost": sum(r["cost"] for r in rows), "profit": sum(r["profit"] for r in rows)}
    routes = sorted(({"route": k, **v} for k, v in by_route.items()), key=lambda x: -x["profit"])
    import auth
    if not auth.is_staff():
        # pilots see how the airline is doing and their own share of it; staff keep the full books
        pid = va.current_pilot_id()
        with db() as con:
            mine = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE kind='profit_share' AND pilot_id=?", (pid,)).fetchone()[0]
            my_flights = con.execute("SELECT COUNT(*) FROM pireps WHERE pilot_id=? AND demo=0 AND review_status='Accepted'", (pid,)).fetchone()[0]
        return jsonify({"summary": True, "cash": round(cash), "starting_capital": start, "profit_share_paid": round(shares),
                        "totals": tot, "this_month": months.get(this_month, {"revenue": 0, "cost": 0, "profit": 0, "flights": 0}),
                        "timeline": timeline, "my_share": round(mine), "my_flights": my_flights,
                        "best_type": ({"aircraft": max(by_type.items(), key=lambda kv: kv[1]["profit"])[0]} if by_type else None)})
    return jsonify({"cash": round(cash), "starting_capital": start, "profit_share_paid": round(shares), "fuel_price": float(s.get("fuel_price_gal") or economics.DEFAULT_FUEL_PRICE),
                    "totals": tot, "this_month": months.get(this_month, {"revenue": 0, "cost": 0, "profit": 0, "flights": 0}),
                    "months": [{"month": k, **v} for k, v in sorted(months.items())], "timeline": timeline,
                    "by_type": [{"aircraft": k, **v} for k, v in sorted(by_type.items(), key=lambda kv: -kv[1]["profit"])],
                    "by_category": [{"category": k, **v} for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1]["profit"])],
                    "best_routes": [r for r in routes if r["profit"] > 0][:8], "worst_routes": [r for r in routes[::-1] if r["profit"] < 0][:5],
                    "cost_split": dict(sorted(cost_split.items(), key=lambda kv: -kv[1])),
                    "ledger": [dict(r) for r in rows[::-1][:25]]})


EXCUSED_DELAYS = acars_core.EXCUSED_DELAYS


@app.get("/api/va/board")
def ops_board():
    """Rows for the split-flap departures and arrivals boards: every pilot's flight, not just the viewer's.
    Departures: flights booked or getting ready to leave (from every pilot's booking and what their PAC ACARS reports),
    topped up with this month's featured routes. Arrivals: flights in the air or landing now, then the latest PIREPs."""
    import datetime as _dt
    import hashlib as _hl
    now = time.time()
    zt = lambda t: _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%H%M") if t else "----"
    with db() as con:
        names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM pilots")}
    who = lambda pid: va.short_name(names.get(pid) or pid)
    dep, arr = [], []
    for pid, b in sorted(all_bookings(), key=lambda x: x[1].get("requested_at") or 0):
        m = b.get("mission") or {}
        if not m.get("origin") or not m.get("destination"):
            continue
        ac = FLEET.get(b.get("aircraft"), {})
        row = {"time": zt(b.get("requested_at")), "flight": b.get("flight_number") or "", "from": m["origin"]["icao"],
               "to": m["destination"]["icao"], "type": ac.get("icao", ""), "tail": b.get("airframe") or "",
               "pilot": who(pid), "status": "BOOKED", "remark": (m.get("category") or "").upper()[:10]}
        sess = SESSIONS.get(pid) or {}
        st = sess.get("remote_status") or {}
        tracking = sess.get("remote") and now - (sess.get("remote_seen") or 0) <= LIVE_STALE_S and st.get("phase")
        if not tracking:
            if now - (b.get("requested_at") or now) < 72 * 3600:   # a booking left untouched for days isn't news
                dep.append(row)
            continue
        phase, live, oooi = st["phase"], st.get("live") or {}, st.get("oooi") or {}
        row["status"] = BOARD_STATUS.get(phase, "ACTIVE")
        if phase in ("PREFLIGHT", "PUSHBACK", "TAXI_OUT", "TAKEOFF"):
            row["time"] = zt(oooi.get("out") or now)
            row["_sort"] = -1          # pilots actually getting ready go above booked flights
            dep.append(row)
            continue
        dest = m["destination"]
        if live.get("lat") is not None and not live.get("on_ground") and (live.get("gs") or 0) > 60 and dest.get("lat") is not None:
            dtg = gc_distance_nm(live["lat"], live["lon"], dest["lat"], dest["lon"])
            row["time"] = zt(now + dtg / max(live["gs"], 120) * 3600)
            alt = live.get("alt_ft") or 0
            row["remark"] = f"FL{alt / 100:03.0f}" if alt > 18000 else f"{alt:,.0f}FT".replace(",", "")
        else:
            row["time"] = zt(oooi.get("on") or now)
            if st.get("landing") and st["landing"].get("rate_fpm") is not None:
                row["remark"] = f"{int(st['landing']['rate_fpm'])}FPM"
        arr.append(row)
    with db() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT flight_number, dep, arr, aircraft, airframe, landing_rate, grade, status, pilot_id, json_extract(detail, '$.oooi.in') AS block_in, filed_at "
            "FROM pireps WHERE id IN (SELECT id FROM pireps WHERE demo=0 AND review_status!='Rejected' ORDER BY filed_at DESC LIMIT 10) "
            "ORDER BY filed_at DESC")]
    for r in rows:
        stat = {"Delivered": "ARRIVED", "Delivered late": "ARR LATE", "Diverted": "DIVERTED", "Failed": "INCIDENT"}.get(r["status"], "ARRIVED")
        arr.append({"time": zt(r["block_in"] or r["filed_at"]), "flight": r["flight_number"], "from": r["dep"], "to": r["arr"],
                    "type": FLEET.get(r["aircraft"], {}).get("icao", ""), "tail": r["airframe"] or "", "pilot": who(r["pilot_id"]), "status": stat,
                    "remark": f"{int(round(r['landing_rate']))}FPM {r['grade']}" if r["landing_rate"] is not None else r["grade"]})
    # scheduled departures from this month's featured routes, at times that stay the same all day, to fill the board
    today = _dt.datetime.now(_dt.timezone.utc)
    featured = []
    for rid in va.featured_routes():
        r = ROUTES.get(rid)
        if not r:
            continue
        h = int(_hl.md5((rid + today.strftime("%Y%m%d")).encode()).hexdigest(), 16)
        std = today.replace(hour=(today.hour + 1 + h % 9) % 24, minute=(h // 9) % 12 * 5, second=0, microsecond=0)
        featured.append({"time": std.strftime("%H%M"), "flight": rid, "from": r["origin"]["icao"], "to": r["destination"]["icao"],
                         "type": FLEET.get(r["aircraft"][0], {}).get("icao", ""), "tail": "", "pilot": "OPEN", "status": "SCHEDULED",
                         "remark": "FEATURED", "_sort": (std.timestamp() - today.timestamp()) % 86400})
    dep.sort(key=lambda x: x.get("_sort", 0))
    featured.sort(key=lambda x: x["_sort"])
    dep = (dep + featured)[:max(8, len(dep))]
    for x in dep:
        x.pop("_sort", None)
    return jsonify({"departures": dep, "arrivals": arr[:max(10, len(arr) - len(rows))], "utc": today.strftime("%H%M")})


@app.get("/api/logbook")
def logbook():
    """A pilot's own logbook. Staff can look at any pilot's with ?pilot=PAC0002."""
    import auth
    pid = va.current_pilot_id()
    want = str(request.args.get("pilot") or "").strip().upper()
    if want and want != pid:
        if not auth.is_staff():
            return jsonify({"error": "That's for staff only."}), 403
        pid = want
    with db() as con:
        # every column except the big detail (the recorded track); just the checkride results are read out of it
        cols = [c[1] for c in con.execute("PRAGMA table_info(pireps)") if c[1] != "detail"]
        ck = "CASE WHEN mission_id=? OR category IN ('Checkride', 'Type checkride') OR mission_id LIKE 'TR-%' THEN json_extract(detail, '$.{}') END"
        rows = [dict(r) for r in con.execute(f"SELECT {', '.join(cols)}, {ck.format('type_checkride')} AS _tc, {ck.format('checkride')} AS _lc "
                                             "FROM pireps WHERE pilot_id=? ORDER BY filed_at DESC", (va.CHECKRIDE_ID, va.CHECKRIDE_ID, pid))]
    for r in rows:
        try:
            tc, lc = json.loads(r.pop("_tc", None) or "{}"), json.loads(r.pop("_lc", None) or "{}")
        except (ValueError, TypeError):
            tc, lc = {}, {}
        ck = ({"kind": "type", "family": tc.get("family"), "passed": bool(tc.get("passed")), "reasons": tc.get("reasons") or []} if tc
              else {"kind": "line", "passed": bool(lc.get("passed")), "reasons": lc.get("reasons") or []} if lc else None)
        r["checkride_result"] = ck
        r.pop("detail", None)
    live = [r for r in rows if not r["demo"] and r.get("review_status", "Accepted") == "Accepted"]
    for r in rows:
        r["flags"] = json.loads(r.get("flags") or "[]")
    totals = {
        "flights": len(live), "block_hours": round(sum(r["block_min"] or 0 for r in live) / 60, 1),
        "cargo_lbs": sum(r["payload_lbs"] or 0 for r in live if r["status"] != "Failed"),
        "points": sum(r["points"] or 0 for r in live),
        "avg_landing": round(sum(r["landing_rate"] for r in live if r["landing_rate"] is not None) / sum(r["landing_rate"] is not None for r in live)) if any(r["landing_rate"] is not None for r in live) else None,
        "avg_score": round(sum(r["score"] for r in live if r["score"] is not None) / sum(r["score"] is not None for r in live)) if any(r["score"] is not None for r in live) else None,
    }
    car = va.career(pid)       # what counts for rank and pay: failed checkrides are left out
    totals.update(career_hours=car["pac_hours"], career_flights=car["flights"])
    return jsonify({"pireps": rows, "totals": totals, "pilot": pid})


@app.get("/api/logbook/<int:pid>")
def logbook_entry(pid):
    with db() as con:
        r = con.execute("SELECT * FROM pireps WHERE id=?", (pid,)).fetchone()
    if not r:
        return jsonify({"error": "PIREP not found."}), 404
    r = dict(r)
    if r.get("source") == "Manual":
        import auth
        if r["pilot_id"] != va.current_pilot_id() and not auth.is_staff():
            return jsonify({"error": "Not found."}), 404
    r["detail"] = json.loads(r["detail"] or "{}")
    # who flew it, for the landing and takeoff cards (not whoever happens to be looking at it)
    pid_ = str(r.get("pilot_id") or "")
    with db() as con:
        who = con.execute("SELECT name FROM pilots WHERE id=?", (pid_,)).fetchone()
    r["pilot_name"] = who["name"] if who else ("Former PAC pilot" if pid_.startswith("EX-") else "")
    return jsonify(r)


@app.delete("/api/logbook/<int:pid>")
def logbook_delete(pid):
    """Removing a PIREP changes careers and the airline's books, so it's for staff."""
    import auth
    if not auth.is_staff():
        return jsonify({"error": "Only staff can delete a PIREP. Ask staff if this one is wrong."}), 403
    with db() as con:
        con.execute("DELETE FROM pireps WHERE id=?", (pid,))
    return jsonify({"ok": True})


va.init({"db": db, "settings": settings, "FLEET": FLEET, "MISSIONS": MISSIONS, "ROUTES": ROUTES, "AIRPORTS": AIRPORTS, "PARTNERS": PARTNERS,
         "airport_obj": airport_obj, "gc_distance_nm": gc_distance_nm, "load_profile": load_profile, "clean_text": clean_text,
         "num": num, "load_json": load_json, "save_json": save_json, "DATA": DATA, "acars_downloads": lambda: acars_downloads()})
app.register_blueprint(va.bp)
import group  # noqa: E402  (Pagani Aviation Group hub feed and PRA division)
group.init({"db": db, "settings": settings, "save_settings": lambda s: save_json(SETTINGS_PATH, s), "FLEET": FLEET, "career": va.career, "site": va.site})
app.register_blueprint(group.bp)
import shop  # noqa: E402
with db() as _con:
    shop.init_db(_con)
app.register_blueprint(shop.bp)
import liveries  # noqa: E402
liveries.init({"DATA": DATA, "FLEET": FLEET, "settings": settings, "load_json": load_json, "save_json": save_json, "clean_text": clean_text})
app.register_blueprint(liveries.bp)
import botlink  # noqa: E402
botlink.init({"db": db, "settings": settings, "DATA": DATA, "va": va, "live_flights": lambda member=True: live_flights(member),
              "FLEET": FLEET, "AIRPORTS": AIRPORTS})
app.register_blueprint(botlink.bp)
va.C["on_pirep_accepted"] = botlink.pirep_accepted
import sayintentions as SI  # noqa: E402
SI.init({"db": db, "settings": settings, "FLEET": FLEET, "AIRPORTS": AIRPORTS, "load_booking": load_booking,
         "load_profile": load_profile, "va": va})


@app.get("/api/sayintentions")
def si_status():
    return jsonify(SI.status(va.current_pilot_id()))


@app.post("/api/sayintentions/key")
def si_key():
    """A pilot pastes their SayIntentions API key on the Downloads page (PAC ACARS finds it by itself)."""
    pid = va.current_pilot_id()
    try:
        SI.set_pilot_key(pid, (request.json or {}).get("api_key"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if SI.pilot_key(pid) and SI.ready():
        SI.push_now(pid, "key saved")
    return jsonify(SI.status(pid))


@app.post("/api/sayintentions/push")
def si_push():
    pid = va.current_pilot_id()
    ok, err = SI.push_now(pid, "sent by the pilot")
    return jsonify({**SI.status(pid), "sent": ok}), (200 if ok else 400)


@app.post("/api/acars/app/sayintentions")
def si_from_app():
    """PAC ACARS read the pilot's key from SayIntentions' flight.json: remember it and bring their crew up to date."""
    pid = va.current_pilot_id()
    try:
        changed = SI.set_pilot_key(pid, (request.json or {}).get("api_key"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if changed or (request.json or {}).get("new_flight"):
        SI.notify(pid, "PAC ACARS saw a SayIntentions flight", delay=0.5)
    return jsonify({"ok": True, "ready": SI.ready()})

# ---------------------------------------------------------------- sign-in
import datetime as _dt_auth  # noqa: E402
import secrets as _secrets  # noqa: E402

import auth  # noqa: E402


def _secret_key():
    """A random key for signing sign-in cookies, made once and kept in data/ (it survives updates)."""
    f = DATA / "secret_key"
    if not f.exists():
        DATA.mkdir(exist_ok=True)
        f.write_text(_secrets.token_hex(32), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip()


app.secret_key = _secret_key()
# On a public server (PAC_PUBLIC=1) PAC runs behind a web server that provides HTTPS: cookies are then marked
# secure, and the real visitor address is read from the proxy so sign-in rate limiting works.
PUBLIC_MODE = os.environ.get("PAC_PUBLIC", "").strip().lower() in ("1", "true", "yes")
app.config.update(SESSION_COOKIE_NAME="pac_session", SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=PUBLIC_MODE,
                  MAX_CONTENT_LENGTH=int(os.environ.get("PAC_MAX_UPLOAD_MB", "2048")) * 1024 * 1024,
                  PERMANENT_SESSION_LIFETIME=_dt_auth.timedelta(days=auth.SESSION_DAYS))
if PUBLIC_MODE:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


@app.after_request
def security_headers(resp):
    """Sensible protections for a site on the open internet."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if PUBLIC_MODE:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resp
auth.init({"db": db, "settings": settings, "load_json": load_json, "DATA": DATA})
app.register_blueprint(auth.bp)
app.before_request(auth.gatekeeper)
import speedup  # noqa: E402  (short cache for start-up data, browser caching)
speedup.init(app)

import pilot_dashboard
pilot_dashboard.register(app, globals())
import operations_health
operations_health.register(app, globals())
import rotation_planner
rotation_planner.register(app, globals())
import cargo_programs
cargo_programs.register(app, globals())
import cargo_experience
cargo_experience.register(app, globals())
import crew_planning
crew_planning.register(app, globals())
import group_flight  # noqa: E402  (the weekly group flight)
group_flight.register(app, globals())
import problem_reports
problem_reports.register(app, globals())


import manual_pireps
manual_pireps.register(app, va)

if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    db().close()
    try:
        b = backup_data("startup")
        if b:
            print(f"  Backup saved to {b}")
    except Exception as e:
        print("  Backup failed:", e)
    repair_logbook()
    migrate_booking_file()
    paid = [x for x in va.backpay() if x]
    if paid:
        print(f"  Paid {len(paid)} earlier flights into your pilot wallet (${sum(x['total'] for x in paid):,.0f}).")
    restore_flight_state()
    threading.Thread(target=ofp_watcher, daemon=True).start()
    port = int(os.environ.get("PAC_PORT", "5050"))
    host = os.environ.get("PAC_HOST", "127.0.0.1")
    if PUBLIC_MODE:
        try:
            from waitress import serve as _serve
        except ImportError:
            print("\n  Public mode needs waitress:  pip install waitress\n")
            raise SystemExit(1)
        print(f"\n  Pagani Air Cargo serving on {host}:{port} (public mode, behind a web server providing HTTPS)\n")
        _serve(app, host=host, port=port, threads=12, ident="PAC")
    else:
        print(f"\n  Pagani Air Cargo ACARS running at http://localhost:{port}\n")
        app.run(host=host, port=port, debug=False, threaded=True)
