"""Pagani Air Cargo virtual airline layer.

Everything that turns the flight tracker into an airline: the pilot roster and
applications, career ranks, events and featured routes, tours, awards and
leaderboards, shared airframe tracking and the staff PIREP review queue.

The data model is multi-pilot (every PIREP carries a pilot ID) so it can move to
a hosted server later without a rewrite. Today it runs locally for one pilot.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import time
import training

from flask import Blueprint, jsonify, request, send_from_directory

bp = Blueprint("va", __name__)
C = {}  # shared context from app.py: db, settings, FLEET, MISSIONS, ROUTES, AIRPORTS, ...

# ---------------------------------------------------------------- rules
RANKS = [
    {"name": "Cadet", "insignia": "/static/ranks/cadet.jpg", "hours": 0, "avg": 0, "checkride": False, "unlocks": []},
    {"name": "Second Officer", "insignia": "/static/ranks/second-officer.jpg", "hours": 0, "avg": 0, "checkride": True, "unlocks": ["B738F", "B722F", "B732F", "B733F"]},
    {"name": "First Officer", "insignia": "/static/ranks/first-officer.jpg", "hours": 25, "avg": 80, "checkride": True, "unlocks": ["A306F", "B752F"]},
    {"name": "Senior First Officer", "insignia": "/static/ranks/senior-first-officer.jpg", "hours": 75, "avg": 80, "checkride": True, "unlocks": ["MD11F", "B763F"]},
    {"name": "Captain", "insignia": "/static/ranks/captain.jpg", "hours": 150, "avg": 82, "checkride": True, "unlocks": ["B77F", "B742F"]},
    {"name": "Senior Captain", "insignia": "/static/ranks/senior-captain.jpg", "hours": 300, "avg": 85, "checkride": True, "unlocks": ["B748F"]},
]
HOME_BASE = "KCVG"
PAY_RATES = {"Cadet": 30, "Second Officer": 55, "First Officer": 95, "Senior First Officer": 130, "Captain": 210, "Senior Captain": 280}
PROFIT_SHARE = 0.05
JUMPSEAT = {"pac": {"label": "Jumpseat on a PAC freighter", "base": 25, "per_nm": 0.03},
            "partner": {"label": "Partner jumpseat", "base": 15, "per_nm": 0.02},
            "airline": {"label": "Airline ticket", "base": 80, "per_nm": 0.11}}
AVG_WINDOW = 10          # average score over the last N accepted flights
AVG_MIN_FLIGHTS = 3      # flights needed before an average counts

REVIEW = {"auto_accept_score": 80, "hard_landing_fpm": -600, "max_landing_g": 1.8, "max_bounces": 1}
A_CHECK_HOURS = 500

CHECKRIDE_ID = "PAC001"
CHECKRIDE = {"aircraft": "B738F", "min_score": 80, "min_rate": -600, "max_g": 1.8}

# Type ratings, in real-world families: one checkride covers closely related aircraft
RATING_FAMILY = {"B738F": "B737", "B732F": "B737", "B733F": "B737", "B722F": "B727", "A306F": "A300", "MD11F": "MD-11",
                 "B752F": "B757/767", "B763F": "B757/767", "B77F": "B777", "B742F": "B747 classic", "B748F": "B747-8"}
TYPE_CHECKRIDE = {"min_score": 80, "min_rate": -600, "max_g": 1.8, "max_approach_speed_spread": 35,
                  "max_sustained_descent_fpm": 1300, "min_nm": 250, "max_nm": 1000}

FEATURED_COUNT = 6
FEATURED_MULT = 1.25

DEFAULT_EVENTS = [
    {"id": "hub-week-2026-09", "name": "Cincinnati Hub Week", "start": "2026-09-21", "end": "2026-09-30", "multiplier": 1.25,
     "categories": [], "regions": [], "airports": ["KCVG"],
     "description": "Every flight into or out of our main hub earns 25% extra points while we celebrate the Cincinnati sort."},
    {"id": "relief-week-2026-10", "name": "Relief Week", "start": "2026-10-05", "end": "2026-10-11", "multiplier": 1.5,
     "categories": ["Humanitarian", "Medical"], "regions": [], "airports": [],
     "description": "Humanitarian and medical missions pay 50% extra points. The whole airline goes where it is needed most."},
    {"id": "pacific-surge-2026-11", "name": "Transpacific Peak", "start": "2026-11-16", "end": "2026-11-30", "multiplier": 1.3,
     "categories": [], "regions": ["Transpacific"], "airports": [],
     "description": "Holiday e-commerce volumes peak across the Pacific. Transpacific routes pay 30% extra points."},
]

TOURS = [
    {"id": "ATW", "name": "Around the world in the 777F", "aircraft": ["B77F"], "bonus": 1500, "series": 9100,
     "legs": ["KCVG", "LIMC", "OMDW", "VHHH", "PANC", "KCVG"],
     "description": "Six sectors, four continents, one airframe. Cincinnati to Milan, Dubai, Hong Kong and home over the Pacific via Anchorage."},
    {"id": "CRB", "name": "Caribbean relief circuit", "aircraft": ["B738F", "B722F", "B733F", "B752F"], "bonus": 600, "series": 9200,
     "legs": ["KMIA", "MTPP", "MDSD", "TJSJ", "MKJP", "KMIA"],
     "description": "A post-hurricane supply loop from Miami through Haiti, the Dominican Republic, Puerto Rico and Jamaica."},
    {"id": "AKB", "name": "Alaska bush run", "aircraft": ["B722F", "B738F", "B732F"], "bonus": 600, "series": 9300,
     "legs": ["KSEA", "PANC", "PABE", "PAOM", "PAFA", "PANC"],
     "description": "Food, fuel parts and mail for communities with no road in. Short runways, fast-changing weather."},
    {"id": "EUX", "name": "European express loop", "aircraft": ["A306F", "B738F", "B752F", "B763F"], "bonus": 500, "series": 9400,
     "legs": ["LIMC", "EDDP", "EBLG", "EGSS", "LEMD", "LIMC"],
     "description": "A night-sort rotation through the big European express hubs, starting and ending at Malpensa."},
]

# Rotations: a real freighter's working pattern, several legs flown in order and back to the start. Unlike tours they can be
# flown again and again; every full lap pays the rotation bonus. Each rotation offers the types (from "types") that can fly
# every leg. Leg numbers come from "series" (PAC9001 up): 9000-9099 and 9500-9599 are kept for rotations.
ROTATIONS = [
    {"id": "R1", "name": "Pacific gateway", "series": 9000, "bonus": 900, "types": ["B77F", "B748F"],
     "legs": ["VHHH", "PANC", "KCVG", "PANC", "VHHH"],
     "cargo": ["Electronics and e-commerce for the US", "Transpacific e-commerce for the hub", "US exports: machinery and pharmaceuticals", "Cherries and seafood for Asia"],
     "description": "The classic heavy freighter loop: Hong Kong to the US hub through Anchorage, and back."},
    {"id": "R2", "name": "Narita–Chicago classic", "series": 9010, "bonus": 700, "types": ["MD11F", "B742F", "B763F", "B77F"],
     "legs": ["RJAA", "PANC", "KORD", "PANC", "RJAA"],
     "cargo": ["Automotive and precision parts", "Precision parts for the Midwest", "Machinery and pharmaceuticals for Asia", "Beef and fruit for Japan"],
     "description": "The way the jumbo freighters always did it: Tokyo to Chicago with a fuel and crew stop in Anchorage."},
    {"id": "R3", "name": "Flower run", "series": 9020, "bonus": 450, "types": ["A306F", "B752F", "B763F", "B722F", "MD11F"],
     "legs": ["KMIA", "SKBO", "SEQM", "KMIA"],
     "cargo": ["Consumer goods and machinery", "Empty flower boxes and packaging", "Long-stem roses for the US"],
     "description": "Down to Bogotá, across to Quito and home to Miami full of roses. Two high-altitude airports on one lap."},
    {"id": "R4", "name": "South American circle", "series": 9030, "bonus": 800, "types": ["MD11F", "B742F", "B77F"],
     "legs": ["KMIA", "SPJC", "SCEL", "SAEZ", "SBGR", "KMIA"],
     "cargo": ["Mining spares and electronics", "Asparagus for onward connection", "Salmon and wine", "Beef and leather", "Fruit, flowers and auto parts"],
     "description": "A big loop round the continent: Lima, Santiago, Buenos Aires and São Paulo before the long sector home."},
    {"id": "R5", "name": "Caribbean island hopper", "series": 9040, "bonus": 450, "types": ["B732F", "B733F", "B738F", "B722F"],
     "legs": ["TJSJ", "TNCM", "TAPA", "TBPB", "TTPP", "TJSJ"],
     "cargo": ["Island resupply", "Island resupply and mail", "General cargo", "Inter-island freight", "Seafood and returns"],
     "description": "Five short sectors down the island chain, starting with the beach approach into St Maarten."},
    {"id": "R6", "name": "Night sort, Europe", "series": 9050, "bonus": 400, "types": ["A306F", "B752F", "B738F", "B733F"],
     "legs": ["EDDP", "EGNX", "EIDW", "EBLG", "EDDP"],
     "cargo": ["Express parcels", "Express parcels and mail", "Express parcels", "E-commerce parcels"],
     "description": "An overnight express loop through the big European sorting hubs and back to Leipzig before dawn."},
    {"id": "R7", "name": "Arctic Norway", "series": 9060, "bonus": 500, "types": ["B733F", "B732F", "B738F", "B722F"],
     "legs": ["ENGM", "ENBO", "ENTC", "ENSB", "ENTC", "ENGM"],
     "cargo": ["North Norway resupply", "Arctic freight", "Svalbard resupply", "Research samples and returns", "Fresh fish"],
     "description": "Up the coast of Norway to Svalbard at 78° north and back again. Short days in winter, midnight sun in summer."},
    {"id": "R8", "name": "North Slope", "series": 9070, "bonus": 500, "types": ["B732F", "B733F", "B738F"],
     "legs": ["PANC", "PASC", "PABR", "PAOT", "PANC"],
     "cargo": ["Oil-field equipment", "Arctic community freight", "Village resupply", "Returns and mail"],
     "description": "Oil-field freight to Deadhorse, then the Arctic coast villages. A job for the gravel-kit 737-200."},
    {"id": "R9", "name": "Gulf to East Africa", "series": 9080, "bonus": 550, "types": ["A306F", "B752F", "B763F", "MD11F"],
     "legs": ["OMDW", "HAAB", "HKJK", "HTDA", "OMDW"],
     "cargo": ["Consumer electronics and relief stock", "Regional transshipment freight", "General cargo", "Cashews and spices"],
     "description": "Dubai to Addis Ababa, Nairobi and Dar es Salaam: hot and high in Ethiopia, then down to the coast."},
    {"id": "R10", "name": "Copperbelt", "series": 9090, "bonus": 450, "types": ["B738F", "B733F", "B722F", "B752F"],
     "legs": ["FAOR", "FZQA", "FLKK", "FVRG", "FAOR"],
     "cargo": ["Mining equipment", "Copper cathode samples", "General cargo", "Tobacco and returns"],
     "description": "Mining freight from Johannesburg to the Copperbelt and back through Lusaka and Harare."},
    {"id": "R11", "name": "Himalayan circuit", "series": 9500, "bonus": 700, "types": ["B738F", "B733F", "B752F", "B732F"],
     "legs": ["VIDP", "VNKT", "VQPR", "VECC", "VIDP"],
     "cargo": ["Relief and consumer goods for Nepal", "Bhutan resupply", "Returns and handicrafts", "Tea and general cargo"],
     "description": "Kathmandu and then Paro, the hardest approach in the network, before heading down to Kolkata and back to Delhi."},
    {"id": "R12", "name": "South-East Asia loop", "series": 9510, "bonus": 450, "types": ["A306F", "B752F", "B763F", "B738F"],
     "legs": ["WSSS", "VTBS", "VVTS", "VHHH", "WSSS"],
     "cargo": ["Electronics components", "Hard drives and fresh fruit", "Garments and electronics", "Semiconductors"],
     "description": "The electronics belt: Singapore, Bangkok, Ho Chi Minh City and Hong Kong."},
    {"id": "R13", "name": "South Pacific islands", "series": 9520, "bonus": 550, "types": ["B752F", "B738F", "B733F", "B732F"],
     "legs": ["NZAA", "NFFN", "NSFA", "NFTF", "NZAA"],
     "cargo": ["Island resupply", "Island freight and mail", "General cargo", "Fresh fish and produce"],
     "description": "Fiji, Samoa and Tonga from Auckland. Long overwater sectors with few alternates."},
    {"id": "R14", "name": "Around Australia", "series": 9530, "bonus": 650, "types": ["A306F", "B738F", "B752F", "B763F"],
     "legs": ["YSSY", "YBBN", "YBCS", "YPDN", "YPPH", "YMML", "YSSY"],
     "cargo": ["Domestic express freight", "Far North Queensland freight", "Top End resupply", "Mining spares", "Crayfish and returns", "Domestic express freight"],
     "description": "Six sectors round the continent: up the east coast, across the Top End to Perth and back over the Nullarbor."},
    {"id": "R15", "name": "North Atlantic triangle", "series": 9540, "bonus": 650, "types": ["MD11F", "B763F", "B742F", "B77F"],
     "legs": ["KJFK", "BIKF", "EGSS", "KJFK"],
     "cargo": ["Retail goods and mail", "Fresh Icelandic seafood", "Machinery and documents"],
     "description": "New York to Keflavík, on to London and back across the Atlantic."},
    {"id": "R16", "name": "US overnight west", "series": 9550, "bonus": 450, "types": ["B752F", "B763F", "A306F", "B738F"],
     "legs": ["KCVG", "KSEA", "KOAK", "KPHX", "KCVG"],
     "cargo": ["Overnight express parcels", "Express parcels", "Express parcels and mail", "E-commerce parcels for the hub"],
     "description": "Out of the Cincinnati hub to Seattle, down the coast to Oakland, across to Phoenix and home for the sort."},
    {"id": "R17", "name": "High Arctic Canada", "series": 9560, "bonus": 550, "types": ["B733F", "B732F", "B752F"],
     "legs": ["CYUL", "CYFB", "CYRB", "CYFB", "CYUL"],
     "cargo": ["Arctic resupply", "Research station supplies", "Returns and samples", "Returns and mail"],
     "description": "Montréal to Iqaluit, then on to the gravel strip at Resolute Bay, one of the northernmost airports in Canada."},
    {"id": "R18", "name": "Mediterranean islands", "series": 9570, "bonus": 400, "types": ["B738F", "B722F", "B733F", "A306F"],
     "legs": ["LIMC", "LMML", "LICC", "LIEE", "LIMC"],
     "cargo": ["Island resupply", "General cargo", "Sicilian citrus", "Sardinian produce"],
     "description": "From the Milan hub to Malta, Sicily and Sardinia."},
]

DEFAULT_AIRFRAMES = [
    ("N738PC", "B738F", "KCVG"), ("N739PC", "B738F", "KCVG"), ("N740PC", "B738F", "KMIA"), ("N741PC", "B738F", "LIMC"),
    ("N600PC", "B722F", "KCVG"), ("N601PC", "B722F", "PANC"), ("N602PC", "B722F", "KMIA"),
    ("N001PC", "A306F", "KCVG"), ("N002PC", "A306F", "KCVG"), ("N003PC", "A306F", "LIMC"), ("N004PC", "A306F", "OMDW"),
    ("N110PC", "MD11F", "KCVG"), ("N111PC", "MD11F", "LIMC"), ("N112PC", "MD11F", "VHHH"),
    ("N770PC", "B77F", "KCVG"), ("N771PC", "B77F", "VHHH"), ("N772PC", "B77F", "OMDW"), ("N773PC", "B77F", "PANC"),
    ("N748PC", "B748F", "KCVG"), ("N749PC", "B748F", "VHHH"),
    ("N300PC", "B732F", "PANC"), ("N301PC", "B732F", "PANC"), ("N302PC", "B732F", "KSEA"),
    ("N010PC", "B733F", "KCVG"), ("N011PC", "B733F", "KMIA"), ("N012PC", "B733F", "LIMC"),
    ("N757PC", "B752F", "KCVG"), ("N758PC", "B752F", "KCVG"), ("N759PC", "B752F", "KMIA"),
    ("N763PC", "B763F", "KCVG"), ("N764PC", "B763F", "KMIA"), ("N765PC", "B763F", "LIMC"),
    ("N200PC", "B742F", "KCVG"), ("N201PC", "B742F", "PANC"),
]

DEFAULT_SITE = {
    "discord_invite": "",          # shown in the welcome letter when set
    "contact_email": "ops@pac-va.com",   # the public contact address: footer, privacy policy, VATSIM
    "public_url": "",              # the address pilots reach PAC at (sign-in links use it)
    "letters_from": "",            # who the letters are signed by; blank uses the staff member's own name
    "discord_widget": "1556081575215636492",  # Discord server ID for the live widget on the home page (blank hides it)

    "tagline": "Relief, medicine and critical freight. Anywhere, on time.",
    "intro": ("Pagani Air Cargo is a virtual cargo airline for flight simulator pilots. We fly humanitarian relief, "
              "cold-chain medicine, AOG parts and scheduled freight across a worldwide network from our main hub in Cincinnati, "
              "with every flight tracked from pushback to on-block."),
    "story": ("PAC started with a simple idea: the most satisfying flights in a simulator are the ones that matter. A 727 into "
              "Kathmandu the morning after an earthquake. Vaccines to Nairobi against the clock. A spare engine for an airliner "
              "stranded in Anchorage. I built the airline around those missions, then around the network that real freighters "
              "fly every night: flowers out of Bogotá, electronics out of Hong Kong, parcels through Cincinnati. Every aircraft "
              "wears the same red, and every flight is flown to the same standard."),
    "recruiting": ("We are looking for pilots who enjoy flying properly: planned in SimBrief, flown by the book, landed with care. "
                   "You don't need real-world experience. You need to enjoy getting it right."),
}

BADGES = [
    ("first_flight", "First delivery", "File your first accepted PIREP."),
    ("checkride", "Checkride passed", "Pass the 737 line checkride."),
    ("flights_10", "10 flights", "Complete 10 accepted flights."),
    ("flights_50", "50 flights", "Complete 50 accepted flights."),
    ("flights_100", "Centurion", "Complete 100 accepted flights."),
    ("hours_100", "100 hours", "Log 100 block hours with PAC."),
    ("hours_500", "500 hours", "Log 500 block hours with PAC."),
    ("butter", "Butter", "Land softer than 100 fpm."),
    ("streak_a", "Straight A's", "Five A-grade flights in a row."),
    ("relief_10", "Relief pilot", "Fly 10 humanitarian or medical missions."),
    ("heavy", "Heavy metal", "Fly the 747-8F."),
    ("all_types", "Type collector", "Fly every aircraft in the fleet."),
    ("himalaya", "Himalayan", "Land at Kathmandu."),
    ("arctic", "Arctic operator", "Land north of 60° latitude."),
    ("continents", "Six continents", "Land on six continents."),
    ("airports_10", "Explorer", "Visit 10 different airports."),
    ("airports_25", "Globetrotter", "Visit 25 different airports."),
    ("airports_50", "Route network", "Visit 50 different airports."),
    ("airports_100", "Centennial", "Visit 100 different airports."),
    ("countries_5", "Border crosser", "Fly to or from 5 countries."),
    ("countries_10", "International", "Fly to or from 10 countries."),
    ("countries_25", "World cargo", "Fly to or from 25 countries."),
    ("on_time_25", "Reliable", "25 on-time deliveries."),
    ("event", "Event flyer", "Earn an event bonus."),
    ("rotation", "Rotation", "Fly a full multi-leg rotation."),
    ("rotations_5", "Line pilot", "Fly five full rotations."),
] + [(f"tour_{t['id']}", t["name"], f"Complete the {t['name']} tour.") for t in TOURS]


# ---------------------------------------------------------------- setup
def init(ctx):
    C.update(ctx)
    global TOUR_LEGS
    TOUR_LEGS = build_tour_legs()
    TOUR_LEGS.update(build_rotation_legs())   # rotation legs are looked up wherever tour legs are


def migrate(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(pireps)")}
    for col, decl in [("pilot_id", "TEXT"), ("review_status", "TEXT DEFAULT 'Accepted'"), ("review_note", "TEXT"),
                      ("reviewed_at", "REAL"), ("flags", "TEXT"), ("bonus_points", "INTEGER DEFAULT 0"), ("airframe", "TEXT"),
                      ("revenue", "REAL"), ("cost", "REAL"), ("profit", "REAL"), ("booking_key", "TEXT")]:
        if col not in cols:
            con.execute(f"ALTER TABLE pireps ADD COLUMN {col} {decl}")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pireps_booking_key ON pireps(pilot_id, booking_key) WHERE booking_key IS NOT NULL")
    con.execute("CREATE TABLE IF NOT EXISTS pirep_effects (pirep_id INTEGER PRIMARY KEY, applied REAL NOT NULL)")
    con.execute("""CREATE TABLE IF NOT EXISTS pilots (id TEXT PRIMARY KEY, name TEXT, email TEXT, country TEXT, discord TEXT,
        simulator TEXT, hub TEXT, joined REAL, status TEXT, checkride TEXT, transfer_hours REAL DEFAULT 0, staff INTEGER DEFAULT 0,
        rank_override TEXT)""")
    pcols = {r[1] for r in con.execute("PRAGMA table_info(pilots)")}
    if pcols and "location" not in pcols:
        con.execute("ALTER TABLE pilots ADD COLUMN location TEXT")
    if pcols and "rank_override" not in pcols:
        con.execute("ALTER TABLE pilots ADD COLUMN rank_override TEXT")
        # the founder is appointed Senior Captain
        con.execute("UPDATE pilots SET rank_override='Senior Captain' WHERE staff=1 AND id=?", (C["settings"]().get("pilot_id") or "PAC0001",))
    con.execute("""CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY AUTOINCREMENT, submitted REAL, name TEXT, email TEXT,
        country TEXT, discord TEXT, simulator TEXT, experience TEXT, hub TEXT, motivation TEXT, status TEXT, note TEXT, pilot_id TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS airframes (reg TEXT PRIMARY KEY, type TEXT, location TEXT, status TEXT,
        hours REAL DEFAULT 0, cycles INTEGER DEFAULT 0, hours_since_check REAL DEFAULT 0, last_flight TEXT, last_pilot TEXT,
        updated REAL, note TEXT)""")
    if "simbrief" not in {r[1] for r in con.execute("PRAGMA table_info(pilots)")}:
        con.execute("ALTER TABLE pilots ADD COLUMN simbrief TEXT")  # each pilot's own SimBrief username
    if "prefs" not in {r[1] for r in con.execute("PRAGMA table_info(pilots)")}:
        con.execute("ALTER TABLE pilots ADD COLUMN prefs TEXT")  # each pilot's own settings (VATSIM CID, map style…)
    if "stand" not in {r[1] for r in con.execute("PRAGMA table_info(airframes)")}:
        con.execute("ALTER TABLE airframes ADD COLUMN stand TEXT")  # where the aircraft is parked, so it departs from there
    import heavy_check
    heavy_check.migrate(con)
    con.execute("""CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, data TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS maint (id INTEGER PRIMARY KEY AUTOINCREMENT, reg TEXT, ata INTEGER, description TEXT,
        severity TEXT, category TEXT, due REAL, status TEXT DEFAULT 'open', source TEXT, reported_by TEXT, flight TEXT, pirep_id INTEGER,
        time REAL, cleared_time REAL, cleared_by TEXT, note TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, kind TEXT, title TEXT, body TEXT,
        important INTEGER DEFAULT 0, expires REAL, author TEXT)""")
    if not con.execute("SELECT 1 FROM news LIMIT 1").fetchone():
        now = time.time()
        con.executemany("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)", [
            (now - 3600, "news", "Partner crew requests are live",
             "FedEx Express, UPS Airlines, Qatar Airways Cargo, Emirates SkyCargo, Cathay Cargo and Atlas Air now hire PAC captains when they're short of crew. Find the requests under Missions › Partners.",
             0, None, "PAC Operations"),
            (now - 1800, "notam", "Import your OFP before printing dispatch paperwork",
             "Dispatch releases show fuel, weights and the route from your SimBrief OFP. Without one, those boxes print blank.",
             0, now + 30 * 86400, "PAC Dispatch"),
            (now - 600, "news", "Share your flights in the gallery",
             "Add screenshots to any PIREP from the logbook. The best ones are featured on the home page.", 0, None, "PAC Operations"),
        ])
    con.execute("""CREATE TABLE IF NOT EXISTS gallery (id INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, pirep_id INTEGER, time REAL,
        caption TEXT, file TEXT, thumb TEXT, featured INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS downloads (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, category TEXT, aircraft TEXT,
        sim TEXT, version TEXT, description TEXT, filename TEXT, stored TEXT, size INTEGER, uploaded REAL, downloads INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS bookings (pilot_id TEXT PRIMARY KEY, data TEXT, requested_at REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS live_missions (id TEXT PRIMARY KEY, data TEXT, scenario_key TEXT, created REAL, expires REAL,
        status TEXT, pilot_id TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, kind TEXT, target REAL,
        period TEXT, deadline REAL, created REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS type_ratings (pilot_id TEXT, family TEXT, source TEXT, date REAL, score INTEGER,
        pirep_id INTEGER, PRIMARY KEY (pilot_id, family))""")
    con.execute("""CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, time REAL, kind TEXT,
        amount REAL, description TEXT, pirep_id INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, day TEXT, kind TEXT, data TEXT, status TEXT, pilot_id TEXT, created REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS urgent (id TEXT PRIMARY KEY, data TEXT, created REAL, expires REAL, status TEXT, pilot_id TEXT)""")
    st = C["settings"]()
    con.execute("UPDATE pireps SET pilot_id=? WHERE pilot_id IS NULL", (st.get("pilot_id") or "PAC0001",))
    if not con.execute("SELECT 1 FROM pilots LIMIT 1").fetchone():
        prof = C["load_profile"](st.get("pilot_id") or "PAC0001")
        con.execute("INSERT INTO pilots (id, name, email, hub, joined, status, checkride, transfer_hours, staff, rank_override) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (st.get("pilot_id") or "PAC0001", f"{prof.get('name', 'Founder')}", "", "KCVG", time.time(), "Active", "Waived", 0, 1, "Senior Captain"))
    for (pid_,) in con.execute("SELECT id FROM pilots WHERE location IS NULL").fetchall():
        last = con.execute("SELECT arr FROM pireps WHERE pilot_id=? AND demo=0 AND review_status!='Rejected' AND arr!='UNKNOWN' "
                           "ORDER BY filed_at DESC LIMIT 1", (pid_,)).fetchone()
        con.execute("UPDATE pilots SET location=? WHERE id=?", (last[0] if last else HOME_BASE, pid_))
    # seed default airframes for any aircraft type that has none yet (new installs and newly added types)
    have_types = {r[0] for r in con.execute("SELECT DISTINCT type FROM airframes")}
    for reg, typ, loc in DEFAULT_AIRFRAMES:
        if typ not in have_types and not con.execute("SELECT 1 FROM airframes WHERE reg=?", (reg,)).fetchone():
            con.execute("INSERT INTO airframes (reg, type, location, status, updated) VALUES (?,?,?,?,?)", (reg, typ, loc, "Available", time.time()))
    if not con.execute("SELECT 1 FROM events LIMIT 1").fetchone():
        for e in DEFAULT_EVENTS:
            con.execute("INSERT INTO events (id, data) VALUES (?,?)", (e["id"], json.dumps(e)))


def current_pilot_id():
    """The signed-in pilot for this request; outside a request (background jobs), the founder."""
    try:
        from flask import has_request_context
        if has_request_context():
            import auth
            pid = auth.current_id()
            if pid:
                return pid
    except Exception:
        pass
    return C["settings"]().get("pilot_id") or "PAC0001"


def today():
    return dt.datetime.now(dt.timezone.utc).date()


# ---------------------------------------------------------------- tours and featured routes
def build_tour_legs():
    legs = {}
    F = C["FLEET"]
    for t in TOURS:
        n = len(t["legs"]) - 1
        for i in range(n):
            o, d = C["airport_obj"](t["legs"][i]), C["airport_obj"](t["legs"][i + 1])
            if not o or not d:
                continue
            ac = F[t["aircraft"][0]]
            dist = C["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
            payload = int(round(ac["max_payload_lbs"] * 0.6 / 500) * 500)
            mid = f"PAC{t['series'] + i + 1}"
            legs[mid] = {
                "id": mid, "title": f"{t['name']} · leg {i + 1} of {n}: {o['city'] or o['icao']} to {d['city'] or d['icao']}",
                "category": "Tour", "priority": "Standard", "tour": t["id"], "leg": i + 1, "legs": n,
                "origin": o, "destination": d, "aircraft": list(t["aircraft"]), "cargo": "Tour freight",
                "payload_lbs": payload, "distance_nm": round(dist),
                "target_block_min": round(45 + dist / ac["cruise_ktas"] * 60 * 1.05),
                "reward": int(round((dist * 0.14 + payload / 1000 * 1.2) / 10) * 10),
                "briefing": f"{t['description']} Leg {i + 1} of {n}, {dist:,.0f} nm. Fly the legs in order with a {' or '.join(F[a]['name'] for a in t['aircraft'])}.",
            }
    return legs


TOUR_LEGS = {}


def build_rotation_legs():
    """The legs of every rotation. Sets each rotation's aircraft: the listed types that can fly every leg."""
    legs = {}
    F = C["FLEET"]
    for r in ROTATIONS:
        stops = [C["airport_obj"](i) for i in r["legs"]]
        if not all(stops):
            r["aircraft"] = []
            continue
        sectors = list(zip(stops, stops[1:]))
        dists = [C["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"]) for o, d in sectors]
        r["aircraft"] = [k for k in r["types"] if k in F and not F[k].get("retired")
                         and all(_fit_types(o, d, 0, dist, [k]) for (o, d), dist in zip(sectors, dists))]
        if not r["aircraft"]:
            continue
        cap = min(F[k]["max_payload_lbs"] for k in r["aircraft"])
        n = len(sectors)
        r["total_nm"] = round(sum(dists))
        for i, ((o, d), dist) in enumerate(zip(sectors, dists)):
            lead = F[r["aircraft"][0]]
            payload = int(round(cap * (0.6 + (i * 7 % 5) / 20) / 500) * 500)
            cargo = r["cargo"][i] if i < len(r["cargo"]) else "General cargo"
            mid = f"PAC{r['series'] + i + 1}"
            legs[mid] = {
                "id": mid, "title": f"{r['name']} · leg {i + 1} of {n}: {o['city'] or o['icao']} to {d['city'] or d['icao']}",
                "category": "Rotation", "priority": "Standard", "rotation": r["id"], "leg": i + 1, "legs": n,
                "origin": o, "destination": d, "aircraft": list(r["aircraft"]), "cargo": cargo,
                "payload_lbs": payload, "distance_nm": round(dist),
                "target_block_min": round(45 + dist / lead["cruise_ktas"] * 60 * 1.05),
                "reward": int(round((dist * 0.16 + payload / 1000 * 1.2) / 10) * 10),
                "briefing": (f"{r['description']} Leg {i + 1} of {n}, {dist:,.0f} nm: {cargo[0].lower() + cargo[1:]}. Fly the legs in order with a "
                             f"{' or '.join(F[a]['name'] for a in r['aircraft'])}; finish the lap for a {r['bonus']:,}-point rotation bonus. "
                             f"You can fly this rotation as often as you like."),
            }
    return legs


def rotation_progress(pilot_id, con=None):
    """Where each pilot is in each rotation: legs flown on the current lap, the next leg and full laps flown.

    Legs count only in order; a leg flown out of order (which booking prevents) is ignored."""
    own = con is None
    con = con or C["db"]()
    rows = con.execute(
        "SELECT mission_id FROM pireps WHERE pilot_id=? AND demo=0 AND status!='Failed' AND review_status!='Rejected' AND mission_id LIKE 'PAC9%' "
        "AND category='Rotation' ORDER BY filed_at, id", (pilot_id,)).fetchall()
    if own:
        con.close()
    flown = [r["mission_id"] for r in rows]
    out = {}
    for r in ROTATIONS:
        ids = [f"PAC{r['series'] + i + 1}" for i in range(len(r["legs"]) - 1)]
        done, laps = 0, 0
        for mid in flown:
            if mid == ids[done]:
                done += 1
                if done == len(ids):
                    done, laps = 0, laps + 1
        out[r["id"]] = {"completed": done, "total": len(ids), "next": ids[done], "laps": laps}
    return out


def featured_routes(month=None):
    month = month or today().strftime("%Y-%m")
    routes = sorted(C["ROUTES"].values(), key=lambda r: hashlib.md5((r["id"] + month).encode()).hexdigest())
    picked, regions = [], set()
    for r in routes:
        if r["region"] not in regions:
            picked.append(r["id"])
            regions.add(r["region"])
        if len(picked) >= FEATURED_COUNT:
            break
    return picked


def load_events():
    with C["db"]() as con:
        return [json.loads(r["data"]) for r in con.execute("SELECT data FROM events")]


def active_events(day=None):
    d = (day or today()).isoformat()
    return [e for e in load_events() if e["start"] <= d <= e["end"]]


def event_matches(e, m):
    if e.get("categories") and m.get("category") not in e["categories"]:
        return False
    if e.get("regions") and m.get("region") not in e["regions"]:
        return False
    if e.get("airports") and not ({m["origin"]["icao"], m["destination"]["icao"]} & set(e["airports"])):
        return False
    return True


def tour_progress(pilot_id, con=None):
    own = con is None
    con = con or C["db"]()
    done = {r["mission_id"] for r in con.execute(
        "SELECT mission_id FROM pireps WHERE pilot_id=? AND demo=0 AND status!='Failed' AND review_status!='Rejected' AND mission_id LIKE 'PAC9%'",
        (pilot_id,))}
    if own:
        con.close()
    out = {}
    for t in TOURS:
        ids = [f"PAC{t['series'] + i + 1}" for i in range(len(t["legs"]) - 1)]
        completed = 0
        for mid in ids:
            if mid in done:
                completed += 1
            else:
                break
        out[t["id"]] = {"completed": completed, "total": len(ids), "next": ids[completed] if completed < len(ids) else None}
    return out


# ---------------------------------------------------------------- pilot pay, wallet, location, jumpseat
def pilot_location(pid=None):
    with C["db"]() as con:
        r = con.execute("SELECT location FROM pilots WHERE id=?", (pid or current_pilot_id(),)).fetchone()
    return (r["location"] if r and r["location"] else HOME_BASE)


def set_location(pid, icao):
    with C["db"]() as con:
        con.execute("UPDATE pilots SET location=? WHERE id=?", (icao, pid))


def balance(pid=None, con=None):
    own = con is None
    con = con or C["db"]()
    v = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id=?", (pid or current_pilot_id(),)).fetchone()[0]
    if own:
        con.close()
    return round(v, 2)


def add_tx(pid, kind, amount, description, pirep_id=None, con=None):
    own = con is None
    con = con or C["db"]()
    con.execute("INSERT INTO wallet (pilot_id, time, kind, amount, description, pirep_id) VALUES (?,?,?,?,?,?)",
                (pid, time.time(), kind, round(amount, 2), description, pirep_id))
    if own:
        con.commit()
        con.close()


def flight_pay(block_min, rank, profit):
    rate = PAY_RATES.get(rank, 55)
    hours = (block_min or 0) / 60
    share = max(0.0, profit or 0) * PROFIT_SHARE
    return {"rate": rate, "hours": round(hours, 2), "flight_pay": round(hours * rate, 2), "profit_share": round(share, 2),
            "total": round(hours * rate + share, 2), "share_pct": PROFIT_SHARE * 100}


def skill_bonus(p):
    """Extra pay for flying well. Each item is independent; the best flights earn all of them."""
    if p.get("status") == "Failed" or p.get("demo"):
        return []
    items = []
    g = p.get("grade")
    if g == "A":
        items.append(("Grade A flight", 150))
    elif g == "B":
        items.append(("Grade B flight", 50))
    rate, bounces = p.get("landing_rate"), p.get("bounces") or 0
    if rate is not None and bounces == 0:
        if rate >= -100:
            items.append((f"Butter landing ({rate:.0f} fpm)", 100))
        elif rate >= -200:
            items.append((f"Smooth landing ({rate:.0f} fpm)", 40))
    tb, plan = p.get("trip_burn_lbs"), p.get("planned_trip_lbs")
    if tb and plan and abs(tb - plan) / plan <= 0.03:
        items.append(("Fuel within 3% of plan", 75))
    if any(str(x[0]).startswith("On-time") for x in (p.get("breakdown") or []) if isinstance(x, (list, tuple)) and x):
        items.append(("On time", 50))
    if (p.get("landing_analysis") or {}).get("stable") is True:
        items.append(("Stable approach", 50))
    if not p.get("flags"):
        items.append(("Clean flight, no review flags", 50))
    return [{"label": l, "amount": a} for l, a in items]


def add_skill(pay, p):
    sk = skill_bonus(p)
    pay["skill"] = sk
    pay["skill_total"] = sum(x["amount"] for x in sk)
    pay["total"] = round(pay["total"] + pay["skill_total"], 2)
    return pay


def pay_pirep(pirep_id):
    """Credits flight pay and profit share for an accepted PIREP (once), then lets the Discord bot know."""
    pay = _pay_pirep(pirep_id)
    if pay is not None:
        try:
            import shop
            shop.pay_gear_bonus(pirep_id)          # PAC shop gear: a little extra on every flight
        except Exception as e:
            print(f"Gear bonus skipped: {e}")
    if pay is not None and C.get("on_pirep_accepted"):
        try:
            C["on_pirep_accepted"](pirep_id)
        except Exception as e:
            print(f"Discord announcement skipped: {e}")
    return pay


def _pay_pirep(pirep_id):
    with C["db"]() as con:
        r = con.execute("SELECT * FROM pireps WHERE id=?", (pirep_id,)).fetchone()
        if not r or r["demo"] or r["review_status"] != "Accepted":
            return None
        if con.execute("SELECT 1 FROM wallet WHERE pirep_id=? AND kind IN ('flight_pay','profit_share')", (pirep_id,)).fetchone():
            return None
        d = json.loads(r["detail"] or "{}")
        if d.get("training") and r["category"] not in ("Checkride", "Type checkride"):
            return None
        rank = d.get("pilot_rank") or career(r["pilot_id"], con)["rank"]
        job = d.get("job") or {}
        perf = {"grade": r["grade"], "landing_rate": r["landing_rate"], "bounces": d.get("bounces"), "trip_burn_lbs": d.get("trip_burn_lbs"),
                "planned_trip_lbs": d.get("planned_trip_lbs"), "breakdown": d.get("breakdown"), "landing_analysis": d.get("landing_analysis"),
                "flags": json.loads(r["flags"] or "[]"), "status": r["status"], "demo": r["demo"]}

        def pay_skill(pay):
            cz = d.get("conflict") or {}
            if cz.get("level") == "caution" and cz.get("pct"):       # hazard pay for caution areas (conflict zones)
                hz = round((pay.get("flight_pay") or 0) * cz["pct"] / 100, 2)
                if hz > 0:
                    names = ", ".join(z["name"] for z in cz.get("zones", []))
                    add_tx(r["pilot_id"], "hazard_pay", hz, f"{r['flight_number']}: {cz['pct']}% hazard pay ({names})", pirep_id, con)
                    pay["hazard_pay"], pay["total"] = hz, round(pay["total"] + hz, 2)
            add_skill(pay, perf)
            if pay["skill_total"]:
                add_tx(r["pilot_id"], "skill_bonus", pay["skill_total"],
                       f"{r['flight_number']} flown well: " + ", ".join(x["label"] for x in pay["skill"]), pirep_id, con)
            return pay
        if job.get("contract"):
            pay = contract_pay(r["block_min"], rank, job.get("contract_bonus"), job.get("contract_rate_mult") or CONTRACT_RATE_MULT)
            add_tx(r["pilot_id"], "flight_pay", pay["flight_pay"], f"Contract {r['flight_number']} for {job.get('operator_name', 'partner')}: {pay['hours']:.1f} h at ${pay['rate']}/h", pirep_id, con)
            if pay["contract_bonus"]:
                add_tx(r["pilot_id"], "contract_bonus", pay["contract_bonus"], f"Crew shortage bonus from {job.get('operator_name', 'partner')}", pirep_id, con)
            return pay_skill(pay)
        pay = flight_pay(r["block_min"], rank, r["profit"])
        add_tx(r["pilot_id"], "flight_pay", pay["flight_pay"], f"{r['flight_number']} {r['dep']}-{r['arr']}: {pay['hours']:.1f} h at ${pay['rate']}/h", pirep_id, con)
        if job.get("ferry_bonus"):
            add_tx(r["pilot_id"], "ferry_bonus", job["ferry_bonus"], f"Ferry bonus {r['flight_number']}", pirep_id, con)
            pay["total"] += job["ferry_bonus"]
        if pay["profit_share"] > 0:
            add_tx(r["pilot_id"], "profit_share", pay["profit_share"], f"{r['flight_number']}: {PROFIT_SHARE * 100:.0f}% of ${r['profit']:,.0f} profit", pirep_id, con)
        return pay_skill(pay)


def backpay():
    """Pays any accepted PIREP that hasn't been paid yet (e.g. flights filed before pay existed). Safe to run repeatedly."""
    with C["db"]() as con:
        ids = [r[0] for r in con.execute("""SELECT p.id FROM pireps p WHERE p.demo=0 AND p.review_status='Accepted'
            AND NOT EXISTS (SELECT 1 FROM wallet w WHERE w.pirep_id=p.id AND w.kind='flight_pay') ORDER BY p.filed_at""")]
    return [pay_pirep(i) for i in ids]


def _passes(pid):
    try:
        with C["db"]() as con:
            r = con.execute("SELECT qty FROM shop_owned WHERE pilot_id=? AND item='jumpseat_pass'", (pid,)).fetchone()
        return r["qty"] if r else 0
    except Exception:
        return 0


def jumpseat_options(frm, to, pid=None):
    a, b = C["airport_obj"](frm), C["airport_obj"](to)
    if not a or not b:
        raise ValueError("Choose an airport from the list.")
    if a["icao"] == b["icao"]:
        raise ValueError(f"You're already at {b['icao']}.")
    dist = C["gc_distance_nm"](a["lat"], a["lon"], b["lat"], b["lon"])
    stations = {r["origin"]["icao"] for r in C["ROUTES"].values()} | {r["destination"]["icao"] for r in C["ROUTES"].values()}
    direct = any(r["origin"]["icao"] == a["icao"] and r["destination"]["icao"] == b["icao"] for r in C["ROUTES"].values())
    opts = []
    if direct or (a["icao"] in stations and b["icao"] in stations):
        j = JUMPSEAT["pac"]
        opts.append({"kind": "pac", "label": j["label"], "cost": round(j["base"] + j["per_nm"] * dist),
                     "note": "Direct on a PAC route" if direct else "Via the PAC network"})
    for pk, pt in C["PARTNERS"].items():
        if a["icao"] in pt["network"] and b["icao"] in pt["network"]:
            j = JUMPSEAT["partner"]
            opts.append({"kind": f"partner:{pk}", "label": f"Jumpseat on {'an' if pt['name'][0] in 'AEIOU' else 'a'} {pt['name']} freighter", "logo": pt["logo"],
                         "cost": round(j["base"] + j["per_nm"] * dist), "note": f"Partner jumpseat agreement · {pt['name']} network"})
    j = JUMPSEAT["airline"]
    opts.append({"kind": "airline", "label": j["label"], "cost": round(j["base"] + j["per_nm"] * dist), "note": "Any airport, any time"})
    passes = _passes(pid) if pid else 0
    if passes:
        opts.insert(0, {"kind": "pass", "label": "Use a jumpseat pass", "cost": 0,
                        "note": f"From the PAC shop · you have {passes}"})
    return {"from": a, "to": b, "distance_nm": round(dist), "options": opts}


def jumpseat(pid, to, kind):
    frm = pilot_location(pid)
    q = jumpseat_options(frm, to, pid)
    opt = next((o for o in q["options"] if o["kind"] == kind), None)
    if not opt:
        raise ValueError("That travel option isn't available for this trip.")
    if kind == "pass":
        import shop
        with C["db"]() as con:
            if not shop.use_pass(con, pid):
                raise ValueError("You don't have a jumpseat pass left.")
            add_tx(pid, "jumpseat", 0, f"Jumpseat pass: {frm} to {q['to']['icao']} ({q['distance_nm']:,} nm)", None, con)
            con.execute("UPDATE pilots SET location=? WHERE id=?", (q["to"]["icao"], pid))
        return {"location": q["to"]["icao"], "cost": 0, "balance": balance(pid)}
    bal = balance(pid)
    if bal < opt["cost"]:
        raise ValueError(f"The trip costs ${opt['cost']:,} and your wallet has ${bal:,.0f}. Fly a flight from {frm} first, or ask staff for an advance.")
    with C["db"]() as con:
        add_tx(pid, "jumpseat", -opt["cost"], f"{opt['label']}: {frm} to {q['to']['icao']} ({q['distance_nm']:,} nm)", None, con)
        con.execute("UPDATE pilots SET location=? WHERE id=?", (q["to"]["icao"], pid))
    return {"location": q["to"]["icao"], "cost": opt["cost"], "balance": balance(pid)}


# ---------------------------------------------------------------- job board: generated cargo, ferry and contract flying
JOB_TEMPLATES = [
    # (kind, category, priority, cargo, title, briefing, load fraction range, heavy?)
    ("Racehorses", "Premium", "High", "Thoroughbred racehorses in stalls with grooms", "Racehorses to {city}",
     "A string of racehorses for a major meeting near {city}. Grooms travel with the animals. Smooth climbs and descents, and no hard braking.", (0.15, 0.3), False),
    ("Zoo", "Premium", "High", "Zoo animals for an international breeding program", "Zoo animals to {city}",
     "Rare animals moving between zoos for a breeding program. Keepers are on board and the hold is kept at a steady temperature.", (0.1, 0.25), False),
    ("Cattle", "Premium", "Standard", "Breeding cattle in livestock stalls", "Breeding cattle to {city}",
     "Pedigree breeding stock for a dairy cooperative near {city}. Ventilation is critical, so no long ground holds with the packs off.", (0.5, 0.8), False),
    ("Motorsport", "Express", "High", "Race cars, spares and team equipment for the Grand Prix", "Grand Prix freight to {city}",
     "The race weekend starts in days and the teams' cars, garages and spares all ride on this flight.", (0.55, 0.9), True),
    ("Teamkit", "Express", "High", "Pro sports team equipment and medical kit", "Team equipment to {city}",
     "A pro team plays away in {city} this weekend and its equipment flies ahead of the players. The equipment staff meet the aircraft.", (0.15, 0.35), False),
    ("Concert", "Express", "Standard", "Stadium tour staging, lighting and sound equipment", "Concert tour gear to {city}",
     "A world tour's stage rig for the next show in {city}. The load-in crew is waiting on the ramp.", (0.5, 0.85), True),
    ("Film", "Express", "Standard", "Film production cameras, lighting and grip equipment", "Film production gear to {city}",
     "A film crew starts shooting near {city} next week and their equipment is on this flight.", (0.3, 0.6), False),
    ("Art", "Premium", "High", "Museum exhibition artworks in climate-controlled crates", "Museum exhibition to {city}",
     "Priceless artworks on loan to a museum in {city}. Couriers accompany the crates. Gentle handling throughout.", (0.1, 0.25), False),
    ("Bullion", "Premium", "High", "Gold bullion and banknotes under armed escort", "Valuables to {city}",
     "A central bank shipment under escort. Security meets the aircraft on arrival.", (0.15, 0.35), False),
    ("Satellite", "Heavy lift", "High", "Communications satellite in a clean-room container", "Satellite to {city}",
     "An outsized clean-room container carrying a satellite bound for its launch site. No sharp maneuvers.", (0.3, 0.55), True),
    ("Turbine", "Heavy lift", "Standard", "Wind turbine gearbox and blade hub", "Wind turbine parts to {city}",
     "A failed gearbox has stopped a wind farm near {city}. The replacement is a single heavy piece.", (0.4, 0.7), True),
    ("Helicopter", "Heavy lift", "Standard", "Helicopter for an air ambulance operator", "Air ambulance helicopter to {city}",
     "A new air ambulance helicopter, rotors folded, for an operator in {city}.", (0.2, 0.4), True),
    ("Mining", "Heavy lift", "Standard", "Mining truck tires and heavy spares", "Mining spares to {city}",
     "A mine near {city} has trucks parked for want of tires and spares. Heavy, awkward pieces.", (0.6, 0.9), True),
    ("Wildfire", "Humanitarian", "Critical", "Wildfire suppression pumps, hoses and retardant equipment", "Wildfire equipment to {city}",
     "Wildfires are burning near {city}. Crews on the ground need this equipment today.", (0.5, 0.85), False),
    ("Shelter", "Humanitarian", "High", "Shelter, hygiene and cooking kits for a refugee camp", "Shelter kits to {city}",
     "A refugee camp near {city} is expanding fast. The NGOs have the kits staged and need lift.", (0.6, 0.9), False),
    ("Water", "Humanitarian", "High", "Water purification plant and generators after flooding", "Flood relief to {city}",
     "Floods have contaminated the water supply around {city}. A mobile purification plant is on this flight.", (0.5, 0.85), False),
    ("Polar", "Humanitarian", "Standard", "Research station resupply: food, fuel parts and science equipment", "Research station resupply via {city}",
     "Seasonal resupply for a remote research station, staged through {city}. Cold-weather operations.", (0.4, 0.7), False),
    ("MRI", "Medical", "High", "MRI scanner and hospital equipment", "Hospital equipment to {city}",
     "A new hospital wing in {city} is waiting on its MRI scanner. The magnet is sensitive to shock.", (0.2, 0.4), False),
    ("Radiopharma", "Medical", "Critical", "Radiopharmaceuticals with a short half-life", "Radiopharmaceuticals to {city}",
     "Medical isotopes for cancer treatment in {city}. They decay by the hour, so every minute counts.", (0.05, 0.15), False),
    ("Insulin", "Medical", "High", "Insulin and temperature-controlled medicines", "Medicines to {city}",
     "A shortage of insulin in {city}. The containers hold temperature for a limited time.", (0.2, 0.45), False),
    ("Semicon", "Express", "High", "Semiconductor manufacturing equipment", "Chip-fab equipment to {city}",
     "Lithography equipment for a new fab near {city}. Extremely valuable and sensitive to vibration.", (0.3, 0.6), True),
    ("Aerospace", "Express", "High", "Aircraft fuselage sections for a production line", "Aircraft sections to {city}",
     "Fuselage sections for an aircraft assembly line near {city}. The line stops if they're late.", (0.3, 0.6), True),
    ("Peak", "Express", "Standard", "Peak-season e-commerce overflow", "Peak-season parcels to {city}",
     "The sort center at {city} is overflowing with seasonal parcels. Extra lift requested tonight.", (0.6, 0.95), False),
    ("Harvest", "Express", "High", "Seasonal fruit harvest in cool containers", "Harvest to {city}",
     "Harvest is in and the fruit must reach {city} markets fresh.", (0.6, 0.9), False),
    ("Seafood", "Express", "High", "Live lobsters and fresh seafood on ice", "Live seafood to {city}",
     "Live seafood for restaurants in {city}. Every hour on the ground costs freshness.", (0.4, 0.75), False),
    ("Mail", "Express", "Standard", "Holiday mail surge", "Holiday mail to {city}",
     "Postal volumes have doubled. An extra section is flying mail to {city}.", (0.5, 0.85), False),
]
SHORTAGE_REASONS = [
    "a captain has called in sick", "the scheduled crew ran out of duty hours after yesterday's weather delays",
    "there's a training backlog on the type this month", "a crew is stuck positioning after a diversion",
    "peak season has stretched the roster thin", "two captains are away on recurrent simulator checks",
]


def _partners():
    return list(C["PARTNERS"].values())
JOBS_PER_DAY = {"cargo": 30, "ferry": 6, "contract": 12}
CONTRACT_RATE_MULT = 1.5
FERRY_BONUS = 150


def _fit_types(o, d, payload, dist, allowed=None):
    F = C["FLEET"]
    rwy = min(o.get("rwy_ft") or 99999, d.get("rwy_ft") or 99999)
    out = [k for k, v in F.items() if not v.get("retired") and (allowed is None or k in allowed)
           and v["range_nm"] >= dist * 1.05 and v["min_rwy_ft"] <= rwy and v["max_payload_lbs"] >= payload]
    return sorted(out, key=lambda k: F[k]["max_payload_lbs"])


def _day():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _day_end():
    d = dt.datetime.now(dt.timezone.utc)
    return (d.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)).timestamp()


def _next_job_id(con, used):
    for n in range(9600, 10000):
        jid = f"PAC{n}"
        if jid not in used and not con.execute("SELECT 1 FROM jobs WHERE id=? AND status IN ('open','booked')", (jid,)).fetchone():
            used.add(jid)
            return jid
    return None


def _cargo_job(rng, o, stations_all, big_airports, used, con):
    F = C["FLEET"]
    t = rng.choice(JOB_TEMPLATES)
    kind, cat, prio, cargo, title, brief, frac, heavy = t
    for _ in range(12):
        pool = big_airports if rng.random() < 0.4 else stations_all
        d = C["airport_obj"](rng.choice(pool))
        if not d or d["icao"] == o["icao"]:
            continue
        if kind == "Polar" and abs(d["lat"]) < 55:
            continue
        dist = C["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
        if dist < 150:
            continue
        lead = _fit_types(o, d, 0, dist)
        if heavy:
            lead = [k for k in lead if F[k]["max_payload_lbs"] >= 90000] or lead
        if not lead:
            continue
        base = rng.choice(lead[: max(1, len(lead) // 2 + 1)])
        payload = int(round(F[base]["max_payload_lbs"] * rng.uniform(*frac) / 500) * 500)
        fits = _fit_types(o, d, payload, dist)
        if not fits:
            continue
        jid = _next_job_id(con, used)
        city = d.get("city") or d["icao"]
        block = round(45 + dist / F[fits[0]]["cruise_ktas"] * 60 * 1.05)
        return {"id": jid, "title": title.format(city=city), "category": cat, "priority": prio, "job": True, "job_kind": "cargo",
                "job_type": kind, "origin": o, "destination": d, "aircraft": fits[:4], "cargo": cargo, "payload_lbs": payload,
                "distance_nm": round(dist), "target_block_min": block, "expires": _day_end(),
                "reward": int(round((dist * 0.14 + payload / 1000 * 1.2) * (1.2 if prio != "Standard" else 1.0) / 10) * 10),
                "briefing": brief.format(city=city) + f" {round(dist):,} nm, {payload:,} lb."}
    return None


def _ferry_job(rng, frame, used, con):
    F = C["FLEET"]
    o = C["airport_obj"](frame["location"])
    ac = F.get(frame["type"])
    if not o or not ac or ac.get("retired"):
        return None
    hubs = [h for h in ("KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC") if h != o["icao"]]
    rng.shuffle(hubs)
    for h in hubs:
        d = C["airport_obj"](h)
        dist = C["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
        if 150 < dist <= ac["range_nm"] * 0.95 and (d.get("rwy_ft") or 99999) >= ac["min_rwy_ft"]:
            why = rng.choice([f"for tomorrow's sort at {h}", f"for scheduled maintenance at {h}", f"to cover a busy week of departures from {h}",
                              f"to balance the fleet at {h}"])
            jid = _next_job_id(con, used)
            return {"id": jid, "title": f"Ferry {frame['reg']} to {d.get('city') or h}", "category": "Ferry", "priority": "Standard",
                    "job": True, "job_kind": "ferry", "origin": o, "destination": d, "aircraft": [frame["type"]], "suggested_airframe": frame["reg"],
                    "fixed_airframe": frame["reg"], "cargo": "Ferry flight (no cargo)", "payload_lbs": 0, "distance_nm": round(dist),
                    "target_block_min": round(45 + dist / ac["cruise_ktas"] * 60 * 1.05), "expires": _day_end(),
                    "reward": int(round(dist * 0.06 / 10) * 10) + 30, "ferry_bonus": FERRY_BONUS,
                    "briefing": f"Position {frame['reg']} ({ac['name']}) from {o['icao']} to {h} {why}. No cargo. Pays your hourly rate plus a ${FERRY_BONUS} ferry bonus."}
    return None


def _contract_job(rng, partner, regions, used, con, origin_icao=None, expires=None):
    """A partner is short of qualified crew for one rotation and hires a PAC captain to fly its aircraft under its callsign."""
    F = C["FLEET"]
    st = [x for x in partner["network"] if x in C["AIRPORTS"]]
    if len(st) < 2:
        return None
    o = C["airport_obj"](origin_icao or (partner["hub"] if rng.random() < 0.5 else rng.choice(st)))
    if not o:
        return None
    for _ in range(14):
        d = C["airport_obj"](rng.choice(st))
        if not d or d["icao"] == o["icao"]:
            continue
        dist = C["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
        types = _fit_types(o, d, 0, dist, allowed=partner["types"])
        if dist < 150 or not types:
            continue
        ac_code = types[0]
        payload = int(round(F[ac_code]["max_payload_lbs"] * rng.uniform(0.55, 0.9) / 500) * 500)
        types = _fit_types(o, d, payload, dist, allowed=partner["types"]) or [ac_code]
        lo, hi = partner.get("flight_range", [100, 9899])
        num = rng.randint(lo, hi)
        jid = f"{partner['code']}{num:03d}" if hi < 1000 else f"{partner['code']}{num}"
        if jid in used or con.execute("SELECT 1 FROM jobs WHERE id=? AND status IN ('open','booked')", (jid,)).fetchone():
            continue
        used.add(jid)
        block = round(45 + dist / F[types[0]]["cruise_ktas"] * 60 * 1.05)
        bonus = rng.choice([250, 400, 600, 800, 1000, 1500])
        reason = rng.choice(SHORTAGE_REASONS)
        return {"id": jid, "title": f"{partner['name']}: {o['icao']} to {d.get('city') or d['icao']}", "category": "Contract", "priority": "Standard",
                "job": True, "job_kind": "contract", "contract": True,
                "operator": {k: partner[k] for k in ("key", "code", "name", "callsign", "hub", "logo")}, "shortage_reason": reason,
                "origin": o, "destination": d, "aircraft": types, "cargo": rng.choice(__import__("missiongen").PARTNER_CARGO.get(partner["key"]) or
                                                                                      ["General cargo", "Express parcels", "E-commerce parcels", "Perishables"]),
                "payload_lbs": payload, "distance_nm": round(dist), "target_block_min": block, "expires": expires or _day_end(),
                "reward": int(round((dist * 0.12 + payload / 1000) / 10) * 10), "contract_bonus": bonus, "contract_rate_mult": CONTRACT_RATE_MULT,
                "briefing": (f"{partner['name']} is short of a qualified captain for this rotation: {reason}. They've hired a PAC pilot to fill in. "
                             f"You fly their {' or '.join(F[t]['name'] for t in types[:2])} under their callsign, {partner['callsign']} {num}. "
                             f"They pay {CONTRACT_RATE_MULT:g}× your PAC hourly rate plus a ${bonus:,} shortage bonus. Fly it in {partner['name']} livery if you have it.")}
    return None


def refresh_jobs_today(here=None):
    """Today's job board. Generated once per UTC day, topped up so there's always work where the pilot is."""
    import random
    day = _day()
    now = time.time()
    here = here or HOME_BASE
    with C["db"]() as con:
        con.execute("UPDATE jobs SET status='expired' WHERE status='open' AND day<? AND kind!='contract'", (day,))
        con.execute("DELETE FROM jobs WHERE status IN ('expired','completed') AND created < ?", (now - 14 * 86400,))
        have = con.execute("SELECT COUNT(*) FROM jobs WHERE day=?", (day,)).fetchone()[0]
        rng = random.Random(day + "|" + str(have))
        used = set()
        stations = sorted(_stations())
        big = [a["icao"] for a in C["AIRPORTS"].values() if a["size"] == "L" and (a["rwy_ft"] or 0) >= 8000]
        new = []
        if have == 0:
            origins = [here] * 5 + ["KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC"] * 2
            origins += [rng.choice(stations) for _ in range(JOBS_PER_DAY["cargo"] - len(origins))]
            for oc in origins:
                o = C["airport_obj"](oc)
                j = o and _cargo_job(rng, o, stations, big, used, con)
                if j:
                    new.append(j)
            import heavy_check
            for fr in [dict(r) for r in con.execute(f"SELECT reg, type, location FROM airframes WHERE status=? AND location NOT IN ({','.join('?' * len(heavy_check.MX_BASES))})",
                                                    (heavy_check.DUE, *heavy_check.MX_BASES))]:
                j = heavy_check.ferry_job(fr, C["airport_obj"], C["gc_distance_nm"], C["FLEET"], _next_job_id(con, used), _day_end(), FERRY_BONUS)
                if j:
                    new.append(j)
            frames = [dict(r) for r in con.execute("SELECT reg, type, location FROM airframes WHERE status='Available'")]
            rng.shuffle(frames)
            frames.sort(key=lambda f: f["location"] in ("KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC"))
            for fr in frames[: JOBS_PER_DAY["ferry"] * 2]:
                if sum(1 for j in new if j["job_kind"] == "ferry") >= JOBS_PER_DAY["ferry"]:
                    break
                j = _ferry_job(rng, fr, used, con)
                if j:
                    new.append(j)
        else:
            # make sure there's always something leaving from where the pilot is
            here_open = sum(1 for (d_,) in con.execute("SELECT data FROM jobs WHERE day=? AND status='open'", (day,))
                            if json.loads(d_)["origin"]["icao"] == here)
            o = C["airport_obj"](here)
            for _ in range(max(0, 3 - here_open)):
                j = o and _cargo_job(rng, o, stations, big, used, con)
                if j:
                    new.append(j)
        # The existing worker generates/publishes these alongside normal jobs.
        import short_heavy_jobs
        new.extend(short_heavy_jobs.generate(C, con, day, here, used, _next_job_id, _day_end(), new))
        for j in new:
            if j and j.get("id"):
                con.execute("INSERT OR REPLACE INTO jobs (id, day, kind, data, status, created) VALUES (?,?,?,?, 'open', ?)",
                            (j["id"], day, j["job_kind"], json.dumps(j), now))
        _partner_feed(con, now, here, used)
        rows = con.execute("SELECT data FROM jobs WHERE (day=? AND status='open') OR (kind='contract' AND status='open') OR (status='booked' AND pilot_id=?)",
                           (day, current_pilot_id())).fetchall()
    return [json.loads(r["data"]) for r in rows]


PARTNER_OPEN = (4, 8)           # partner crew requests open at any time: at least, at most
PARTNER_GAP_MIN = (45, 120)     # minutes between new requests once the minimum is met
PARTNER_HOURS = (8, 30)         # each request stays open this long


def _partner_feed(con, now, here, used):
    """Partner crew requests trickle in through the day instead of all at once; each has its own expiry."""
    import random
    open_rows = []
    for r in con.execute("SELECT id, data FROM jobs WHERE kind='contract' AND status='open'").fetchall():
        if (json.loads(r["data"]).get("expires") or 0) < now:
            con.execute("UPDATE jobs SET status='expired' WHERE id=?", (r["id"],))
        else:
            open_rows.append(json.loads(r["data"]))
    last = con.execute("SELECT id, data, created FROM jobs WHERE kind='contract' ORDER BY created DESC LIMIT 1").fetchone()
    last_t = last["created"] if last else 0
    want = 0
    if len(open_rows) < PARTNER_OPEN[0]:
        want = PARTNER_OPEN[0] - len(open_rows)
    elif len(open_rows) < PARTNER_OPEN[1]:
        span = PARTNER_GAP_MIN[1] - PARTNER_GAP_MIN[0]  # a different wait after each request, 45 to 120 minutes
        gap = (PARTNER_GAP_MIN[0] + (sum(ord(ch) * (i + 7) for i, ch in enumerate(last["id"])) * 2654435761) % (span + 1)) * 60
        if now - last_t >= gap:
            want = 1
    if not want:
        return
    rng = random.Random(f"{int(now) // 300}|{len(open_rows)}|{last['id'] if last else ''}")
    parts = _partners()
    last_partner = json.loads(last["data"])["operator"]["key"] if last else None
    per = {}
    for j in open_rows:
        per[j["operator"]["key"]] = per.get(j["operator"]["key"], 0) + 1
    made = 0
    for _ in range(want * 4):            # a partner can come up empty (no rotation fits), so try another
        if made >= want:
            break
        choices = [p for p in parts if p["key"] != last_partner and per.get(p["key"], 0) < 2] or parts
        p = rng.choice(choices)
        start = here if here in p["network"] and rng.random() < 0.5 else None
        j = _contract_job(rng, p, {}, used, con, start, expires=now + rng.uniform(*PARTNER_HOURS) * 3600)
        if j:
            made += 1
            j["created"] = now
            con.execute("INSERT OR REPLACE INTO jobs (id, day, kind, data, status, created) VALUES (?,?,?,?, 'open', ?)",
                        (j["id"], _day(), "contract", json.dumps(j), now))
            last_partner = p["key"]
            per[p["key"]] = per.get(p["key"], 0) + 1


def job_by_id(jid):
    with C["db"]() as con:
        r = con.execute("SELECT data, status FROM jobs WHERE id=?", (jid,)).fetchone()
    return (json.loads(r["data"]), r["status"]) if r else (None, None)


def set_job_status(jid, status):
    with C["db"]() as con:
        con.execute("UPDATE jobs SET status=?, pilot_id=? WHERE id=?", (status, current_pilot_id(), jid))


def contract_pay(block_min, rank, bonus, mult=CONTRACT_RATE_MULT):
    rate = PAY_RATES.get(rank, 55) * mult
    hours = (block_min or 0) / 60
    return {"rate": round(rate), "hours": round(hours, 2), "flight_pay": round(hours * rate, 2), "profit_share": 0.0,
            "contract_bonus": bonus or 0, "total": round(hours * rate + (bonus or 0), 2), "share_pct": 0}


# ---------------------------------------------------------------- dynamic urgent missions
URGENT_MAX = 6
URGENT_IDS = range(9410, 9500)   # PAC9410-9499: clear of tours (9101-9405), rotations (9001-9099, 9501-9599) and jobs (9600+)
URGENT_EVERY_S = 40 * 60
URGENT_KINDS = [
    {"kind": "AOG", "title": "AOG: spare engine to {city}", "cargo": "Spare engine on transport stand and change tooling", "mult": 2.0,
     "load": (0.35, 0.6), "brief": "A customer airliner is grounded at {icao} with a failed engine. Every hour on the ground costs them a fortune. Get the spare there before the deadline."},
    {"kind": "Medical", "title": "Blood products to {city}", "cargo": "Blood products and plasma in temperature-controlled containers", "mult": 1.8,
     "load": (0.25, 0.45), "brief": "Hospitals in {city} are running short after a mass-casualty incident. The shipment is packed on dry ice with a hard expiry."},
    {"kind": "Production", "title": "Line-stop parts to {city}", "cargo": "Production line components", "mult": 1.8,
     "load": (0.4, 0.8), "brief": "A factory near {icao} stops its line tonight without these parts. Deliver before the shift change."},
    {"kind": "Relief", "title": "Flood relief for {city}", "cargo": "Water purification units, tarpaulins and food kits", "mult": 1.15,
     "load": (0.6, 0.9), "brief": "Flash floods overnight near {city}. NGOs have the relief pallets staged and need lift immediately."},
    {"kind": "Pharma", "title": "Vaccine top-up to {city}", "cargo": "Vaccines in active cold-chain containers", "mult": 1.8,
     "load": (0.2, 0.4), "brief": "A vaccination campaign in {city} is days from running out. The containers have limited hold-over time."},
    {"kind": "Marine", "title": "Ship's engine part to {city}", "cargo": "Turbocharger and engine spares for a container ship", "mult": 1.9,
     "load": (0.15, 0.35), "brief": "A container ship is stuck alongside at the port near {city} with a failed turbocharger, and the port is charging by the hour. A marine engineer will meet the aircraft.", "where": "port"},
    {"kind": "Power", "title": "Blackout: grid parts to {city}", "cargo": "Transformer bushings, switchgear and cable", "mult": 1.7,
     "load": (0.4, 0.75), "brief": "A substation failure has left much of {city} without power. The utility needs these parts to bring the grid back tonight."},
    {"kind": "Wildfire", "title": "Firefighting foam to {city}", "cargo": "Fire retardant concentrate, pumps and hoses", "mult": 1.2,
     "load": (0.5, 0.85), "brief": "Wildfires are threatening towns near {city} and the tankers are running out of retardant. Expect smoke and gusty winds on approach.", "where": "fire"},
    {"kind": "Antivenom", "title": "Antivenom to {city}", "cargo": "Antivenom and emergency medicines in cool boxes", "mult": 1.8,
     "load": (0.05, 0.15), "brief": "Hospitals around {city} have run out of antivenom after a spike in snakebite cases. A small load with a very big job.", "where": "tropics"},
    {"kind": "Rescue", "title": "Rescue team equipment to {city}", "cargo": "Search and rescue team kit, rescue dogs' crates and medical stock", "mult": 1.3,
     "load": (0.35, 0.6), "brief": "A building collapse in {city} has trapped people. An international rescue team is ready to go the moment their equipment lands."},
    {"kind": "Data", "title": "Servers for a failed data center in {city}", "cargo": "Replacement servers and storage arrays", "mult": 1.7,
     "load": (0.25, 0.5), "brief": "A fire has taken a data center near {city} offline, and banks and hospitals are running on backups. The replacement hardware must be in the racks tonight."},
    {"kind": "Sports", "title": "Team equipment to {city}: game tomorrow", "cargo": "Pro team equipment, uniforms and medical kit", "mult": 1.6,
     "load": (0.15, 0.35), "brief": "A pro team's equipment truck broke down on the way to the airport and the game in {city} is tomorrow. The equipment staff are waiting at the stadium.", "where": "team"},
    {"kind": "Racing", "title": "Race team spares to {city}", "cargo": "Spare chassis, gearboxes and pit equipment", "mult": 1.6,
     "load": (0.2, 0.45), "brief": "A team crashed both cars in practice and the race is tomorrow at {city}. The spares were built overnight: the mechanics are waiting at the circuit.", "where": "racing"},
]


# Some urgent requests only make sense in certain places or seasons: a container ship needs a seaport, a wildfire
# needs fire country in fire season, antivenom is a tropical need, a pro team plays in a big-league city.
URGENT_PORTS = {"KLAX", "KJFK", "KEWR", "KMIA", "KIAH", "KSEA", "KOAK", "KSFO", "KBWI", "KPHL", "KBOS", "EHAM", "LEBL", "LIRF",
                "LGAV", "LTFM", "OMDW", "OTHH", "OEJN", "OEDF", "OBBI", "OKKK", "WSSS", "WMKK", "VHHH", "ZSPD", "ZGSZ", "ZGGG",
                "ZSQD", "RKPK", "RKSI", "RJAA", "RJBB", "RCKH", "RCTP", "VTBS", "VABB", "OPKC", "VCBI", "VOMM", "FACT", "HKMO",
                "DNMM", "DGAA", "SBGL", "SBGR", "SAEZ", "SCEL", "SPJC", "MPTO", "YSSY", "YMML", "YBBN", "YPPH", "NZAA", "CYVR",
                "CYHZ", "CYUL", "PANC", "LPPT", "EGLL", "EGSS", "EGPD", "ENBR", "ENGM", "EKCH", "EFHK", "EETN"}
URGENT_FIRE = {"KLAX", "KSFO", "KBOI", "KDEN", "KPHX", "KSLC", "KSEA", "KPDX", "KOAK", "KSAN", "KABQ", "KLAS", "CYVR", "CYEG",
               "CYYC", "LGAV", "LPPT", "LEMD", "LEBL", "LIRF", "LICC", "LCLK", "YSSY", "YMML", "YBBN", "YPPH", "SCEL"}
URGENT_RACING = {"LIMC", "EBLG", "LHBP", "LOWW", "EHAM", "LEBL", "CYUL", "KMIA", "KLAS", "MMMX", "SBGR", "OBBI", "OEJN", "OTHH",
                 "WSSS", "RJBB", "ZSPD", "YMML", "UBBB", "KIND", "KCLT", "EGLL", "WMKK"}


def urgent_fits(kind, a, now=None):
    """Whether an urgent request of this kind makes sense at airport a (now: for seasonal ones)."""
    w = kind.get("where")
    if not w:
        return True
    icao, lat = a.get("icao"), a.get("lat") or 0
    if w == "port":
        return icao in URGENT_PORTS
    if w == "racing":
        return icao in URGENT_RACING
    if w == "tropics":
        return abs(lat) <= 25
    if w == "team":
        import missiongen
        return icao in missiongen.TEAM_CITY or icao in missiongen.VENUE_CITY
    if w == "fire":
        mo = dt.datetime.fromtimestamp(now or time.time(), dt.timezone.utc).month
        return icao in URGENT_FIRE and (mo in (6, 7, 8, 9, 10) if lat > 0 else mo in (11, 12, 1, 2, 3))
    return True


def _stations():
    st = {}
    for r in C["ROUTES"].values():
        for a in (r["origin"], r["destination"]):
            st[a["icao"]] = a
    return st


# ---------------------------------------------------------------- downloads center
DOWNLOAD_CATEGORIES = ["Livery", "Checklist", "Document", "Scenery", "Other"]
DOWNLOAD_MAX_MB = 2048
DOWNLOAD_DESC_MAX = 2000      # long enough for full install steps
DOWNLOAD_SIMS = ("", "MSFS", "MSFS 2024", "X-Plane")
DOWNLOAD_TYPES = (".zip", ".7z", ".rar", ".pdf", ".png", ".jpg", ".txt", ".json", ".ini", ".cfg", ".xml", ".docx", ".xlsx", ".mp4")


def _dl_dir():
    d = C["DATA"] / "downloads"
    d.mkdir(exist_ok=True)
    return d


def _filing_icao():
    import re as _re
    code = str(C["settings"]().get("filing_icao") or "").strip().upper()
    return code if _re.fullmatch(r"[A-Z]{3}", code) else "PGI"


def simbrief_sheet(code):
    """The values to set up a SimBrief airframe for a PAC aircraft type."""
    import dispatch as DP
    ac = C["FLEET"].get(code)
    if not ac:
        return None
    mtow = ac.get("mtow_lbs") or 0
    mzfw, mlw = DP.LIMITS.get(code, (round(mtow * .75, -2), round(mtow * .8, -2)))
    max_pl = ac.get("max_payload_lbs") or 0
    oew = int(max(round(mzfw - max_pl, -2), 0))
    with C["db"]() as con:
        regs = [r["reg"] for r in con.execute("SELECT reg FROM airframes WHERE type=? AND status!='Retired' ORDER BY reg", (code,))]
    return {"code": code, "name": ac["name"], "icao": ac.get("icao"), "simbrief_type": ac.get("simbrief_type") or ac.get("icao"),
            "simbrief_airframe": ac.get("simbrief_airframe") or "", "sim": ac.get("sim"), "airline": _filing_icao(), "callsign": "PAGANI", "oew_lbs": oew, "mzfw_lbs": int(mzfw), "mtow_lbs": int(mtow),
            "mlw_lbs": int(mlw), "max_payload_lbs": int(max_pl), "fuel_burn_pph": ac.get("fuel_burn_pph"), "cruise_ktas": ac.get("cruise_ktas"),
            "range_nm": ac.get("range_nm"), "registrations": regs}


@bp.get("/api/downloads")
def downloads_list():
    with C["db"]() as con:
        files = [dict(r) for r in con.execute("SELECT * FROM downloads ORDER BY category, uploaded DESC")]
    for f in files:
        f.pop("stored", None)
    acars = C["acars_downloads"]() if C.get("acars_downloads") else None
    return jsonify({"files": files, "categories": DOWNLOAD_CATEGORIES, "acars": acars,
                    "simbrief": [simbrief_sheet(k) for k, v in C["FLEET"].items() if not v.get("retired")]})


@bp.get("/api/downloads/<int:fid>/file")
def downloads_file(fid):
    from flask import send_from_directory
    with C["db"]() as con:
        r = con.execute("SELECT * FROM downloads WHERE id=?", (fid,)).fetchone()
        if not r or not (_dl_dir() / r["stored"]).exists():
            return jsonify({"error": "That file isn't available any more."}), 404
        con.execute("UPDATE downloads SET downloads=downloads+1 WHERE id=?", (fid,))
    return send_from_directory(_dl_dir(), r["stored"], as_attachment=True, download_name=r["filename"])


@bp.get("/api/downloads/simbrief/<code>.txt")
def downloads_simbrief(code):
    sh = simbrief_sheet(code)
    if not sh:
        return jsonify({"error": "No such aircraft type."}), 404
    f = lambda v: f"{v:,} lb" if isinstance(v, int) else str(v)
    lines = ["PAGANI AIR CARGO - SIMBRIEF AIRFRAME SHEET", f"{sh['name']} ({sh['icao']})", "=" * 48,
             f"SimBrief aircraft type   {sh['simbrief_type']}",
             f"SimBrief airframe ID     {sh['simbrief_airframe']}  (PAC's shared airframe: paste it as the aircraft type)" if sh.get("simbrief_airframe") else "",
             f"Airline code             {sh['airline']}", f"Callsign                 {sh['callsign']}",
             f"Empty weight (OEW)       {f(sh['oew_lbs'])}", f"Max zero fuel weight     {f(sh['mzfw_lbs'])}", f"Max takeoff weight       {f(sh['mtow_lbs'])}",
             f"Max landing weight       {f(sh['mlw_lbs'])}", f"Max payload              {f(sh['max_payload_lbs'])}",
             f"Typical fuel burn        {sh['fuel_burn_pph']:,} lb/h" if sh.get("fuel_burn_pph") else "", f"Cruise speed (TAS)       {sh['cruise_ktas']} kt" if sh.get("cruise_ktas") else "",
             f"Range                    {sh['range_nm']:,} nm" if sh.get("range_nm") else "",
             f"PAC registrations        {', '.join(sh['registrations']) or 'none yet'}", "",
             "In SimBrief: Account > Airframes > New airframe, choose the aircraft type, then enter these values.",
             "Weights are PAC's planning figures for flight simulation; your aircraft add-on may differ slightly.", "For flight simulation use only."]
    from flask import Response
    return Response("\r\n".join(l for l in lines if l is not None) + "\r\n", mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment; filename=PAC-SimBrief-{code}.txt"})


@bp.post("/api/staff/downloads")
def downloads_upload():
    import re as _re
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Choose a file to upload."}), 400
    ext = "." + f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in DOWNLOAD_TYPES:
        return jsonify({"error": f"That kind of file isn't accepted. Use one of: {' '.join(DOWNLOAD_TYPES)}"}), 400
    if (request.content_length or 0) > DOWNLOAD_MAX_MB * 1_048_576:
        return jsonify({"error": f"Files can be up to {DOWNLOAD_MAX_MB:,} MB."}), 400
    title = C["clean_text"](request.form.get("title") or f.filename, 120)
    cat = request.form.get("category") if request.form.get("category") in DOWNLOAD_CATEGORIES else "Other"
    safe = _re.sub(r"[^\w.\-]", "_", f.filename)[-120:]
    stored = f"{int(time.time())}-{safe}"
    path = _dl_dir() / stored
    f.save(path)
    with C["db"]() as con:
        con.execute("""INSERT INTO downloads (title, category, aircraft, sim, version, description, filename, stored, size, uploaded)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (title, cat, (request.form.get("aircraft") or "")[:20], (request.form.get("sim") or "")[:20],
                                               C["clean_text"](request.form.get("version") or "", 20), C["clean_text"](request.form.get("description") or "", DOWNLOAD_DESC_MAX),
                                               f.filename[-150:], stored, path.stat().st_size, time.time()))
    return downloads_list()


@bp.post("/api/staff/downloads/<int:fid>")
def downloads_edit(fid):
    b = request.json or {}
    with C["db"]() as con:
        if not con.execute("SELECT 1 FROM downloads WHERE id=?", (fid,)).fetchone():
            return jsonify({"error": "Not found."}), 404
        for k, n in (("title", 120), ("version", 20), ("description", DOWNLOAD_DESC_MAX)):
            if k in b:
                con.execute(f"UPDATE downloads SET {k}=? WHERE id=?", (C["clean_text"](b[k] or "", n), fid))
        if b.get("category") in DOWNLOAD_CATEGORIES:
            con.execute("UPDATE downloads SET category=? WHERE id=?", (b["category"], fid))
        if "aircraft" in b and (not b["aircraft"] or b["aircraft"] in C["FLEET"]):
            con.execute("UPDATE downloads SET aircraft=? WHERE id=?", (b["aircraft"] or "", fid))
        if "sim" in b and b["sim"] in DOWNLOAD_SIMS:
            con.execute("UPDATE downloads SET sim=? WHERE id=?", (b["sim"], fid))
    return downloads_list()


@bp.delete("/api/staff/downloads/<int:fid>")
def downloads_delete(fid):
    with C["db"]() as con:
        r = con.execute("SELECT stored FROM downloads WHERE id=?", (fid,)).fetchone()
        if r:
            (_dl_dir() / r["stored"]).unlink(missing_ok=True)
            con.execute("DELETE FROM downloads WHERE id=?", (fid,))
    return downloads_list()


# ---------------------------------------------------------------- station guides
def station_list(pilot_id):
    """PAC's stations: the route network, the hubs, partner hubs and anywhere the pilot has flown."""
    import stations as SG
    A = C["AIRPORTS"]
    codes = set(_stations()) | set(LIVE_HUBS) | {p["hub"] for p in C["PARTNERS"].values()} | set(SG.GUIDES)
    counts = {}
    with C["db"]() as con:
        for r in con.execute("SELECT dep, arr FROM pireps WHERE pilot_id=? AND demo=0 AND review_status!='Rejected'", (pilot_id,)):
            for i in (r["dep"], r["arr"]):
                counts[i] = counts.get(i, 0) + 1
    codes |= {i for i in counts if i in A}
    phub = {p["hub"]: p["name"] for p in C["PARTNERS"].values()}
    out = []
    for i in codes:
        a = A.get(i)
        if not a:
            continue
        out.append({"icao": i, "iata": a.get("iata"), "name": a["name"], "city": a.get("city"), "country": a.get("country"),
                    "continent": a.get("continent"), "hub": i in LIVE_HUBS, "main_hub": i == "KCVG", "partner_hub": phub.get(i),
                    "guide": i in SG.GUIDES, "visits": counts.get(i, 0)})
    return sorted(out, key=lambda x: (not x["main_hub"], not x["guide"], not x["hub"], -x["visits"], x["icao"]))


def station_detail(icao, pilot_id):
    import analysis
    import stations as SG
    A, F = C["AIRPORTS"], C["FLEET"]
    a = A.get(icao)
    if not a:
        return None
    rwys = []
    for r in analysis.runways(C["DATA"]).get(icao, []):
        length = r[10] or 0
        rwys.append({"ids": f"{r[0]}/{r[5]}", "length_ft": length, "width_ft": r[11], "headings": [round(r[3]), round(r[8])],
                     "ends": [[r[1], r[2]], [r[6], r[7]]],
                     "types": [F[k]["name"] for k, v in sorted(F.items(), key=lambda kv: kv[1]["max_payload_lbs"])
                               if not v.get("retired") and v["min_rwy_ft"] <= length]})
    rwys.sort(key=lambda x: -x["length_ft"])
    with C["db"]() as con:
        rows = [dict(r) for r in con.execute("""SELECT id, flight_number, dep, arr, filed_at, landing_rate, grade FROM pireps
            WHERE pilot_id=? AND demo=0 AND review_status!='Rejected' AND (dep=? OR arr=?) ORDER BY filed_at DESC""", (pilot_id, icao, icao))]
    arrivals = [r for r in rows if r["arr"] == icao and r["landing_rate"] is not None and r["landing_rate"] <= -20]
    best = max(arrivals, key=lambda r: r["landing_rate"]) if arrivals else None
    us = a.get("country") == "US"
    return {"icao": icao, "iata": a.get("iata"), "name": a["name"], "city": a.get("city"), "country": a.get("country"),
            "continent": a.get("continent"), "lat": a["lat"], "lon": a["lon"], "elev_ft": a.get("elev_ft"), "size": a.get("size"),
            "hub": icao in LIVE_HUBS, "partner_hubs": [p["name"] for p in C["PARTNERS"].values() if p["hub"] == icao],
            "runways": rwys, "guide": SG.GUIDES.get(icao), "stands": SG.PAC_STANDS.get(icao), "stand_map": stand_map(icao),
            "stand_source": SG.STAND_SOURCES.get(icao),
            "stats": {"flights": len(rows), "departures": sum(1 for r in rows if r["dep"] == icao), "arrivals": sum(1 for r in rows if r["arr"] == icao),
                      "last": rows[0] if rows else None, "best_landing": best},
            "charts": ([["FAA charts (AirNav)", f"https://www.airnav.com/airport/{icao}"]] if us else [])
            + [["ChartFox (free charts for simulation)", f"https://chartfox.org/{icao}"], ["SkyVector", f"https://skyvector.com/airport/{icao}"]]}


def stand_map(icao):
    """PAC's stands on the station map: [{stand, size, info, lat, lon, placed}]; 'placed' once staff have positioned them."""
    import stations as SG
    if icao not in SG.PAC_STANDS:
        return None
    custom = (C["load_json"](C["DATA"] / "stand_positions.json", {}) or {}).get(icao, {})
    rename = SG.OLD_STAND_NAMES.get(icao, {})
    custom = {rename.get(k, k): v for k, v in custom.items()}  # positions saved under old stand names still count
    pos = {**SG.STAND_POSITIONS.get(icao, {}), **custom}
    out = []
    for size, names in SG.PAC_STANDS[icao].items():
        for n in names:
            if n in pos:
                out.append({"stand": n, "size": size, "info": SG.STAND_INFO.get(size, ""), "lat": pos[n][0], "lon": pos[n][1],
                            "placed": n in custom or bool(SG.STAND_SOURCES.get(icao, {}).get("published") or SG.STAND_SOURCES.get(icao, {}).get("final"))})
    return sorted(out, key=lambda x: x["stand"])


def assign_stand(icao, aircraft, flight, which, reg=None):
    """PAC's stand for a flight at a station with PAC stands, sized for the aircraft: {"icao", "stand", "size", "info", "lat", "lon"}.
    A departure stand is where the aircraft is actually parked when PAC knows; otherwise a free stand of the right size.
    The arrival stand uses the same choice ACARS makes at top of descent, so what the pilot is shown at booking is what they get."""
    import random
    import stations as SG
    rng = random.Random(f"{flight}|{icao}" + ("|dep" if which == "dep" else ""))
    n = SG.stand_for(icao, aircraft, rng)
    if not n:
        return None
    all_stands = [x["stand"] for x in (stand_map(icao) or [])]
    with C["db"]() as con:
        parked = {r["stand"]: r["reg"] for r in con.execute(
            "SELECT reg, stand FROM airframes WHERE location=? AND stand IS NOT NULL AND status!='Retired'", (icao,))}
        mine = con.execute("SELECT stand FROM airframes WHERE reg=? AND location=?", (reg or "", icao)).fetchone() if reg else None
    if which == "dep" and mine and mine["stand"] in all_stands:
        n = mine["stand"]          # the aircraft is already parked here: start where you left it
    elif parked.get(n) and parked[n] != reg:
        order = "CDEF"
        need = order.index(SG.AIRCRAFT_CODE.get(aircraft, "D"))
        big = {x["stand"]: order.index(x["size"]) for x in (stand_map(icao) or []) if x["size"] in order}
        free = sorted((v, x) for x, v in big.items() if v >= need and not parked.get(x))  # big enough, smallest first
        if free:                   # another aircraft is on that stand: take a free one that fits
            n = rng.choice([x for v, x in free if v == free[0][0]])
    pos = {x["stand"]: x for x in (stand_map(icao) or [])}.get(n)
    return {"icao": icao, "stand": n, "size": pos["size"] if pos else None, "info": pos["info"] if pos else "",
            "lat": pos["lat"] if pos else None, "lon": pos["lon"] if pos else None}


@bp.post("/api/staff/stations/<icao>/stands")
def stand_map_save(icao):
    """Staff place PAC's stands on the satellite map."""
    icao = icao.upper()
    a = C["AIRPORTS"].get(icao)
    b = request.json or {}
    if not a or not stand_map(icao):
        return jsonify({"error": "This station has no PAC stands."}), 404
    names = {x["stand"] for x in stand_map(icao)}
    clean = {}
    for n, ll in (b.get("positions") or {}).items():
        try:
            lat, lon = float(ll[0]), float(ll[1])
        except (TypeError, ValueError, IndexError):
            return jsonify({"error": f"Stand {n}: bad position."}), 400
        if n not in names:
            return jsonify({"error": f"There's no stand {n} at {icao}."}), 400
        if C["gc_distance_nm"](a["lat"], a["lon"], lat, lon) > 4:
            return jsonify({"error": f"Stand {n} is too far from {icao}."}), 400
        clean[n] = [round(lat, 6), round(lon, 6)]
    allp = C["load_json"](C["DATA"] / "stand_positions.json", {}) or {}
    if b.get("reset"):
        allp.pop(icao, None)
    else:
        allp[icao] = {**allp.get(icao, {}), **clean}
    C["save_json"](C["DATA"] / "stand_positions.json", allp)
    return jsonify({"ok": True, "stand_map": stand_map(icao)})


@bp.get("/api/stations")
def stations_api():
    return jsonify(station_list(current_pilot_id()))


@bp.get("/api/stations/<icao>")
def station_api(icao):
    d = station_detail(icao.upper(), current_pilot_id())
    return jsonify(d) if d else (jsonify({"error": "No such airport."}), 404)


# ---------------------------------------------------------------- the living mission board
LIVE_BOARD_SIZE = 14            # open missions on the board (plus the line checkride)
LIVE_HERE_MIN = 3               # at least this many leave from where the pilot is
LIVE_DAYS = (1.5, 6.0)          # each mission is open for this many days
LIVE_NO_REPEAT_DAYS = 10        # the same scenario on the same route doesn't come back sooner
CLASSIC_SHARE = 0.2             # share of new slots that bring back a hand-written classic mission
LIVE_HUBS = ["KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC"]
PRIORITY_MULT = {"Standard": 1.0, "High": 1.15, "Critical": 1.3}


def _pick_type(rng, o, d, dist, size, allowed=None):
    """An aircraft of the right size for the work (small, medium or heavy) that can fly the leg."""
    types = _fit_types(o, d, 0, dist, allowed)
    if not types:
        return None
    n = len(types)
    third = max(1, n // 3)
    pool = types[:third] if size == "small" else types[-third:] if size == "heavy" else (types[third:n - third] or types)
    return rng.choice(pool)


def _recommend(lead, fits, n=3):
    """The lead type first, then the closest in size, with at least one type from the other simulator when one fits."""
    F = C["FLEET"]
    size = lambda k: abs(math.log(F[k]["max_payload_lbs"] / F[lead]["max_payload_lbs"]))  # noqa: E731
    others = sorted((k for k in fits if k != lead), key=size)
    out = [lead]
    other_sim = next((k for k in others if F[k].get("sim") != F[lead].get("sim")), None)
    if other_sim:
        out.append(other_sim)
    out += [k for k in others if k not in out]
    return out[:n]


def _fill(text, **kw):
    try:
        out = text.format(**kw)
    except (KeyError, IndexError):
        out = text
    return out[:1].upper() + out[1:]          # "the Bay Area's team…" still starts with a capital


def _scenario_mission(rng, scen, con, here, recent, origin=None):
    """One mission from a scenario, or None if no leg works (unknown airport, out of range, repeated route)."""
    import missiongen as MG
    A, F = C["AIRPORTS"], C["FLEET"]
    big = [i for i, a in A.items() if a.get("size") == "L" and (a.get("rwy_ft") or 0) >= 8000]
    for _ in range(14):
        oc = origin or (rng.choice([here] + LIVE_HUBS) if scen["from"] == MG.ANY else rng.choice(scen["from"]))
        o = C["airport_obj"](oc) if oc in A else None
        if not o:
            continue
        if scen["to"] == MG.ANY:
            for _ in range(30):
                dc = rng.choice(big)
                dd = C["gc_distance_nm"](o["lat"], o["lon"], A[dc]["lat"], A[dc]["lon"])
                if 250 <= dd <= 3500:
                    break
            else:
                continue
        else:
            dc = rng.choice(scen["to"])
        if dc == oc or dc not in A or f"{scen['key']}|{oc}|{dc}" in recent:
            continue
        d = C["airport_obj"](dc)
        dist = C["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
        if dist < 120:
            continue
        allowed = scen.get("types")
        lead = _pick_type(rng, o, d, dist, scen.get("size", "medium"), allowed)
        if not lead:
            continue
        ferry = bool(scen.get("ferry"))
        payload = 0 if ferry else max(2000, int(round(min(F[lead]["max_payload_lbs"] * rng.uniform(*scen["load"]),
                                                          scen.get("max_lbs", 10 ** 9) * rng.uniform(0.6, 1.0)) / 500) * 500))
        types = _fit_types(o, d, payload, dist, allowed)
        if not types:
            continue
        types = _recommend(lead, types)
        challenge = None
        if scen.get("challenge"):
            at = dc if dc in MG.CHALLENGES else oc if oc in MG.CHALLENGES else None
            if at:
                label, note = MG.CHALLENGES[at]
                challenge = {"icao": at, "label": label, "note": note}
        cargo = rng.choice(scen["cargo"])
        kw = {"o": oc, "d": dc, "team": (scen.get("teams") or {}).get(oc) or MG.TEAM_CITY.get(oc) or MG.PLACE.get(oc) or o.get("city") or o["name"],
              "oc": MG.PLACE.get(oc) or o.get("city") or o["name"],
              "dcity": MG.VENUE_CITY.get(dc) or MG.TEAM_CITY.get(dc) or MG.PLACE.get(dc) or d.get("city") or d["name"], "dc": MG.PLACE.get(dc) or d.get("city") or d["name"],
              "cargo": cargo.lower()[0] + cargo[1:] if cargo else "", "Cargo": cargo, "cargo_low": cargo[0].lower() + cargo[1:], "cargo_short": cargo.split(",")[0].split(" and ")[0].split(" (")[0].lower(),
              "month": dt.datetime.now(dt.timezone.utc).strftime("%B"), "challenge": challenge["note"] if challenge else ""}
        title = _fill(rng.choice(scen["titles"]), **kw)
        title = title[0].upper() + title[1:]
        block = round(45 + dist / F[types[0]]["cruise_ktas"] * 60 * 1.05)
        mult = PRIORITY_MULT.get(scen["priority"], 1) * (1.2 if challenge else 1)
        reward = int(min(900, max(150, round((dist * (0.2 if ferry else 0.3) + payload / 1000 * 1.2) * mult / 10) * 10)))
        m = {"title": title, "category": scen["category"], "priority": scen["priority"], "briefing": " ".join(_fill(rng.choice(scen["briefs"]), **kw).split()),
             "cargo": cargo, "origin": o, "destination": d, "payload_lbs": payload, "aircraft": types, "reward": reward,
             "target_block_min": block, "distance_nm": round(dist), "scenario": scen["key"], "region": "Live"}
        if ferry:
            m.update(ferry=True, ferry_bonus=FERRY_BONUS)
        if challenge:
            m["challenge"] = challenge
        if scen.get("handling"):
            m["handling"] = scen["handling"]
        if allowed:
            m["types_only"] = True     # a delivery or a retirement: only these types make sense
        return m
    return None


def _new_live_id(con, rng):
    for _ in range(200):
        mid = f"PAC{rng.randint(6000, 8999)}"
        if mid not in C["MISSIONS"] and mid not in C["ROUTES"] and not con.execute("SELECT 1 FROM live_missions WHERE id=?", (mid,)).fetchone():
            return mid
    return None


def refresh_mission_board(here=None):
    """The mission board: the line checkride plus a living set of missions that changes every few days."""
    import random
    import missiongen as MG
    now = time.time()
    here = here or HOME_BASE
    month = dt.datetime.now(dt.timezone.utc).month
    with C["db"]() as con:
        con.execute("UPDATE live_missions SET status='expired' WHERE status='open' AND expires < ?", (now,))
        con.execute("DELETE FROM live_missions WHERE status IN ('expired','completed') AND created < ?", (now - 30 * 86400,))
        open_ = [dict(r) for r in con.execute("SELECT * FROM live_missions WHERE status='open' ORDER BY created")]
        recent = {r[0] for r in con.execute("SELECT scenario_key FROM live_missions WHERE created > ?", (now - LIVE_NO_REPEAT_DAYS * 86400,))}
        need = LIVE_BOARD_SIZE - len(open_)
        if need > 0:
            rng = random.Random(f"{now // 600}|{len(open_)}|{here}")
            here_open = sum(1 for r in open_ if json.loads(r["data"])["origin"]["icao"] == here)
            in_season = [sc for sc in MG.SCENARIOS if not sc["months"] or month in sc["months"]]
            weights = [sc["weight"] * (1.6 if sc["months"] else 1.0) for sc in in_season]
            classics = [m for k, m in C["MISSIONS"].items() if k != CHECKRIDE_ID]
            tries = 0
            while need > 0 and tries < 80:
                tries += 1
                m = None
                if here_open < LIVE_HERE_MIN:
                    local = [sc for sc in in_season if sc["from"] == MG.ANY or here in sc["from"]]
                    if local:
                        m = _scenario_mission(rng, rng.choice(local), con, here, recent, origin=here)
                    if m:
                        here_open += 1
                elif classics and rng.random() < CLASSIC_SHARE:
                    c = rng.choice(classics)
                    key = f"classic|{c['id']}"
                    if key not in recent and not con.execute("SELECT 1 FROM live_missions WHERE id=? AND status IN ('open','booked')", (c["id"],)).fetchone():
                        m = {**c, "classic": True}
                else:
                    m = _scenario_mission(rng, rng.choices(in_season, weights)[0], con, here, recent)
                if not m:
                    continue
                key = f"classic|{m['id']}" if m.get("classic") else f"{m['scenario']}|{m['origin']['icao']}|{m['destination']['icao']}"
                mid = m["id"] if m.get("classic") else _new_live_id(con, rng)
                if not mid:
                    break
                expires = now + rng.uniform(*LIVE_DAYS) * 86400
                m.update(id=mid, live=True, created=now, expires=expires)
                con.execute("INSERT OR REPLACE INTO live_missions (id, data, scenario_key, created, expires, status) VALUES (?,?,?,?,?, 'open')",
                            (mid, json.dumps(m), key, now, expires))
                recent.add(key)
                need -= 1
        rows = con.execute("SELECT data FROM live_missions WHERE status='open' OR (status='booked' AND pilot_id=?) ORDER BY created DESC",
                           (current_pilot_id(),)).fetchall()
    board = [json.loads(r["data"]) for r in rows]
    ck = C["MISSIONS"].get(CHECKRIDE_ID)
    return ([ck] if ck else []) + board


def live_mission(mid, any_status=False):
    """A live mission by id: open or booked (to book or fly it), or any status (for history)."""
    with C["db"]() as con:
        r = con.execute("SELECT data FROM live_missions WHERE id=?" + ("" if any_status else " AND status IN ('open','booked')"), (mid,)).fetchone()
    return json.loads(r["data"]) if r else None


def set_live_status(mid, status):
    with C["db"]() as con:
        con.execute("UPDATE live_missions SET status=?, pilot_id=? WHERE id=?", (status, current_pilot_id(), mid))


def _make_urgent(con, rng, now):
    taken = [json.loads(r["data"]) for r in con.execute("SELECT data FROM urgent WHERE status IN ('open','booked')")]
    used_regs = {t.get("suggested_airframe") for t in taken}
    used_origins = {t["origin"]["icao"] for t in taken}
    used_types = {t["aircraft"][0] for t in taken}
    frames = [dict(r) for r in con.execute("SELECT reg, type, location FROM airframes WHERE status='Available'")
              if r["reg"] not in used_regs and r["location"] not in used_origins]
    frames.sort(key=lambda f: (f["type"] in used_types, rng.random()))
    stations = _stations()
    for fr in frames:
        o = C["airport_obj"](fr["location"])
        ac = C["FLEET"].get(fr["type"])
        if not o or not ac:
            continue
        cands = [a for a in stations.values() if a["icao"] != o["icao"]
                 and 250 <= C["gc_distance_nm"](o["lat"], o["lon"], a["lat"], a["lon"]) <= ac["range_nm"] * 0.85]
        if not cands:
            continue
        k = rng.choice(URGENT_KINDS)
        fit = [a for a in cands if urgent_fits(k, a, now)]
        if not fit:                       # nowhere in range suits this kind: pick one that fits anywhere
            k = rng.choice([x for x in URGENT_KINDS if not x.get("where")])
            fit = cands
        d = C["airport_obj"](rng.choice(fit)["icao"])
        if not d or (d.get("rwy_ft") and d["rwy_ft"] < ac["min_rwy_ft"]):
            continue
        dist = C["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
        block = round(45 + dist / ac["cruise_ktas"] * 60 * 1.05)
        payload = int(round(ac["max_payload_lbs"] * rng.uniform(*k["load"]) / 500) * 500)
        expires = now + rng.randint(3 * 60, 9 * 60) * 60
        deliver_by = expires + block * 60 + rng.choice([45, 60, 75, 90, 120]) * 60
        # a free number: not open or booked, and not used in the last two days (so recent PIREPs stay unambiguous)
        busy = {r[0] for r in con.execute("SELECT id FROM urgent WHERE status IN ('open','booked') OR created > ?", (now - 2 * 86400,))}
        free = [n for n in URGENT_IDS if f"PAC{n}" not in busy]
        if not free:
            return None
        n = rng.choice(free)
        con.execute("DELETE FROM urgent WHERE id=?", (f"PAC{n}",))   # an old, finished request with the same number
        city = d.get("city") or d["icao"]
        m = {"id": f"PAC{n}", "title": k["title"].format(city=city, icao=d["icao"]), "category": "Urgent", "priority": "Critical",
             "urgent": True, "urgent_kind": k["kind"], "origin": o, "destination": d, "aircraft": [fr["type"]], "suggested_airframe": fr["reg"],
             "cargo": k["cargo"], "payload_lbs": payload, "distance_nm": round(dist), "target_block_min": block,
             "reward": int(round((dist * 0.14 + payload / 1000 * 1.2) * 1.5 / 10) * 10), "yield_mult": k["mult"],
             "expires": expires, "deliver_by": deliver_by,
             "briefing": k["brief"].format(city=city, icao=d["icao"]) + f" {fr['reg']} ({ac['name']}) is available at {o['icao']}."}
        con.execute("INSERT INTO urgent (id, data, created, expires, status) VALUES (?,?,?,?, 'open')", (m["id"], json.dumps(m), now, expires))
        return m
    return None


def refresh_urgent_missions(here=None):
    """Open urgent requests; expires old ones and trickles in new ones (up to URGENT_MAX at a time)."""
    import random
    now = time.time()
    with C["db"]() as con:
        con.execute("UPDATE urgent SET status='expired' WHERE status='open' AND expires < ?", (now,))
        con.execute("DELETE FROM urgent WHERE status IN ('expired','completed') AND created < ?", (now - 30 * 86400,))
        rows = con.execute("SELECT data, created FROM urgent WHERE status='open' ORDER BY created").fetchall()
        last = con.execute("SELECT MAX(created) FROM urgent").fetchone()[0] or 0
        rng = random.Random(int(now * 1000))
        if len(rows) < URGENT_MAX and (not rows or now - last >= URGENT_EVERY_S):
            for _ in range(2 if not rows else 1):
                if _make_urgent(con, rng, now):
                    rows = con.execute("SELECT data, created FROM urgent WHERE status='open' ORDER BY created").fetchall()
        return [json.loads(r["data"]) for r in rows]


def urgent_by_id(mid):
    with C["db"]() as con:
        r = con.execute("SELECT data, status FROM urgent WHERE id=?", (mid,)).fetchone()
    return (json.loads(r["data"]), r["status"]) if r else (None, None)


def set_urgent_status(mid, status):
    with C["db"]() as con:
        con.execute("UPDATE urgent SET status=?, pilot_id=? WHERE id=?", (status, current_pilot_id(), mid))


# ---------------------------------------------------------------- ranks
def type_unlock_rank(code):
    """The rank that unlocks an aircraft type: set by admins per type, otherwise the built-in ladder."""
    ac = C["FLEET"].get(code, {})
    if ac.get("unlock_rank") in [r["name"] for r in RANKS]:
        return ac["unlock_rank"]
    return next((r["name"] for r in RANKS if code in r["unlocks"]), "Second Officer")


def ranks_effective():
    live = [k for k, v in C["FLEET"].items() if not v.get("retired")]
    return [{**r, "unlocks": [k for k in live if type_unlock_rank(k) == r["name"]], "pay": PAY_RATES.get(r["name"])} for r in RANKS]


def pilot_record(pilot_id, con=None):
    own = con is None
    con = con or C["db"]()
    r = con.execute("SELECT * FROM pilots WHERE id=?", (pilot_id,)).fetchone()
    if own:
        con.close()
    return dict(r) if r else {"id": pilot_id, "name": pilot_id, "checkride": "Pending", "transfer_hours": 0}


def career(pilot_id, con=None):
    own = con is None
    con = con or C["db"]()
    p = pilot_record(pilot_id, con)
    rows = [dict(r) for r in con.execute(
        "SELECT block_min, score, filed_at "
        "FROM pireps WHERE pilot_id=? AND demo=0 AND review_status='Accepted' ORDER BY filed_at DESC", (pilot_id,))]
    last_ck = con.execute("SELECT filed_at, json_extract(detail, '$.checkride') AS ck FROM pireps WHERE pilot_id=? AND demo=0 AND mission_id=? "
                          "AND review_status!='Rejected' ORDER BY filed_at DESC LIMIT 1", (pilot_id, CHECKRIDE_ID)).fetchone()
    if own:
        con.close()
    last_attempt = None
    if last_ck:
        _ck = json.loads(last_ck["ck"] or "{}") or {}
        last_attempt = {"when": last_ck["filed_at"], "passed": bool(_ck.get("passed")), "reasons": _ck.get("reasons") or []}
    pac_hours = sum(r["block_min"] or 0 for r in rows) / 60
    hours = pac_hours + (p.get("transfer_hours") or 0)
    recent = [r for r in rows if r["score"] is not None][:AVG_WINDOW]
    avg = round(sum(r["score"] for r in recent) / len(recent), 1) if len(recent) >= AVG_MIN_FLIGHTS else None
    ck = p.get("checkride") in ("Passed", "Waived")

    def meets(rank):
        if rank["checkride"] and not ck:
            return False
        if hours < rank["hours"]:
            return False
        if rank["avg"] and (avg is None or avg < rank["avg"]):
            return False
        return True

    idx = 0
    for i, rk in enumerate(RANKS):
        if meets(rk):
            idx = i
        else:
            break
    earned = RANKS[idx]["name"]
    appointed = p.get("rank_override") if p.get("rank_override") in [r["name"] for r in RANKS] else None
    if appointed:
        idx = [r["name"] for r in RANKS].index(appointed)
    names = [r["name"] for r in RANKS]
    unlocked = [k for k, v in C["FLEET"].items() if not v.get("retired") and names.index(type_unlock_rank(k)) <= idx]
    if direct_entry():
        unlocked += [k for k in rated_types(pilot_id) if k not in unlocked]
    nxt = RANKS[idx + 1] if idx + 1 < len(RANKS) and not appointed else None
    need = []
    if nxt:
        if nxt["checkride"] and not ck:
            need.append({"label": "Pass the 737 line checkride or any type checkride" if direct_entry() else "Pass the 737 checkride", "done": False})
        if nxt["hours"]:
            need.append({"label": f"{nxt['hours']} hours", "done": hours >= nxt["hours"], "value": round(hours, 1), "target": nxt["hours"]})
        if nxt["avg"]:
            need.append({"label": f"Average score {nxt['avg']}+ over your last {AVG_WINDOW} flights", "done": avg is not None and avg >= nxt["avg"],
                         "value": avg, "target": nxt["avg"]})
    return {"pilot": p, "rank": RANKS[idx]["name"], "rank_index": idx, "appointed": bool(appointed), "earned_rank": earned, "next": nxt["name"] if nxt else None, "requirements": need,
            "hours": round(hours, 1), "pac_hours": round(pac_hours, 1), "transfer_hours": p.get("transfer_hours") or 0,
            "avg_score": avg, "flights": len(rows), "unlocked": unlocked, "checkride": p.get("checkride"), "checkride_last": last_attempt,
            "checkride_via": line_checkride_via(p)}


# ---------------------------------------------------------------- airframes
def heal_booked(con, now=None):
    """An airframe marked Booked with no open booking holding it (the booking was cancelled, expired or replaced
    without releasing it) goes back to Available. Ten minutes' grace so a booking being made right now is never touched."""
    now = now or time.time()
    held = set()
    for (data,) in con.execute("SELECT data FROM bookings"):
        try:
            reg = (json.loads(data or "null") or {}).get("airframe")
        except (TypeError, ValueError, AttributeError):
            continue
        if reg:
            held.add(reg)
    freed = []
    for r in con.execute("SELECT reg FROM airframes WHERE status='Booked' AND COALESCE(updated,0) < ?", (now - 600,)).fetchall():
        if r["reg"] not in held:
            con.execute("UPDATE airframes SET status='Available', updated=? WHERE reg=? AND status='Booked'", (now, r["reg"]))
            freed.append(r["reg"])
    if freed:
        print("Released airframes with no booking:", ", ".join(freed))
    return freed


def airframes(con=None):
    if con is None:
        enforce_overdue()
        try:
            with C["db"]() as hc:
                heal_booked(hc)
        except Exception as e:          # never let housekeeping break the fleet list
            print("heal_booked:", e)
    own = con is None
    con = con or C["db"]()
    rows = [dict(r) for r in con.execute("SELECT * FROM airframes ORDER BY type, reg")]
    items = {}
    for it in con.execute("SELECT id, reg, ata, description, severity, category, due FROM maint WHERE status='open' ORDER BY time"):
        items.setdefault(it["reg"], []).append({**dict(it), "ata_name": ATA.get(it["ata"], ""), "overdue": bool(it["due"] and it["due"] < time.time())})
    namers = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM pilots")}
    aog_open = {}
    try:
        import aog
        aog.init(con)
        for c in con.execute("SELECT * FROM aog_cases WHERE status IN ('awaiting_parts','repairing')"):
            k = json.loads(c["kit"] or "{}")
            aog_open[c["reg"]] = {"id": c["id"], "status": c["status"], "title": c["title"], "station": c["station"], "mission_id": c["mission_id"],
                                  "hub": c["hub"], "contractor": bool(c["contractor"]), "parts_due": c["parts_due"], "repair_until": c["repair_until"],
                                  "weight_lbs": k.get("weight_lbs"), "team": k.get("team"), "cause_flight": c["cause_flight"], "opened": c["opened"]}
    except Exception as e:
        print("AOG list:", e)
    for r in rows:
        r["open_items"] = items.get(r["reg"], [])
        r["aog"] = aog_open.get(r["reg"])
        if r.get("named_by"):
            r["named_by_name"] = namers.get(r["named_by"], r["named_by"])
    if own:
        con.close()
    for r in rows:
        r["check_due_in"] = round(A_CHECK_HOURS - (r["hours_since_check"] or 0), 1)
        r["heavy_due_in"] = round(__import__("heavy_check").HEAVY_CHECK_HOURS - (r.get("hours_since_heavy") or 0))
        a = C["AIRPORTS"].get(r["location"])
        r["lat"], r["lon"] = (a["lat"], a["lon"]) if a else (None, None)
    return rows


def check_booking(m, ac, reg, st):
    if m.get("type_checkride") or m.get("id") == CHECKRIDE_ID:
        return "Start this checkride from Career > Qualifications to choose company-funded training.", None
    """Returns (error, airframe_row). Enforces rank and airframe rules when switched on."""
    pid = current_pilot_id()
    if m.get("tour"):
        if ac not in m["aircraft"]:
            return f"This tour is flown with the {' or '.join(C['FLEET'][a]['name'] for a in m['aircraft'])}.", None
        prog = tour_progress(pid)[m["tour"]]
        if prog["next"] != m["id"]:
            return ("You've already flown this leg." if prog["next"] is None or m["leg"] <= prog["completed"]
                    else f"Fly leg {prog['completed'] + 1} of this tour first."), None
    if m.get("rotation"):
        if ac not in m["aircraft"]:
            return f"This rotation is flown with the {' or '.join(C['FLEET'][a]['name'] for a in m['aircraft'])}.", None
        prog = rotation_progress(pid)[m["rotation"]]
        if prog["next"] != m["id"]:
            return f"Fly leg {prog['completed'] + 1} of this rotation next.", None
    if m.get("types_only") and ac not in m["aircraft"]:
        return f"This flight is for the {' or '.join(C['FLEET'][a]['name'] for a in m['aircraft'])}.", None
    if m.get("contract") and ac not in m["aircraft"]:
        return f"{m['operator']['name']} flies this with the {' or '.join(C['FLEET'][a]['name'] for a in m['aircraft'])}.", None
    if m.get("job_kind") == "ferry" and ac not in m["aircraft"]:
        return f"This ferry is for {m['fixed_airframe']}, a {C['FLEET'][m['aircraft'][0]]['name']}.", None
    if m.get("job"):
        _jm, jstatus = job_by_id(m["id"])
        if jstatus != "open":
            return "This job is no longer available.", None
        if m.get("fixed_airframe") and reg and reg != m["fixed_airframe"]:
            return f"This ferry is for {m['fixed_airframe']}.", None
    if m.get("urgent"):
        um, status = urgent_by_id(m["id"])
        if status != "open" or time.time() > um["expires"]:
            return "This urgent request is no longer available.", None
    if m["id"] == CHECKRIDE_ID and ac != CHECKRIDE["aircraft"]:
        return "The checkride is flown on the 737-800BCF.", None
    if m.get("type_checkride") and rating_family(ac) != m["type_checkride"]:
        return f"This checkride is for the {m['type_checkride']} rating: fly it in the {' or '.join(C['FLEET'][a]['name'] for a in m['aircraft'])}.", None
    try:
        import shop
        fleet_pass = bool(shop.fleet_pass(pid)) and career(pid)["rank_index"] > 0    # after the line checkride
    except Exception:
        fleet_pass = False
    if (st.get("require_type_ratings", False) and not m.get("type_checkride") and m["id"] != CHECKRIDE_ID
            and not fleet_pass and rating_family(ac) not in type_ratings(pid)):
        fam = rating_family(ac)
        return (f"You need the {fam} type rating to fly the {C['FLEET'][ac]['name']}. Fly the {fam} checkride first: "
                f"Career › Type ratings."), None
    if st.get("enforce_pilot_location", True) and m["origin"]["icao"] != pilot_location(pid):
        here = pilot_location(pid)
        return (f"You're at {here}, and this flight leaves from {m['origin']['icao']}. Jumpseat to {m['origin']['icao']} first "
                f"(Missions › Jumpseat)."), None
    if st.get("enforce_ranks"):
        car = career(pid)
        de_check = bool(m.get("type_checkride")) and direct_entry()
        if m["id"] != CHECKRIDE_ID and car["rank_index"] == 0 and not de_check and ac not in rated_types(pid):
            return ("Pass your 737 checkride or obtain an accepted type checkride for this family before flying the line." if direct_entry() else "Pass your 737 checkride before flying the line."), None
        if m["id"] != CHECKRIDE_ID and ac not in car["unlocked"] and not fleet_pass and not de_check:
            need = type_unlock_rank(ac)
            return f"The {C['FLEET'][ac]['name']} unlocks at {need}. You're {car['rank']}.", None
    if m.get("contract"):
        return None, None  # the partner airline's aircraft, not a PAC airframe
    with C["db"]() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM airframes WHERE reg=?", (reg,)).fetchone() if reg else None
        if reg and not row:
            return f"Airframe {reg} isn't in the fleet.", None
        if row:
            row = dict(row)
            if row["type"] != ac:
                return f"{reg} is a {C['FLEET'][row['type']]['name']}, not a {C['FLEET'][ac]['name']}.", None
            import heavy_check
            if row["status"] != "Available" and not heavy_check.may_book(row, m):
                return f"{reg} is not available ({row['status'].lower()}).", None
            why = heavy_check.dispatch_problem(row, m, C["FLEET"], C["airport_obj"], C["gc_distance_nm"])
            if why:
                return why, None
            if st.get("enforce_airframes", True) and row["location"] != m["origin"]["icao"]:
                return f"{reg} is at {row['location']}, not {m['origin']['icao']}. Pick an aircraft that's there or ferry one in.", None
        elif st.get("enforce_airframes", True):
            return f"Choose an airframe at {m['origin']['icao']} for this flight.", None
        if row:
            con.execute("UPDATE airframes SET status='Booked', updated=? WHERE reg=?", (time.time(), reg))
    return None, row


def release_airframe(reg):
    if not reg:
        return
    with C["db"]() as con:
        con.execute("UPDATE airframes SET status='Available', updated=? WHERE reg=? AND status='Booked'", (time.time(), reg))


def nearest_airport(lat, lon, within=5):
    best, bd = None, within
    for a in C["AIRPORTS"].values():
        if abs(a["lat"] - lat) > 0.2:
            continue
        d = C["gc_distance_nm"](lat, lon, a["lat"], a["lon"])
        if d < bd:
            best, bd = a["icao"], d
    return best


# ---------------------------------------------------------------- PIREP enrichment
def enrich_pirep(p, booking, rec):
    """Adds bonuses, checkride result, review flags and the review decision to a PIREP draft."""
    m = booking["mission"]
    pid = current_pilot_id()
    bonuses = []
    base = p["points"]
    if p["status"] != "Failed" and not p.get("demo"):
        for e in active_events():
            if event_matches(e, m):
                bonuses.append([f"{e['name']} ×{e['multiplier']}", round(base * (e["multiplier"] - 1)), "event"])
        if m["id"] in featured_routes():
            bonuses.append([f"Featured route of the month ×{FEATURED_MULT}", round(base * (FEATURED_MULT - 1)), "featured"])
        if m.get("tour"):
            prog = tour_progress(pid)[m["tour"]]
            if prog["next"] == m["id"] and prog["completed"] + 1 == prog["total"]:
                t = next(t for t in TOURS if t["id"] == m["tour"])
                bonuses.append([f"Tour complete: {t['name']}", t["bonus"], "tour"])
        if m.get("rotation"):
            prog = rotation_progress(pid)[m["rotation"]]
            if prog["next"] == m["id"] and prog["completed"] + 1 == prog["total"]:
                r = next(r for r in ROTATIONS if r["id"] == m["rotation"])
                bonuses.append([f"Rotation complete: {r['name']}", r["bonus"], "tour"])
    if m.get("urgent") and not m.get("relief") and p["status"] != "Failed" and not p.get("demo"):   # relief flights earn no bonus
        on_time = bool(rec.oooi.get("in")) and rec.oooi["in"] <= m["deliver_by"] and p["status"] != "Diverted"
        p["urgent_on_time"] = on_time
        p["urgent"] = {"deliver_by": m["deliver_by"], "on_time": on_time}
        if on_time:
            bonuses.append(["Urgent delivery before the deadline ×1.5", round(base * 0.5), "urgent"])
    on = getattr(rec, "online", None)
    if on and on.get("checks") and not p.get("demo"):
        share = on.get("hits", 0) / on["checks"]
        p["online"] = {"network": on.get("network"), "callsign": on.get("callsign"), "share": round(share, 2), "checks": on["checks"]}
        if share >= 0.6 and p["status"] != "Failed":
            bonuses.append([f"Flown online on {on.get('network')} ×1.1", round(base * 0.1), "online"])
    p["bonuses"] = bonuses
    p["bonus_points"] = sum(b[1] for b in bonuses)
    p["base_points"] = base
    p["points"] = base + p["bonus_points"]

    # checkride
    if m["id"] == CHECKRIDE_ID:
        fails = []
        if booking["aircraft"] != CHECKRIDE["aircraft"]:
            fails.append("wrong aircraft type")
        if p["status"] not in ("Delivered", "Delivered late"):
            fails.append("did not arrive at the destination")
        if p["score"] < CHECKRIDE["min_score"]:
            fails.append(f"score below {CHECKRIDE['min_score']}")
        if p.get("landing_rate") is None or p["landing_rate"] < CHECKRIDE["min_rate"]:
            fails.append(f"landing firmer than {CHECKRIDE['min_rate']} fpm")
        if (p.get("landing_g") or 0) > CHECKRIDE["max_g"]:
            fails.append(f"landing load above {CHECKRIDE['max_g']} G")
        if (p.get("bounces") or 0) > 1:
            fails.append("multiple landing bounces")
        if any(e["kind"] == "slew" for e in rec.events):
            fails.append("position jump")
        p["checkride"] = {"passed": not fails, "reasons": fails}
    if m.get("type_checkride"):
        fam, fails = m["type_checkride"], []
        if rating_family(booking["aircraft"]) != fam:
            fails.append(f"flown in the wrong type (this checkride is for the {fam})")
        if p["status"] not in ("Delivered", "Delivered late"):
            fails.append("did not arrive at the destination")
        if p["score"] < TYPE_CHECKRIDE["min_score"]:
            fails.append(f"score below {TYPE_CHECKRIDE['min_score']}")
        if p.get("landing_rate") is None or p["landing_rate"] < TYPE_CHECKRIDE["min_rate"]:
            fails.append(f"landing firmer than {abs(TYPE_CHECKRIDE['min_rate'])} fpm")
        if (p.get("landing_g") or 0) > TYPE_CHECKRIDE["max_g"]:
            fails.append(f"landing load above {TYPE_CHECKRIDE['max_g']} G")
        if (p.get("bounces") or 0) > 1:
            fails.append("multiple landing bounces")
        landing_analysis = p.get("landing_analysis") or {}
        approach = landing_analysis.get("approach") or {}
        if (approach.get("ias_min") is not None and approach.get("ias_max") is not None
                and approach["ias_max"] - approach["ias_min"] > TYPE_CHECKRIDE["max_approach_speed_spread"]):
            fails.append("unstable approach")
        if approach.get("sustained_descent_500_fpm") is not None and (
                approach["sustained_descent_500_fpm"] < -TYPE_CHECKRIDE["max_sustained_descent_fpm"]):
            fails.append("unstable approach")
        if any(e["kind"] == "slew" for e in rec.events):
            fails.append("position jump")
        p["type_checkride"] = {"family": fam, "passed": not fails, "reasons": fails}

    # review flags
    flags = []
    if p.get("landing_rate") is not None and p["landing_rate"] < REVIEW["hard_landing_fpm"]:
        flags.append(f"Hard landing {p['landing_rate']} fpm")
    if (p.get("landing_g") or 0) > REVIEW["max_landing_g"]:
        flags.append(f"Landing load {p['landing_g']} G")
    if p["status"] in ("Diverted", "Failed"):
        flags.append(p["status"])
    if any(e["kind"] == "slew" for e in rec.events):
        flags.append("Position jump or slew")
    if (p.get("takeoff_analysis") or {}).get("tail_strike"):
        flags.append("Tail strike")
    integ = p.get("integrity") or {}
    if integ.get("paused_air_min", 0) >= 10:
        flags.append(f"Paused {integ['paused_air_min']:.0f} min in flight")
    if integ.get("accel_s", 0) >= 10:
        flags.append(f"Sim rate up to {integ.get('max_rate', 1):g}× for {integ['accel_s'] // 60:.0f} min {integ['accel_s'] % 60:.0f} s")
    if (p.get("bounces") or 0) > REVIEW["max_bounces"]:
        flags.append(f"{p['bounces']} bounces")
    if p["score"] < REVIEW["auto_accept_score"]:
        flags.append(f"Score {p['score']} below {REVIEW['auto_accept_score']}")
    p["flags"] = flags
    p["review_status"] = "Accepted" if (p.get("demo") or not flags) else "Pending"
    if m.get("training"):
        p["training"] = dict(m["training"])
        p.update(points=0, base_points=0, bonus_points=0, bonuses=[])
    return p


def after_file(p, booking, rec, pirep_id):
    """Moves the airframe, logs hours and cycles, grounds it if needed, records a checkride pass."""
    reg = booking.get("airframe")
    pid = current_pilot_id()
    tc = p.get("type_checkride") or {}
    bot_events = []
    with C["db"]() as con:
        # Commit the marker with these database effects so a retry cannot apply them twice.
        applied = con.execute("INSERT OR IGNORE INTO pirep_effects (pirep_id, applied) VALUES (?,?)",
                              (pirep_id, time.time())).rowcount == 1
        if applied:
            if tc.get("passed") and not p.get("demo") and p.get("review_status") == "Accepted" and p.get("status") in ("Delivered", "Delivered late"):
                record_accepted_type_pass(con, pirep_id)
            if reg and not p.get("demo"):
                loc = p["arr"] if p["arr"] in C["AIRPORTS"] else (nearest_airport(rec.last.lat, rec.last.lon) or booking["mission"]["origin"]["icao"])
                row = con.execute("SELECT * FROM airframes WHERE reg=?", (reg,)).fetchone()
                if row:
                    hrs = (p.get("flight_min") or 0) / 60
                    since = (row["hours_since_check"] or 0) + hrs
                    status, note = "Available", None
                    import aog
                    aog_kind = aog.classify(p.get("landing_rate"), p.get("landing_g"), (p.get("takeoff_analysis") or {}).get("tail_strike"))
                    touch = f"{p.get('landing_rate')} fpm, {p.get('landing_g') or 0:.2f} G"
                    if aog_kind == "structural":
                        status, note = "Damaged", f"Structural damage after a hard landing on {p['flight_number']} ({touch})"
                    elif aog_kind == "tail_strike":
                        status, note = "Inspection", f"Tail strike inspection after {p['flight_number']}"
                    elif aog_kind == "hard_landing":
                        status, note = "Inspection", f"Hard landing inspection after {p['flight_number']} ({touch})"
                    elif since >= A_CHECK_HOURS:
                        status, note = "A-check due", f"A-check due at {since:.0f} hours since last check"
                    import heavy_check
                    since_heavy = (row["hours_since_heavy"] or 0) + hrs if "hours_since_heavy" in row.keys() else 0
                    heavy = heavy_check.after_flight(since_heavy, loc, status, reg=row["reg"])
                    heavy_until = None
                    if heavy:
                        status, note, heavy_until = heavy
                    arr_st = (booking.get("arr_stand") or {})
                    parked = arr_st.get("stand") if arr_st.get("icao") == loc else None
                    con.execute("""UPDATE airframes SET location=?, status=?, hours=hours+?, cycles=cycles+1, hours_since_check=?,
                        last_flight=?, last_pilot=?, updated=?, note=?, stand=?, hours_since_heavy=?, heavy_until=? WHERE reg=?""",
                                (loc, status, hrs, since, p["flight_number"], pid, time.time(), note, parked, since_heavy, heavy_until, reg))
                    auto = {"Damaged": (5, note), "Inspection": (53 if "Tail strike" in (note or "") else 5, note), "A-check due": (5, note)}
                    if status in auto:
                        iid = create_item(con, reg, auto[status][0], auto[status][1], "grounding", source="acars", flight=p["flight_number"], pirep_id=pirep_id)
                        if aog_kind:   # grounded away from maintenance: recovery case and mission
                            try:
                                _case, ev = aog.open_case(con, reg, row["type"], loc, aog_kind, [iid], p["flight_number"], pirep_id, C)
                                if ev:
                                    bot_events.append(("aog_opened", ev))
                            except Exception as e:
                                print("AOG case:", e)
                    for f in getattr(rec, "faults", []) or []:
                        create_item(con, reg, f["ata"], f["description"], f["severity"], f.get("category", "C"), "pilot", p["flight_number"], pirep_id, f.get("t"))
                    if status == "Available" and con.execute("SELECT 1 FROM maint WHERE reg=? AND status='open' AND severity='grounding'", (reg,)).fetchone():
                        con.execute("UPDATE airframes SET status='Maintenance', note='Open grounding write-up', updated=? WHERE reg=?", (time.time(), reg))
            elif reg:
                con.execute("UPDATE airframes SET status='Available', updated=? WHERE reg=? AND status='Booked'", (time.time(), reg))
            if not p.get("demo") and p["arr"] != "UNKNOWN" and (m_training := booking["mission"].get("training", {})).get("mode") != "dedicated":
                con.execute("UPDATE pilots SET location=? WHERE id=?", (p["arr"] if p["arr"] in C["AIRPORTS"] else
                            (nearest_airport(rec.last.lat, rec.last.lon) or booking["mission"]["destination"]["icao"]), pid))
            if booking["mission"].get("job"):
                con.execute("UPDATE jobs SET status=? WHERE id=?", ("completed" if not p.get("demo") else "open", booking["mission"]["id"]))
            if booking["mission"].get("urgent"):
                con.execute("UPDATE urgent SET status=? WHERE id=?", ("completed" if not p.get("demo") else "open", booking["mission"]["id"]))
                if booking["mission"].get("aog_case") and not p.get("demo") and p.get("status") in ("Delivered", "Delivered late"):
                    import aog
                    ev = aog.parts_delivered(con, booking["mission"]["aog_case"], p["flight_number"], pid)
                    if ev:
                        prof = con.execute("SELECT name, discord_id FROM pilots WHERE id=?", (pid,)).fetchone()
                        ev.update({"pilot": prof["name"] if prof else pid, "discord_id": prof["discord_id"] if prof else None})
                        bot_events.append(("aog_parts", ev))
            if booking["mission"].get("live"):
                con.execute("UPDATE live_missions SET status=? WHERE id=?", ("completed" if not p.get("demo") else "open", booking["mission"]["id"]))
            if p.get("checkride", {}).get("passed") and not p.get("demo") and p.get("review_status") == "Accepted":
                mark_line_checkride_passed(con, pid)
    if tc.get("passed") and not p.get("demo") and p.get("review_status") == "Accepted" and p.get("status") in ("Delivered", "Delivered late"):
        note_rating_on_licence(pid, tc["family"], time.time())
    _emit_bot(bot_events)
    return pay_pirep(pirep_id)


def _emit_bot(events):
    """Bot events go out after the database transaction (the bot's log shares the database)."""
    if not events:
        return
    try:
        import botlink
        for kind, data in events:
            botlink.emit(kind, data)
    except Exception as e:
        print("bot event:", e)


# ---------------------------------------------------------------- awards and leaderboards
def badges(pilot_id):
    with C["db"]() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM pireps WHERE pilot_id=? AND demo=0 AND review_status='Accepted' ORDER BY filed_at", (pilot_id,))]
        p = pilot_record(pilot_id, con)
    ok = [r for r in rows if r["status"] != "Failed"]
    hours = sum(r["block_min"] or 0 for r in rows) / 60
    types = {r["aircraft"] for r in ok}
    arrivals = [C["AIRPORTS"].get(r["arr"]) for r in ok]
    continents = {a["continent"] for a in arrivals if a}
    visited = {i for r in ok for i in (r["dep"], r["arr"]) if i in C["AIRPORTS"]}
    countries = {C["AIRPORTS"][i]["country"] for i in visited}
    streak = best = 0
    for r in rows:
        streak = streak + 1 if r["grade"] == "A" else 0
        best = max(best, streak)
    relief = sum(1 for r in ok if r["category"] in ("Humanitarian", "Medical"))
    tours = tour_progress(pilot_id)
    laps = sum(x["laps"] for x in rotation_progress(pilot_id).values())
    have = {
        "rotation": (laps, 1), "rotations_5": (laps, 5),
        "first_flight": (len(ok), 1), "checkride": (1 if p.get("checkride") in ("Passed", "Waived") else 0, 1),
        "flights_10": (len(ok), 10), "flights_50": (len(ok), 50), "flights_100": (len(ok), 100),
        "hours_100": (round(hours, 1), 100), "hours_500": (round(hours, 1), 500),
        "butter": (1 if any(r["landing_rate"] is not None and r["landing_rate"] >= -100 for r in ok) else 0, 1),
        "streak_a": (best, 5), "relief_10": (relief, 10), "heavy": (1 if "B748F" in types else 0, 1),
        "all_types": (len(types & set(C["FLEET"])), len(C["FLEET"])),
        "himalaya": (1 if any(r["arr"] == "VNKT" for r in ok) else 0, 1),
        "arctic": (1 if any(a and a["lat"] >= 60 for a in arrivals) else 0, 1),
        "continents": (len(continents), 6),
        "airports_10": (len(visited), 10), "airports_25": (len(visited), 25), "airports_50": (len(visited), 50),
        "airports_100": (len(visited), 100), "countries_5": (len(countries), 5), "countries_10": (len(countries), 10),
        "countries_25": (len(countries), 25),
        "on_time_25": (sum(1 for r in ok if r["status"] == "Delivered"), 25),
        "event": (1 if any((r["bonus_points"] or 0) > 0 for r in ok) else 0, 1),
    }
    for t in TOURS:
        pr = tours[t["id"]]
        have[f"tour_{t['id']}"] = (pr["completed"], pr["total"])
    return [{"id": b, "name": n, "description": d, "value": have[b][0], "target": have[b][1], "earned": have[b][0] >= have[b][1]}
            for b, n, d in BADGES]


# ---------------------------------------------------------------- type ratings and type checkrides
def direct_entry():
    """Experienced pilots may take any type checkride without the rank or hours; passing it rates them on the family."""
    return bool(C["settings"]().get("direct_entry_checkrides", True))


def rated_types(pilot_id):
    """Aircraft a pilot may fly through a type rating earned by checkride or granted by staff (direct entry)."""
    if not direct_entry():
        return []
    fams = {f for f, r in type_ratings(pilot_id).items() if r["source"] == "staff" or (r["source"] == "checkride" and r.get("verified"))}
    return [k for k, v in C["FLEET"].items() if not v.get("retired") and rating_family(k) in fams]


def rating_family(code):
    ac = C["FLEET"].get(code, {})
    return ac.get("rating_family") or RATING_FAMILY.get(code) or ac.get("icao") or code


def family_types(fam):
    return [k for k, v in C["FLEET"].items() if not v.get("retired") and rating_family(k) == fam]


def rating_slug(fam):
    return "TR-" + "".join(ch if ch.isalnum() else "-" for ch in fam).strip("-")


def valid_type_pass(row, family=None):
    if not row or row["demo"] or row["review_status"] != "Accepted" or row["status"] not in ("Delivered", "Delivered late"):
        return False
    try:
        tc = json.loads(row["detail"] or "{}").get("type_checkride") or {}
        fam = tc.get("family")
        return bool(tc.get("passed") and fam and (family is None or family == fam)
                    and rating_family(row["aircraft"]) == fam and row["mission_id"] == rating_slug(fam))
    except (ValueError, TypeError, AttributeError):
        return False


def _line_via(con, pilot_id, fam):
    """Remember (on the pilot's prefs) which type checkride satisfied the line checkride; None clears it."""
    r = con.execute("SELECT prefs FROM pilots WHERE id=?", (pilot_id,)).fetchone()
    try:
        prefs = json.loads((r["prefs"] if r else None) or "{}")
    except (ValueError, TypeError):
        prefs = {}
    if not isinstance(prefs, dict):
        prefs = {}
    if fam:
        prefs["line_checkride_via"] = fam
    else:
        prefs.pop("line_checkride_via", None)
    con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(prefs), pilot_id))


def mark_line_checkride_passed(con, pilot_id):
    """Records the line checkride as passed. The first time, PAC also moves the pilot (free, like other company training
    travel) to the home base they chose when they applied, so a pilot who picked Milan or Hong Kong starts their career
    there rather than wherever the checkride happened to end."""
    row = con.execute("SELECT checkride, hub, location FROM pilots WHERE id=?", (pilot_id,)).fetchone()
    if not row or row["checkride"] in ("Passed", "Waived"):
        return False
    con.execute("UPDATE pilots SET checkride='Passed' WHERE id=?", (pilot_id,))
    hub = (row["hub"] or "").upper()
    if hub in C["AIRPORTS"] and row["location"] != hub \
            and not con.execute("SELECT 1 FROM bookings WHERE pilot_id=?", (pilot_id,)).fetchone():
        add_tx(pilot_id, "training_travel", 0, f"Company relocation to your home base after the line checkride: {row['location'] or '?'} to {hub}", None, con)
        con.execute("UPDATE pilots SET location=? WHERE id=?", (hub, pilot_id))
    return True


def line_checkride_via(pilot):
    """The type checkride family that counted as this pilot's line checkride, or None."""
    try:
        prefs = json.loads(pilot.get("prefs") or "{}")
        return prefs.get("line_checkride_via") if isinstance(prefs, dict) else None
    except (ValueError, TypeError, AttributeError):
        return None


def record_accepted_type_pass(con, report_id):
    row = con.execute("SELECT * FROM pireps WHERE id=?", (report_id,)).fetchone()
    if row and not row["demo"] and row["review_status"] == "Accepted" and row["status"] in ("Delivered", "Delivered late") and row["mission_id"] == CHECKRIDE_ID and row["aircraft"] == CHECKRIDE["aircraft"] and json.loads(row["detail"] or "{}").get("checkride", {}).get("passed"):
        mark_line_checkride_passed(con, row["pilot_id"])
        _line_via(con, row["pilot_id"], None)          # the real 737 line checkride: it grants the 737 qualification
    if valid_type_pass(row):
        fam = json.loads(row["detail"])["type_checkride"]["family"]
        current = con.execute("SELECT source FROM type_ratings WHERE pilot_id=? AND family=?", (row["pilot_id"], fam)).fetchone()
        if not current or current[0] != "staff":
            grant_rating(con, row["pilot_id"], fam, "checkride", row["score"], report_id)
        # a passed type checkride also counts as the line checkride (direct entry, as announced on 16 October),
        # without handing out a 737 rating the pilot never flew for
        ck = con.execute("SELECT checkride FROM pilots WHERE id=?", (row["pilot_id"],)).fetchone()
        if ck and ck["checkride"] not in ("Passed", "Waived"):
            mark_line_checkride_passed(con, row["pilot_id"])
            _line_via(con, row["pilot_id"], fam)


def type_ratings(pilot_id):
    """{family: how it was earned}. Earned by passing a type checkride, granted by staff, by the line checkride (737),
    or by having flown the type with PAC before ratings existed."""
    out = {}
    with C["db"]() as con:
        for r in con.execute("SELECT * FROM type_ratings WHERE pilot_id=?", (pilot_id,)):
            verified = False
            if r["source"] == "checkride" and r["pirep_id"]:
                report = con.execute("SELECT * FROM pireps WHERE id=? AND pilot_id=?", (r["pirep_id"], pilot_id)).fetchone()
                if not valid_type_pass(report, r["family"]):
                    continue
                verified = True
            out[r["family"]] = {"source": r["source"], "date": r["date"], "score": r["score"], "pirep_id": r["pirep_id"], "verified": verified}
        flown = con.execute("""SELECT aircraft, MIN(filed_at) FROM pireps WHERE pilot_id=? AND demo=0 AND review_status='Accepted'
            AND status!='Failed' AND COALESCE(category,'') NOT IN ('Checkride','Type checkride') GROUP BY aircraft""", (pilot_id,)).fetchall()
        p = pilot_record(pilot_id, con)
    for ac, first in flown:
        out.setdefault(rating_family(ac), {"source": "flown", "date": first, "score": None, "pirep_id": None})
    if p.get("checkride") in ("Passed", "Waived") and not line_checkride_via(p):   # satisfied by a type checkride: no 737 rating
        out.setdefault(rating_family(CHECKRIDE["aircraft"]), {"source": "line checkride", "date": None, "score": None, "pirep_id": None})
    return out


def ratings_overview(pilot_id, _career=None):
    """Every rating family: rated (and how), available (unlocked by rank: fly the checkride), or locked by rank."""
    rated = type_ratings(pilot_id)
    unlocked = set((_career if _career is not None else career(pilot_id))["unlocked"])
    fams = []
    for fam in dict.fromkeys(rating_family(k) for k, v in C["FLEET"].items() if not v.get("retired")):
        types = family_types(fam)
        open_types = [t for t in types if t in unlocked]
        need = None if open_types else min((type_unlock_rank(t) for t in types), key=lambda n: [r["name"] for r in RANKS].index(n))
        de = direct_entry() and not open_types
        fams.append({"family": fam, "types": types, "type_names": [C["FLEET"][t]["name"] for t in types], "rated": rated.get(fam),
                     "unlocked": bool(open_types) or de, "direct_entry": de, "unlock_rank": need, "checkride_id": rating_slug(fam)})
    return fams


_CK_CANDS = {}   # (start airport, runway length, any-size?, airport count) -> checkride destinations in range


def checkride_mission(pilot_id, mission_id, origin=None, aircraft=None, _career=None):
    """The type checkride for a family: a short company sector (250-1,000 nm) in that type, from where the pilot is.
    A real PAC route when one fits; otherwise a sector to a large airport 300-700 nm away with a long enough runway."""
    fam = next((f for f in dict.fromkeys(rating_family(k) for k in C["FLEET"]) if rating_slug(f) == mission_id), None)
    if not fam:
        return None
    types = family_types(fam)
    unlocked = ([aircraft] if aircraft in types else []) if aircraft else ([t for t in types if t in (_career if _career is not None else career(pilot_id))["unlocked"]] or types)
    if not unlocked: return None
    here = origin or pilot_location(pilot_id)
    with C["db"]() as con:
        local_types = {r[0] for r in con.execute("SELECT type FROM airframes WHERE location=? AND status='Available'", (here,))}
    unlocked.sort(key=lambda t: t not in local_types)
    lead = C["FLEET"][unlocked[0]]
    min_rwy = max(C["FLEET"][t].get("min_rwy_ft") or 6000 for t in unlocked)
    A = C["AIRPORTS"]
    lo, hi = (100, 1000) if aircraft else (TYPE_CHECKRIDE["min_nm"], TYPE_CHECKRIDE["max_nm"])
    seed = sum(map(ord, pilot_id + fam))
    routes = sorted((r for r in C["ROUTES"].values() if r["origin"]["icao"] == here and any(t in r["aircraft"] for t in unlocked)
                     and (A.get(r["destination"]["icao"], {}).get("rwy_ft") or 0) >= min_rwy
                     and lo <= (r.get("distance_nm") or 0) <= hi), key=lambda r: r["id"])
    if routes:
        base = dict(routes[seed % len(routes)])
    else:
        # the pilot's airport if its runway suits the type, otherwise the nearest PAC hub that does
        start = here if (A.get(here, {}).get("rwy_ft") or 0) >= min_rwy else min(
            (h for h in DELIVERY_HUBS_LIST if (A.get(h, {}).get("rwy_ft") or 0) >= min_rwy and h in A),
            key=lambda h: C["gc_distance_nm"](A[here]["lat"], A[here]["lon"], A[h]["lat"], A[h]["lon"]) if here in A else 0)
        o = A[start]
        ck_key = (start, min_rwy, bool(aircraft), len(A))
        cands = _CK_CANDS.get(ck_key)
        if cands is None:   # the airports in range never change, so work them out once per start airport and runway length
            cands = sorted((i for i, a in A.items() if i != start and (aircraft or a.get("size") == "L") and (a.get("rwy_ft") or 0) >= min_rwy
                            and (100 if aircraft else 300) <= C["gc_distance_nm"](o["lat"], o["lon"], a["lat"], a["lon"]) <= (1000 if aircraft else 700)))
            if len(_CK_CANDS) > 200:
                _CK_CANDS.clear()
            _CK_CANDS[ck_key] = cands
        if not cands:
            return None
        dest = cands[seed % len(cands)]
        dist = C["gc_distance_nm"](o["lat"], o["lon"], A[dest]["lat"], A[dest]["lon"])
        base = {"origin": C["airport_obj"](start), "destination": C["airport_obj"](dest), "distance_nm": round(dist),
                "target_block_min": round(dist / max(300, lead.get("cruise_ktas") or 450) * 60 + 30), "region": "Company sector"}
    names = " or ".join(C["FLEET"][t]["name"] for t in unlocked)
    return {**base, "id": mission_id, "title": f"{fam} type checkride: {base['origin']['icao']} to {base['destination']['icao']}",
            "category": "Type checkride", "priority": "Standard", "type_checkride": fam, "types_only": True, "aircraft": unlocked,
            "payload_lbs": int(round(lead["max_payload_lbs"] * 0.55 / 500) * 500), "reward": 150,
            "cargo": "Ballast and company material", "urgent": False,
            "briefing": (f"Your {fam} type rating checkride, flown in the {names}. Fly a normal company sector by the book: SimBrief plan, "
                         f"250 kt below 10,000 ft, a steady approach, and a landing no firmer than {abs(TYPE_CHECKRIDE['min_rate'])} fpm "
                         f"with landing load no higher than {TYPE_CHECKRIDE['max_g']} G and no more than one bounce. "
                         f"ACARS grades it: score {TYPE_CHECKRIDE['min_score']} or better with no review flags, followed by an accepted report, earns the rating.")}


DELIVERY_HUBS_LIST = ("KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC")


def grant_rating(con, pilot_id, fam, source, score=None, pirep_id=None):
    con.execute("INSERT OR REPLACE INTO type_ratings (pilot_id, family, source, date, score, pirep_id) VALUES (?,?,?,?,?,?)",
                (pilot_id, fam, source, time.time(), score, pirep_id))


def note_rating_on_licence(pilot_id, fam, when):
    """The founder's profile holds the license: mark the PAC checkride on the matching type rating."""
    if pilot_id != (C["settings"]().get("pilot_id") or "PAC0001"):
        return
    try:
        prof = C["load_profile"](pilot_id)
        date = dt.datetime.fromtimestamp(when, dt.timezone.utc).strftime("%Y-%m-%d")
        types = set(family_types(fam))
        rows = [r for r in prof.get("type_ratings", []) if r.get("fleet") in types]
        if not rows:
            t = family_types(fam)[0]
            rows = [{"type": C["FLEET"][t]["icao"], "fleet": t, "name": C["FLEET"][t]["name"], "role": "Captain", "issued": "", "prior_hours": 0,
                     "status": "Active", "notes": ""}]
            prof.setdefault("type_ratings", []).extend(rows)
        for r in rows:
            r["issued"] = r.get("issued") or date
            r["status"] = "Active"
            if "PAC checkride" not in (r.get("notes") or ""):
                r["notes"] = ((r.get("notes") or "") + f" · PAC checkride {date}").strip(" ·")
        C["save_json"](C["DATA"] / "profile.json", prof)
    except Exception as e:
        print("Could not note the rating on the license:", e)


def checkride_aircraft_stations(pilot_id, entry, _career=None):
    """Stations with an available, eligible aircraft and a flyable checkride."""
    if not entry.get("unlocked") or not entry.get("mission"):
        return []
    with C["db"]() as con:
        rows = con.execute("SELECT reg, type, location FROM airframes WHERE status='Available' ORDER BY location, reg").fetchall()
    by_station = {}
    for row in rows:
        if row["type"] in entry["types"] and row["location"] in C["AIRPORTS"]:
            by_station.setdefault(row["location"], []).append(dict(row))
    here = pilot_location(pilot_id)
    candidates = []
    for station, frames in by_station.items():
        mission = checkride_mission(pilot_id, entry["checkride_id"], station, _career=_career)
        if not mission or mission["origin"]["icao"] != station:
            continue
        usable = [f for f in frames if f["type"] in mission["aircraft"]]
        if usable:
            candidates.append({"icao": station, "airframes": [f["reg"] for f in usable]})
    airport = C["AIRPORTS"].get(here)
    def order(item):
        dest = C["AIRPORTS"][item["icao"]]
        distance = C["gc_distance_nm"](airport["lat"], airport["lon"], dest["lat"], dest["lon"]) if airport else 0
        return (item["icao"] != here, distance, item["icao"])
    return sorted(candidates, key=order)


@bp.post("/api/ratings/company-travel")
def checkride_company_travel():
    """Company travel now occurs atomically with fleet checkride booking."""
    return jsonify({"error": "Use Start checkride in Qualifications. Company travel is included when you book a fleet checkride."}), 409
    pilot_id = current_pilot_id()
    body = request.json or {}
    mission_id = str(body.get("checkride_id") or "")
    destination = str(body.get("to") or "").strip().upper()
    entry = next((f for f in ratings_overview(pilot_id) if f["checkride_id"] == mission_id), None)
    if not entry or not entry["unlocked"] or entry["rated"]:
        return jsonify({"error": "Company travel is available only for an unrated type checkride you can take."}), 400
    if not C["settings"]().get("enforce_airframes", True):
        return jsonify({"error": "Aircraft locations are not enforced; company travel is not needed."}), 400
    entry["mission"] = checkride_mission(pilot_id, mission_id)
    options = checkride_aircraft_stations(pilot_id, entry)
    if any(s["icao"] == pilot_location(pilot_id) for s in options):
        return jsonify({"error": "A checkride aircraft is already available at your station."}), 409
    if destination == pilot_location(pilot_id) or destination not in {s["icao"] for s in options}:
        return jsonify({"error": "No eligible checkride aircraft is available at that station. Refresh Career to see current options."}), 409
    departure = pilot_location(pilot_id)
    with C["db"]() as con:
        if con.execute("SELECT 1 FROM bookings WHERE pilot_id=?", (pilot_id,)).fetchone():
            return jsonify({"error": "Finish or cancel your booked flight before company travel."}), 409
        chosen = next(s for s in options if s["icao"] == destination)
        marks = ','.join('?' for _ in chosen["airframes"])
        if not con.execute(f"SELECT 1 FROM airframes WHERE reg IN ({marks}) AND location=? AND status='Available'",
                           (*chosen["airframes"], destination)).fetchone():
            return jsonify({"error": "The checkride aircraft was just booked. Refresh Career for another station."}), 409
        add_tx(pilot_id, "training_travel", 0,
               f"Company positioning for {entry['family']} checkride: {departure} to {destination}", None, con)
        con.execute("UPDATE pilots SET location=? WHERE id=?", (destination, pilot_id))
    return jsonify({"location": destination, "cost": 0,
                    "mission": checkride_mission(pilot_id, mission_id)})


@bp.get("/api/ratings")
def ratings_api():
    pid = current_pilot_id()
    # Reuse this pilot snapshot only inside this request; never across pilots or requests.
    career_data = career(pid)
    fams = ratings_overview(pid, _career=career_data)
    for f in fams:  # the checkride flight for each rating the pilot can take next
        f["mission"] = checkride_mission(pid, f["checkride_id"], _career=career_data) if f["unlocked"] and (not f["rated"] or f.get("direct_entry")) else None
        stations = checkride_aircraft_stations(pid, f, _career=career_data) if f["mission"] else []
        here = pilot_location(pid)
        f["available_here"] = not C["settings"]().get("enforce_airframes", True) or any(s["icao"] == here for s in stations)
        f["company_travel"] = ([s for s in stations if s["icao"] != here]
                               if not f["rated"] and not f["available_here"] and C["settings"]().get("enforce_airframes", True)
                               else [])
    return jsonify({"families": fams, "standard": TYPE_CHECKRIDE, "direct_entry": direct_entry(),
                    "required": bool(C["settings"]().get("require_type_ratings", False))})


@bp.post("/api/staff/ratings/<pid>")
def staff_ratings(pid):
    b = request.json or {}
    if b.get("action") == "list":
        return jsonify({"ok": True, "ratings": ratings_overview(pid)})
    fam = str(b.get("family") or "")
    if fam not in {rating_family(k) for k in C["FLEET"]}:
        return jsonify({"error": "Unknown rating."}), 400
    with C["db"]() as con:
        if b.get("action") == "remove":
            con.execute("DELETE FROM type_ratings WHERE pilot_id=? AND family=?", (pid, fam))
        else:
            grant_rating(con, pid, fam, "staff")
    return jsonify({"ok": True, "ratings": ratings_overview(pid)})


# ---------------------------------------------------------------- my stats, records, collection and monthly recap
def _flown(pilot_id, start=None, end=None):
    """The pilot's real flights (no demos, not rejected), oldest first."""
    q = "SELECT * FROM pireps WHERE pilot_id=? AND demo=0 AND review_status!='Rejected'"
    args = [pilot_id]
    if start is not None:
        q += " AND filed_at>=? AND filed_at<?"
        args += [start, end]
    with C["db"]() as con:
        return [dict(r) for r in con.execute(q + " ORDER BY filed_at", args)]


def _month_bounds(month):
    y, mo = map(int, month.split("-"))
    return (dt.datetime(y, mo, 1, tzinfo=dt.timezone.utc).timestamp(),
            dt.datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())


def _brief(r):
    return {"id": r["id"], "flight": r["flight_number"], "dep": r["dep"], "arr": r["arr"], "aircraft": r["aircraft"],
            "date": dt.datetime.fromtimestamp(r["filed_at"], dt.timezone.utc).strftime("%Y-%m-%d")}


def _best_landing(rows):
    soft = [r for r in rows if r["landing_rate"] is not None and r["landing_rate"] <= -20 and r["status"] != "Failed"]
    return max(soft, key=lambda r: r["landing_rate"]) if soft else None


def stats(pilot_id):
    rows = _flown(pilot_id)
    ok = [r for r in rows if r["status"] != "Failed"]
    A, F = C["AIRPORTS"], C["FLEET"]
    visits, first = {}, {}
    for r in ok:
        for i in (r["dep"], r["arr"]):
            if i in A:
                visits[i] = visits.get(i, 0) + 1
                first.setdefault(i, r["filed_at"])
    airports = [{"icao": i, "name": A[i]["name"], "city": A[i]["city"], "country": A[i]["country"], "continent": A[i]["continent"],
                 "lat": A[i]["lat"], "lon": A[i]["lon"], "visits": n,
                 "first": dt.datetime.fromtimestamp(first[i], dt.timezone.utc).strftime("%Y-%m-%d")} for i, n in visits.items()]
    routes = {}
    for r in ok:
        if r["dep"] in A and r["arr"] in A and r["dep"] != r["arr"]:
            k = (r["dep"], r["arr"])
            routes[k] = routes.get(k, 0) + 1
    by_type = {}
    for r in ok:
        t = by_type.setdefault(r["aircraft"], {"code": r["aircraft"], "name": F.get(r["aircraft"], {}).get("name", r["aircraft"]), "flights": 0, "hours": 0.0})
        t["flights"] += 1
        t["hours"] += (r["block_min"] or 0) / 60
    months = []
    now = dt.datetime.now(dt.timezone.utc)
    for k in range(11, -1, -1):
        y, mo = now.year, now.month - k
        while mo <= 0:
            mo += 12
            y -= 1
        a, b = _month_bounds(f"{y}-{mo:02d}")
        mrows = [r for r in ok if a <= r["filed_at"] < b]
        months.append({"month": f"{y}-{mo:02d}", "flights": len(mrows), "hours": round(sum((r["block_min"] or 0) for r in mrows) / 60, 1)})
    # streaks: A grades in a row, and days in a row with a flight
    a_run = a_best = 0
    for r in rows:
        a_run = a_run + 1 if r["grade"] == "A" else 0
        a_best = max(a_best, a_run)
    days = sorted({dt.datetime.fromtimestamp(r["filed_at"], dt.timezone.utc).date() for r in ok})
    d_best = d_run = 0
    for i, d in enumerate(days):
        d_run = d_run + 1 if i and (d - days[i - 1]).days == 1 else 1
        d_best = max(d_best, d_run)
    top_route = max(routes.items(), key=lambda kv: kv[1]) if routes else None
    fav = max(by_type.values(), key=lambda t: t["hours"]) if by_type else None
    best = _best_landing(ok)
    rec = lambda r, value, unit: {**_brief(r), "value": value, "unit": unit} if r else None
    records = {
        "softest_landing": rec(best, best["landing_rate"] if best else None, "fpm"),
        "longest_distance": rec(max(ok, key=lambda r: r["distance_nm"] or 0), None, "nm") if ok else None,
        "longest_block": rec(max(ok, key=lambda r: r["block_min"] or 0), None, "min") if ok else None,
        "heaviest_load": rec(max(ok, key=lambda r: r["payload_lbs"] or 0), None, "lb") if ok else None,
        "most_points": rec(max(ok, key=lambda r: r["points"] or 0), None, "points") if ok else None,
    }
    for k, field in (("longest_distance", "distance_nm"), ("longest_block", "block_min"), ("heaviest_load", "payload_lbs"), ("most_points", "points")):
        if records[k]:
            src = next(r for r in ok if r["id"] == records[k]["id"])
            records[k]["value"] = round(src[field] or 0)
    countries = sorted({a["country"] for a in airports})
    continents = sorted({a["continent"] for a in airports})
    rates = [r["landing_rate"] for r in ok if r["landing_rate"] is not None]
    return {
        "totals": {"flights": len(ok), "hours": round(sum((r["block_min"] or 0) for r in ok) / 60, 1),
                   "distance_nm": round(sum((r["distance_nm"] or 0) for r in ok)), "cargo_lbs": round(sum((r["payload_lbs"] or 0) for r in ok)),
                   "points": sum((r["points"] or 0) for r in ok), "avg_score": round(sum(r["score"] for r in ok if r["score"] is not None) / sum(r["score"] is not None for r in ok), 1) if any(r["score"] is not None for r in ok) else None,
                   "avg_landing": round(sum(rates) / len(rates)) if rates else None,
                   "grades": {g: sum(1 for r in ok if r["grade"] == g) for g in "ABCDF"}},
        "collection": {"airports": len(airports), "countries": len(countries), "continents": len(continents),
                       "country_list": countries, "continent_list": continents,
                       "milestones": {"airports": [10, 25, 50, 100], "countries": [5, 10, 25], "continents": [6]}},
        "airports": sorted(airports, key=lambda a: -a["visits"]),
        "routes": [{"dep": d, "arr": a_, "flights": n, "from": [A[d]["lat"], A[d]["lon"]], "to": [A[a_]["lat"], A[a_]["lon"]]} for (d, a_), n in routes.items()],
        "by_type": sorted(({**t, "hours": round(t["hours"], 1)} for t in by_type.values()), key=lambda t: -t["hours"]),
        "months": months,
        "records": records,
        "streaks": {"a_grades": a_best, "days": d_best},
        "favourites": {"route": {"dep": top_route[0][0], "arr": top_route[0][1], "flights": top_route[1]} if top_route else None,
                       "aircraft": fav, "airport": max(airports, key=lambda a: a["visits"]) if airports else None},
    }


def recap(pilot_id, month):
    a, b = _month_bounds(month)
    rows = [r for r in _flown(pilot_id, a, b) if r["status"] != "Failed"]
    before = {i for r in _flown(pilot_id, 0, a) if r["status"] != "Failed" for i in (r["dep"], r["arr"])}
    new_airports = sorted({i for r in rows for i in (r["dep"], r["arr"]) if i not in before and i in C["AIRPORTS"]})
    y, mo = map(int, month.split("-"))
    prev = f"{y - (mo == 1)}-{(mo - 2) % 12 + 1:02d}"
    pa, pb = _month_bounds(prev)
    prow = [r for r in _flown(pilot_id, pa, pb) if r["status"] != "Failed"]
    with C["db"]() as con:
        earned = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id=? AND amount>0 AND kind!='adjustment' AND time>=? AND time<?",
                             (pilot_id, a, b)).fetchone()[0]
    routes, types = {}, {}
    for r in rows:
        routes[(r["dep"], r["arr"])] = routes.get((r["dep"], r["arr"]), 0) + 1
        types[r["aircraft"]] = types.get(r["aircraft"], 0) + (r["block_min"] or 0)
    best = _best_landing(rows)
    hours = round(sum((r["block_min"] or 0) for r in rows) / 60, 1)
    return {"month": month, "label": dt.date(y, mo, 1).strftime("%B %Y"), "flights": len(rows), "hours": hours,
            "distance_nm": round(sum((r["distance_nm"] or 0) for r in rows)), "cargo_lbs": round(sum((r["payload_lbs"] or 0) for r in rows)),
            "points": sum((r["points"] or 0) for r in rows), "earned": round(earned),
            "avg_score": round(sum(r["score"] for r in rows if r["score"] is not None) / sum(r["score"] is not None for r in rows), 1) if any(r["score"] is not None for r in rows) else None,
            "grades": {g: sum(1 for r in rows if r["grade"] == g) for g in "ABCDF"},
            "best_landing": {**_brief(best), "rate": best["landing_rate"]} if best else None,
            "top_route": (lambda kv: {"dep": kv[0][0], "arr": kv[0][1], "flights": kv[1]})(max(routes.items(), key=lambda kv: kv[1])) if routes else None,
            "top_aircraft": (lambda kv: {"code": kv[0], "name": C["FLEET"].get(kv[0], {}).get("name", kv[0]), "hours": round(kv[1] / 60, 1)})(max(types.items(), key=lambda kv: kv[1])) if types else None,
            "new_airports": new_airports, "vs_previous": {"month": prev, "flights": len(prow), "hours": round(sum((r["block_min"] or 0) for r in prow) / 60, 1)}}


def recap_months(pilot_id):
    rows = _flown(pilot_id)
    return sorted({dt.datetime.fromtimestamp(r["filed_at"], dt.timezone.utc).strftime("%Y-%m") for r in rows}, reverse=True)


# ---------------------------------------------------------------- personal goals
GOAL_KINDS = {"hours": ("block hours", "hours"), "flights": ("flights", "flights"), "distance": ("nm flown", "nm"),
              "cargo": ("lb of cargo", "lb"), "airports": ("new airports", "airports"), "countries": ("new countries", "countries"),
              "a_grades": ("A grades", "A grades"), "soft": ("landings softer than 150 fpm", "soft landings")}
GOAL_PERIODS = ("month", "year", "deadline", "ever")


def _goal_window(g, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if g["period"] == "month":
        start = dt.datetime(now.year, now.month, 1, tzinfo=dt.timezone.utc)
        end = dt.datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=dt.timezone.utc)
        return start.timestamp(), end.timestamp(), now.strftime("%B")
    if g["period"] == "year":
        return dt.datetime(now.year, 1, 1, tzinfo=dt.timezone.utc).timestamp(), dt.datetime(now.year + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp(), str(now.year)
    if g["period"] == "deadline":
        return g["created"], (g["deadline"] or now.timestamp()) + 86400, None
    return 0, 4e9, None


def goal_progress(pilot_id, g):
    start, end, label = _goal_window(g)
    rows = [r for r in _flown(pilot_id, start, end) if r["status"] != "Failed"]
    k = g["kind"]
    if k in ("airports", "countries"):
        before = [r for r in _flown(pilot_id, 0, start) if r["status"] != "Failed"]
        seen = {i for r in before for i in (r["dep"], r["arr"]) if i in C["AIRPORTS"]}
        new = {i for r in rows for i in (r["dep"], r["arr"]) if i in C["AIRPORTS"] and i not in seen}
        if k == "countries":
            had = {C["AIRPORTS"][i]["country"] for i in seen}
            new = {C["AIRPORTS"][i]["country"] for i in new} - had
        value = len(new)
    else:
        value = {"hours": lambda: sum((r["block_min"] or 0) for r in rows) / 60, "flights": lambda: len(rows),
                 "distance": lambda: sum((r["distance_nm"] or 0) for r in rows), "cargo": lambda: sum((r["payload_lbs"] or 0) for r in rows),
                 "a_grades": lambda: sum(1 for r in rows if r["grade"] == "A"),
                 "soft": lambda: sum(1 for r in rows if r["landing_rate"] is not None and -150 < r["landing_rate"] <= -20)}[k]()
    now = time.time()
    left = max(0, int((end - now) // 86400)) if g["period"] != "ever" else None
    noun, unit = GOAL_KINDS[k]
    if g["target"] == 1:  # "1 new country", not "1 new countries"
        noun = {"block hours": "block hour", "flights": "flight", "new airports": "new airport", "new countries": "new country",
                "A grades": "A grade", "landings softer than 150 fpm": "landing softer than 150 fpm"}.get(noun, noun)
    when = {"month": f"in {label}", "year": f"in {label}", "ever": "in total",
            "deadline": f"by {dt.datetime.fromtimestamp(g['deadline'] or now, dt.timezone.utc).strftime('%b %d, %Y')}"}[g["period"]]
    return {**g, "value": round(value, 1), "pct": min(100, round(value / g["target"] * 100)) if g["target"] else 0,
            "done": value >= g["target"], "title": f"{g['target']:,.0f} {noun} {when}", "unit": unit, "days_left": left,
            "expired": g["period"] == "deadline" and now > end and value < g["target"]}


@bp.get("/api/goals")
def goals_list():
    pid = current_pilot_id()
    with C["db"]() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM goals WHERE pilot_id=? ORDER BY created", (pid,))]
    return jsonify({"goals": [goal_progress(pid, g) for g in rows], "kinds": {k: v[0] for k, v in GOAL_KINDS.items()}})


@bp.post("/api/goals")
def goals_add():
    pid = current_pilot_id()
    b = request.json or {}
    kind, period = b.get("kind"), b.get("period", "month")
    try:
        target = float(b.get("target"))
    except (TypeError, ValueError):
        return jsonify({"error": "Give the goal a number to aim for."}), 400
    if kind not in GOAL_KINDS or period not in GOAL_PERIODS or not 0 < target <= 1e9:
        return jsonify({"error": "Choose what to aim for, how much, and by when."}), 400
    deadline = None
    if period == "deadline":
        try:
            deadline = dt.datetime.strptime(str(b.get("deadline")), "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            return jsonify({"error": "Pick the date to reach it by."}), 400
        if deadline < time.time() - 86400:
            return jsonify({"error": "That date has already passed."}), 400
    with C["db"]() as con:
        if con.execute("SELECT COUNT(*) FROM goals WHERE pilot_id=?", (pid,)).fetchone()[0] >= 12:
            return jsonify({"error": "You have 12 goals already. Remove one to add another."}), 400
        con.execute("INSERT INTO goals (pilot_id, kind, target, period, deadline, created) VALUES (?,?,?,?,?,?)",
                    (pid, kind, target, period, deadline, time.time()))
    return goals_list()


@bp.delete("/api/goals/<int:gid>")
def goals_remove(gid):
    with C["db"]() as con:
        con.execute("DELETE FROM goals WHERE id=? AND pilot_id=?", (gid, current_pilot_id()))
    return goals_list()


@bp.get("/api/stats")
def stats_api():
    return jsonify(stats(current_pilot_id()))


@bp.get("/api/recap")
def recap_api():
    pid = current_pilot_id()
    months = recap_months(pid)
    month = request.args.get("month") or (months[0] if months else today().strftime("%Y-%m"))
    if not __import__("re").fullmatch(r"\d{4}-\d{2}", month):
        return jsonify({"error": "Month should look like 2026-09."}), 400
    import cargo_programs
    from contextlib import closing
    try:
        with closing(C['db']()) as con:
            cargo = cargo_programs.month_summary(con, C['AIRPORTS'], pid, month)
    except ValueError:
        return jsonify({"error": "Choose a valid calendar month."}), 400
    response = jsonify({**recap(pid, month), "months": months, "cargo_passport": cargo})
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def leaderboards(month=None):
    month = month or today().strftime("%Y-%m")
    y, mo = map(int, month.split("-"))
    start = dt.datetime(y, mo, 1, tzinfo=dt.timezone.utc).timestamp()
    end = dt.datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp()
    base = "FROM pireps p LEFT JOIN pilots r ON r.id=p.pilot_id WHERE p.demo=0 AND p.review_status='Accepted' AND p.filed_at>=? AND p.filed_at<?"
    q = lambda sql: [dict(r) for r in con.execute(sql, (start, end))]
    with C["db"]() as con:
        smooth = q(f"SELECT p.pilot_id, r.name, p.landing_rate value, p.flight_number, p.arr {base} AND p.landing_rate IS NOT NULL AND p.status!='Failed' ORDER BY p.landing_rate DESC LIMIT 10")
        cargo = q(f"SELECT p.pilot_id, r.name, SUM(CASE WHEN p.status!='Failed' THEN p.payload_lbs ELSE 0 END) value {base} GROUP BY p.pilot_id ORDER BY value DESC LIMIT 10")
        hours = q(f"SELECT p.pilot_id, r.name, ROUND(SUM(p.block_min)/60.0,1) value {base} GROUP BY p.pilot_id ORDER BY value DESC LIMIT 10")
        score = q(f"SELECT p.pilot_id, r.name, ROUND(AVG(p.score),1) value, COUNT(*) n {base} GROUP BY p.pilot_id HAVING n>=3 ORDER BY value DESC LIMIT 10")
        points = [dict(r) for r in con.execute(
            "SELECT p.pilot_id, r.name, SUM(p.points) value FROM pireps p LEFT JOIN pilots r ON r.id=p.pilot_id "
            "WHERE p.demo=0 AND p.review_status='Accepted' GROUP BY p.pilot_id ORDER BY value DESC LIMIT 10")]
    return {"month": month, "smoothest": smooth, "cargo": cargo, "hours": hours, "score": score, "points_all_time": points}


# ---------------------------------------------------------------- site content
def site():
    return {**DEFAULT_SITE, **C["load_json"](C["DATA"] / "site.json", {})}


# ---------------------------------------------------------------- routes: public
@bp.get("/api/va/config")
def va_config():
    return jsonify({"ranks": ranks_effective(), "avg_window": AVG_WINDOW, "avg_min_flights": AVG_MIN_FLIGHTS, "review": REVIEW,
                    "checkride": {**CHECKRIDE, "mission": C["MISSIONS"].get(CHECKRIDE_ID)}, "type_checkride": TYPE_CHECKRIDE, "a_check_hours": A_CHECK_HOURS,
                    "featured_mult": FEATURED_MULT, "type_ratings_required": bool(C["settings"]().get("require_type_ratings", False)), "direct_entry": direct_entry(), "tours": TOURS, "tour_legs": list(TOUR_LEGS.values()), "rotations": ROTATIONS,
                    "badges": [{"id": b, "name": n, "description": d} for b, n, d in BADGES]})


# ---------------------------------------------------------------- network partners (the VATSIM logo)
# VATSIM's Virtual Airline Partner policy asks for its logo on the home page or in a clearly marked Partners section.
# PAC ships the official no-tagline logo from VATSIM's public logo pack (static/partners/vatsim-logo.svg, unaltered).
# Staff can upload a newer file from vats.im/logo to replace it; PAC never redraws or alters it.
NETWORK_LOGO_BUILT_IN = {"vatsim": "/static/partners/vatsim-logo.svg"}
NETWORK_LOGO_TYPES = {"image/png": ".png", "image/webp": ".webp", "image/svg+xml": ".svg"}


def _net_logo_dir():
    return C["DATA"] / "network_logos"


def network_logo_file(net="vatsim"):
    d = _net_logo_dir()
    return next((f for f in sorted(d.glob(f"{net}.*")) if f.suffix in NETWORK_LOGO_TYPES.values()), None) if d.exists() else None


NETWORKS = ("vatsim", "ivao")


def network_logos():
    f, fi = network_logo_file("vatsim"), network_logo_file("ivao")
    st = C["settings"]()
    return {"vatsim": f"/api/va/home/network-logo/vatsim?v={int(f.stat().st_mtime)}" if f else NETWORK_LOGO_BUILT_IN["vatsim"],
            "vatsim_uploaded": bool(f),
            # shown on the home page only once staff switch it on: the logo says PAC is a VATSIM partner or associate
            "show": bool(st.get("vatsim_partner_section", False)),
            # IVAO sends its Virtual Airline logo to certified VAs; PAC has no built-in copy, staff upload the one IVAO provides
            "ivao": f"/api/va/home/network-logo/ivao?v={int(fi.stat().st_mtime)}" if fi else None,
            "ivao_show": bool(st.get("ivao_partner_section", False))}


@bp.get("/api/va/home/network-logo/<net>")
def network_logo_get(net):
    f = network_logo_file(net) if net in NETWORKS else None
    if not f:
        return jsonify({"error": "No logo uploaded."}), 404
    resp = send_from_directory(_net_logo_dir(), f.name, max_age=86400)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    if f.suffix == ".svg":         # an SVG is shown as a picture only, never run as a page
        resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return resp


@bp.post("/api/staff/network-logo")
def network_logo_upload():
    net = request.args.get("net", "vatsim")
    if net not in NETWORKS:
        return jsonify({"error": "Unknown network."}), 400
    name = net.upper()
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": f"Choose the {name} logo file (PNG, WebP or SVG)."}), 400
    data = f.read()
    ext = NETWORK_LOGO_TYPES.get(f.mimetype)
    looks = {".png": data[:8] == b"\x89PNG\r\n\x1a\n", ".webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
             ".svg": b"<svg" in data[:4096].lower()}
    if not ext or not looks.get(ext):
        return jsonify({"error": f"Upload the logo as a PNG, WebP or SVG file, as {name} provides it."}), 400
    if len(data) > 5 * 1024 * 1024:
        return jsonify({"error": "That file is over 5 MB. Use the web-sized logo from the pack."}), 400
    if ext == ".svg" and (b"<script" in data.lower() or b"javascript:" in data.lower()):
        return jsonify({"error": f"That SVG contains scripts. Use the PNG version of the {name} logo instead."}), 400
    d = _net_logo_dir()
    d.mkdir(exist_ok=True)
    for old in d.glob(f"{net}.*"):
        old.unlink()
    (d / (net + ext)).write_bytes(data)
    return jsonify({"ok": True, "logos": network_logos()})


@bp.delete("/api/staff/network-logo")
def network_logo_delete():
    net = request.args.get("net", "vatsim")
    if net not in NETWORKS:
        return jsonify({"error": "Unknown network."}), 400
    for old in _net_logo_dir().glob(f"{net}.*") if _net_logo_dir().exists() else []:
        old.unlink()
    return jsonify({"ok": True, "logos": network_logos()})


def short_name(name):
    """'Joseph Pagani' -> 'Joseph P.': enough for a public roster, without publishing full names (GDPR)."""
    parts = str(name or "").split()
    return parts[0] if len(parts) < 2 else f"{parts[0]} {parts[-1][0]}."


@bp.get("/api/public/roster")
def public_roster():
    """The public pilot roster and flight log (VATSIM and IVAO ask for both to be visible without signing in).
    First name and initial only; no emails, Discord, network IDs or locations."""
    with C["db"]() as con:
        pilots = [dict(r) for r in con.execute("SELECT id, name, hub, joined, staff FROM pilots WHERE status='Active' ORDER BY id")]
        roster = []
        for pl in pilots:
            car = career(pl["id"], con)
            roster.append({"id": pl["id"], "name": short_name(pl["name"]), "rank": car["rank"], "hub": pl.get("hub") or "",
                           "joined": pl.get("joined"), "hours": car["pac_hours"], "flights": car["flights"], "staff": bool(pl.get("staff"))})
        names = {pl["id"]: short_name(pl["name"]) for pl in pilots}
        flights = [dict(r) for r in con.execute(
            "SELECT filed_at, flight_number, pilot_id, dep, arr, aircraft, block_min, status FROM pireps "
            "WHERE demo=0 AND review_status='Accepted' ORDER BY filed_at DESC LIMIT 50")]
        tot = con.execute("SELECT COUNT(*), COALESCE(SUM(block_min), 0) / 60.0 FROM pireps WHERE demo=0 AND review_status='Accepted'").fetchone()
    for f in flights:
        f["pilot"] = names.get(f["pilot_id"], "Former pilot")
        if f["pilot_id"] not in names:
            f["pilot_id"] = ""
        f["aircraft_name"] = (C["FLEET"].get(f["aircraft"]) or {}).get("name", f["aircraft"])
    return jsonify({"pilots": roster, "flights": flights, "totals": {"pilots": len(roster), "flights": tot[0], "hours": round(tot[1], 1)},
                    "callsign": C["settings"]().get("filing_icao") or "PGI"})


@bp.get("/api/va/home")
def va_home():
    with C["db"]() as con:
        tot = dict(con.execute("""SELECT COUNT(*) flights, COALESCE(SUM(block_min),0)/60.0 hours,
            COALESCE(SUM(CASE WHEN status!='Failed' THEN payload_lbs ELSE 0 END),0) cargo, COALESCE(SUM(distance_nm),0) distance
            FROM pireps WHERE demo=0 AND review_status='Accepted'""").fetchone())
        pilots = con.execute("SELECT COUNT(*) FROM pilots WHERE status='Active'").fetchone()[0]
        recent = [dict(r) for r in con.execute(
            """SELECT p.flight_number, p.dep, p.arr, p.aircraft, p.landing_rate, p.filed_at, p.grade, r.name FROM pireps p
               LEFT JOIN pilots r ON r.id=p.pilot_id WHERE p.demo=0 AND p.review_status='Accepted' ORDER BY p.filed_at DESC LIMIT 6""")]
    stations = {r["origin"]["icao"] for r in C["ROUTES"].values()} | {r["destination"]["icao"] for r in C["ROUTES"].values()}
    return jsonify({"site": site(), "totals": {**tot, "hours": round(tot["hours"], 1), "pilots": pilots,
                                                 "routes": len(C["ROUTES"]), "stations": len(stations), "airframes": len(airframes())},
                    "network_logos": network_logos(),
                    "recent": recent, "events": active_events(), "featured": featured_routes(), "founder": C["load_profile"](C["settings"]().get("pilot_id") or "PAC0001")})


@bp.get("/api/va/career")
def va_career():
    pid = current_pilot_id()
    evs = sorted(load_events(), key=lambda e: e["start"])
    d = today().isoformat()
    return jsonify({"career": career(pid), "badges": badges(pid), "leaderboards": leaderboards(),
                    "events": [dict(e, state="active" if e["start"] <= d <= e["end"] else "upcoming" if e["start"] > d else "past") for e in evs],
                    "featured": featured_routes(), "tours": TOURS, "tour_progress": tour_progress(pid),
                    "rotations": ROTATIONS, "rotation_progress": rotation_progress(pid),
                    "enforce_ranks": bool(C["settings"]().get("enforce_ranks"))})


@bp.get("/api/airframes")
def va_airframes():
    return jsonify(airframes())


@bp.post("/api/applications")
def apply():
    b = request.json or {}
    ct = C["clean_text"]
    name, email = ct(b.get("name"), 80), ct(b.get("email"), 120)
    if not name or "@" not in email:
        return jsonify({"error": "Enter your name and a valid email address."}), 400
    if not b.get("agree"):
        return jsonify({"error": "Please confirm you've read the pilot handbook."}), 400
    with C["db"]() as con:
        con.execute("""INSERT INTO applications (submitted, name, email, country, discord, simulator, experience, hub, motivation, status)
            VALUES (?,?,?,?,?,?,?,?,?, 'Pending')""", (time.time(), name, email, ct(b.get("country"), 60), ct(b.get("discord"), 60),
                                                        ct(b.get("simulator"), 40), ct(b.get("experience"), 40), ct(b.get("hub"), 8),
                                                        ct(b.get("motivation"), 2000)))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- routes: staff
@bp.get("/api/staff/overview")
def staff_overview():
    with C["db"]() as con:
        reviews = [dict(r) for r in con.execute(
            """SELECT p.id, p.filed_at, p.flight_number, p.mission_title, p.dep, p.arr, p.planned_arr, p.aircraft, p.airframe,
               p.landing_rate, p.landing_g, p.score, p.grade, p.status, p.points, p.flags, p.review_status, p.review_note, r.name pilot,
               p.detail
               FROM pireps p LEFT JOIN pilots r ON r.id=p.pilot_id WHERE p.demo=0 ORDER BY
               CASE p.review_status WHEN 'Pending' THEN 0 ELSE 1 END, p.filed_at DESC LIMIT 60""")]
        apps = [dict(r) for r in con.execute(
            """SELECT a.*, (p.id IS NOT NULL) on_roster FROM applications a LEFT JOIN pilots p ON p.id=a.pilot_id
               ORDER BY CASE a.status WHEN 'Pending' THEN 0 ELSE 1 END, a.submitted DESC""")]
        roster = [dict(r) for r in con.execute("SELECT * FROM pilots ORDER BY id")]
        try:
            transfer_pending = con.execute("SELECT COUNT(*) FROM transfer_requests WHERE status='Pending'").fetchone()[0]
        except Exception:  # table not created yet
            transfer_pending = 0
    for r in reviews:
        r["flags"] = json.loads(r["flags"] or "[]")
        d = json.loads(r.pop("detail") or "{}")
        r["manual"] = bool(d.get("manual"))
        r["breakdown"] = d.get("breakdown", [])
        r["checkride"], r["type_checkride"] = d.get("checkride"), d.get("type_checkride")
    for p in roster:
        p.pop("password_hash", None)
        p.pop("password_set", None)
        c = career(p["id"])
        p.update(rank=c["rank"], hours=c["hours"], flights=c["flights"], avg_score=c["avg_score"], balance=balance(p["id"]))
    s = C["settings"]()
    return jsonify({"reviews": reviews, "applications": apps, "roster": roster, "airframes": airframes(), "transfer_pending": transfer_pending, "activity_overdue": _overdue_count(), "aborts": C["recent_aborts"]() if "recent_aborts" in C else [],
                    "events": sorted(load_events(), key=lambda e: e["start"]), "site": site(),
                    "rules": {"enforce_ranks": bool(s.get("enforce_ranks")), "enforce_airframes": bool(s.get("enforce_airframes", True)),
                              "allow_ground_reposition": bool(s.get("allow_ground_reposition", True)),
                              "enforce_pilot_location": bool(s.get("enforce_pilot_location", True)),
                              "require_type_ratings": bool(s.get("require_type_ratings", False)),
                              "direct_entry_checkrides": bool(s.get("direct_entry_checkrides", True)),
                              "require_release_signature": bool(s.get("require_release_signature", True)),
                              "shop_enabled": bool(s.get("shop_enabled", True)),
                              "live_map_public": bool(s.get("live_map_public"))}})


@bp.post("/api/staff/reviews/<int:pid>")
def staff_review(pid):
    b = request.json or {}
    import manual_pireps, sys
    result = manual_pireps.review(sys.modules[__name__], pid, b)
    if result is not None:
        return result
    action = b.get("action")
    if action not in ("accept", "reject"):
        return jsonify({"error": "Choose accept or reject."}), 400
    with C["db"]() as con:
        con.execute("UPDATE pireps SET review_status=?, review_note=?, reviewed_at=? WHERE id=?",
                    ("Accepted" if action == "accept" else "Rejected", C["clean_text"](b.get("note"), 500), time.time(), pid))
        try:
            import cargo_network
            cargo_network.set_flight_outcome(con, pid, accepted=(action == "accept"),
                                             keep_cargo=bool(b.get("keep_cargo", True)))
        except Exception as e:      # cargo bookkeeping must never block a review
            print("cargo outcome:", e)
    if action == "accept":
        with C["db"]() as con:
            record_accepted_type_pass(con, pid)
    paid = pay_pirep(pid) if action == "accept" else None
    return jsonify({"ok": True, "paid": paid})


def _recheck_checkrides(d, items, score, note=""):
    """After staff waive penalties, checks a failed checkride again: a waived overspeed or position jump no longer
    counts, and the score test uses the new score. Returns what now passes: {"line": True} and/or {"type": family}."""
    out = {}
    live = [x[0].lower() for x in items if x[1] < 0]
    jump_left = any(("250" in t and "fl100" in t) or "slew" in t or "position jump" in t for t in live)
    for key, rules in (("checkride", CHECKRIDE), ("type_checkride", TYPE_CHECKRIDE)):
        ck = d.get(key)
        if not ck or ck.get("passed"):
            continue
        reasons = [x for x in ck.get("reasons", []) if not x.startswith("score below")
                   and not (x in ("overspeed or position jump", "position jump") and not jump_left)]
        if score < rules["min_score"]:
            reasons.append(f"score below {rules['min_score']}")
        ck.update(reasons=reasons, passed=not reasons)
        if not reasons:
            ck["passed_after_review"] = note or "penalties waived by staff"
            out["line" if key == "checkride" else "type"] = True if key == "checkride" else ck.get("family")
    return out


@bp.post("/api/staff/reviews/<int:pid>/waive")
def staff_waive(pid):
    with C["db"]() as con:
        manual = con.execute("SELECT source FROM pireps WHERE id=?", (pid,)).fetchone()
    if manual and manual[0] == "Manual":
        return jsonify({"error": "Manual reports have no recorded penalties to waive."}), 400
    """Staff waive penalty lines (for example when ACARS misread something); score, grade and points are recalculated."""
    b = request.json or {}
    idxs = {int(i) for i in (b.get("items") or []) if str(i).isdigit()}
    note = C["clean_text"](b.get("note"), 300)
    with C["db"]() as con:
        row = con.execute("SELECT * FROM pireps WHERE id=?", (pid,)).fetchone()
        if not row:
            return jsonify({"error": "PIREP not found."}), 404
        d = json.loads(row["detail"] or "{}")
        items = d.get("breakdown", [])
        changed = 0
        for i in idxs:
            if 0 <= i < len(items) and items[i][1] < 0:
                items[i] = [f"{items[i][0]} (waived by staff{': ' + note if note else ''})", 0]
                changed += 1
        if not changed:
            return jsonify({"error": "Pick at least one penalty to waive."}), 400
        old_score, status = row["score"], row["status"]
        score = max(0, min(100, 100 + sum(x[1] for x in items)))
        if any("structural damage" in x[0] and x[1] < 0 for x in items):
            score = 0
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        old_base = d.get("base_points", row["points"])
        m = C["MISSIONS"].get(row["mission_id"]) or live_mission(row["mission_id"], True) or C["ROUTES"].get(row["mission_id"]) or TOUR_LEGS.get(row["mission_id"]) or {}
        reward = (old_base * 100 / old_score) if old_score else m.get("reward", 0)
        base = 0 if status == "Failed" else round(reward * score / 100)
        bonuses = []
        for lbl, pts, kind in d.get("bonuses", []):
            bonuses.append([lbl, pts if kind == "tour" or not old_base else round(pts * base / old_base), kind])
        if d.get("training"): base, bonuses = 0, []
        points = base + sum(x[1] for x in bonuses)
        d.update(breakdown=items, bonuses=bonuses, base_points=base)
        passed_now = _recheck_checkrides(d, items, score, note)
        if passed_now.get("line") and row["mission_id"] == CHECKRIDE_ID and row["review_status"] == "Accepted" and not row["demo"]:
            mark_line_checkride_passed(con, row["pilot_id"])
        con.execute("UPDATE pireps SET score=?, grade=?, points=?, bonus_points=?, detail=? WHERE id=?",
                    (score, grade, points, sum(x[1] for x in bonuses), json.dumps(d), pid))
        record_accepted_type_pass(con, pid)
        if b.get("release_airframe") and row["airframe"]:
            con.execute("UPDATE airframes SET status='Available', note=NULL, updated=? WHERE reg=? AND status IN ('Inspection','Damaged')",
                        (time.time(), row["airframe"]))
    return jsonify({"ok": True, "score": score, "grade": grade, "points": points})


def letter_fields(pilot_id=None, name="", hub="KCVG", staff_name=None):
    import auth
    st = site()
    hubs = {"KCVG": "Cincinnati", "KMIA": "Miami", "LIMC": "Milan Malpensa", "OMDW": "Dubai World Central",
            "PANC": "Anchorage", "VHHH": "Hong Kong"}
    me = auth.pilot_row(auth.current_id()) or {}
    return {"name": name, "pilot_id": pilot_id or "", "hub": hub or "KCVG", "hub_name": hubs.get(hub or "KCVG", ""),
            "site": auth.site_address(st.get("public_url", "")), "discord": st.get("discord_invite", "").strip(),
            "staff_name": (staff_name or st.get("letters_from") or me.get("name") or "PAC Operations Control"),
            "expires_days": auth.INVITE_DAYS}


@bp.get("/api/staff/letter/<kind>/<pid>")
def staff_letter(kind, pid):
    """The letter for a pilot: acceptance (with a fresh sign-in link), rejection or a sign-in reminder."""
    import auth
    import letters as LT
    if kind not in ("accepted", "rejected", "reminder"):
        return jsonify({"error": "Unknown letter."}), 400
    with C["db"]() as con:
        r = con.execute("SELECT id, name, email, hub FROM pilots WHERE id=?", (pid,)).fetchone()
    if not r and kind != "rejected":
        return jsonify({"error": "Pilot not found."}), 404
    link = ""
    if kind in ("accepted", "reminder"):
        link = auth.invite_link(pid)
        if not link:
            return jsonify({"error": "Couldn't make a sign-in link for that pilot."}), 400
    f = letter_fields(pid, r["name"] if r else "", (r["hub"] if r else "KCVG"))
    out = LT.letter(kind, link=link, reason=C["clean_text"](request.args.get("reason"), 400), **f)
    return jsonify({**out, "to": (r["email"] if r else ""), "pilot_id": pid, "link": link})


@bp.get("/api/staff/letter/rejected")
def staff_letter_rejected():
    """The rejection letter for an applicant, who has no pilot record."""
    import letters as LT
    f = letter_fields(None, C["clean_text"](request.args.get("name"), 80), "KCVG")
    out = LT.letter("rejected", reason=C["clean_text"](request.args.get("reason"), 400), **f)
    return jsonify({**out, "to": C["clean_text"](request.args.get("email"), 120)})


def send_letter_now(kind, *, pid=None, name="", email="", reason=""):
    """Email a letter straight away when PAC's email account is set up. Returns a note for the staff screen."""
    import auth
    import letters as LT
    import mailer
    st = C["settings"]()
    if not mailer.config_ready(st):
        return {"sent": False, "why": "no_mail"}
    if not mailer.valid_email(email):
        return {"sent": False, "why": "no_address"}
    link = auth.invite_link(pid) if kind in ("accepted", "reminder") and pid else ""
    L = LT.letter(kind, link=link, reason=reason, **letter_fields(pid, name, "KCVG"))
    ok, err = mailer.send(st, email, L["subject"], L["text"], L["html"], wait=True)
    return {"sent": bool(ok), "to": email, "error": err if not ok else None, "subject": L["subject"]}


def next_pilot_id(con):
    """The next pilot ID. Normally IDs are never reused, not even after a pilot leaves: PAC looks at everyone who has
    ever held one (current pilots, past flights, approved applications), so a departed pilot's history can't be mixed
    up with a new pilot's. While 'Reuse pilot IDs' is on (for testing before going live), PAC fills the lowest free
    number among current pilots instead, so the same test application can be approved again and again."""
    import re as _re
    if C["settings"]().get("reuse_pilot_ids"):
        taken = {int(m.group(1)) for (v,) in con.execute("SELECT id FROM pilots") if (m := _re.search(r"(\d+)$", str(v or "")))}
        n = 1
        while n in taken:
            n += 1
        return f"PAC{n:04d}"
    highest = 0
    for q in ("SELECT id FROM pilots", "SELECT DISTINCT pilot_id FROM pireps WHERE pilot_id IS NOT NULL",
              "SELECT DISTINCT pilot_id FROM applications WHERE pilot_id IS NOT NULL",
              "SELECT DISTINCT pilot_id FROM gallery WHERE pilot_id IS NOT NULL"):
        for (v,) in con.execute(q):
            m = _re.search(r"(\d+)$", str(v or ""))
            if m:
                highest = max(highest, int(m.group(1)))
    return f"PAC{highest + 1:04d}"


@bp.post("/api/staff/applications/<int:aid>")
def staff_application(aid):
    """Approve or decline an application. Approving issues the next pilot ID; PAC emails the letter when its
    email account is set up and the automatic setting is on."""
    b = request.json or {}
    action = b.get("action")
    if action not in ("approve", "reject"):
        return jsonify({"error": "Choose approve or reject."}), 400
    st = C["settings"]()
    with C["db"]() as con:
        a = con.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
        if not a:
            return jsonify({"error": "Application not found."}), 404
        note = C["clean_text"](b.get("note"), 500)
        new_id = None
        if action == "approve":
            new_id = next_pilot_id(con)
            hub = a["hub"] if a["hub"] in C["AIRPORTS"] else "KCVG"
            # a new pilot starts at the home base they chose (it used to default to Cincinnati for everyone)
            con.execute("""INSERT INTO pilots (id, name, email, country, discord, simulator, hub, location, joined, status, checkride, transfer_hours, staff)
                VALUES (?,?,?,?,?,?,?,?,?, 'Active', 'Pending', 0, 0)""",
                        (new_id, a["name"], a["email"], a["country"], a["discord"], a["simulator"], hub, hub, time.time()))
            con.execute("UPDATE applications SET status='Approved', pilot_id=?, note=? WHERE id=?", (new_id, note, aid))
        else:
            con.execute("UPDATE applications SET status='Rejected', note=? WHERE id=?", (note, aid))
        name, email = a["name"], a["email"]
    if action == "approve":
        try:
            import botlink
            botlink.new_pilot(new_id, name, a["discord"] if "discord" in a.keys() else "")
        except Exception as e:
            print(f"Discord welcome skipped: {e}")
    # outside the database block: a slow mail server must not hold the database open
    auto = st.get("mail_auto_welcome", True) if action == "approve" else st.get("mail_auto_decline", False)
    mail = {"sent": False, "why": "off"}
    if auto and b.get("email_it") is not False:
        mail = send_letter_now("accepted" if action == "approve" else "rejected",
                               pid=new_id, name=name, email=email, reason="" if action == "approve" else note)
    return jsonify({"ok": True, "pilot_id": new_id, "email": email, "name": name,
                    "reason": "" if action == "approve" else note, "mail": mail})


# An application that belongs to a pilot on the roster is kept: it's their joining record. Removing a pilot already
# detaches their application (pilot_id NULL), so deleting old ones never changes which pilot IDs PAC has issued.
OLD_APPS = "status != 'Pending' AND (pilot_id IS NULL OR pilot_id NOT IN (SELECT id FROM pilots))"


@bp.delete("/api/staff/applications/<int:aid>")
def staff_application_delete(aid):
    with C["db"]() as con:
        a = con.execute("SELECT a.name, a.pilot_id, (p.id IS NOT NULL) on_roster FROM applications a "
                        "LEFT JOIN pilots p ON p.id=a.pilot_id WHERE a.id=?", (aid,)).fetchone()
        if not a:
            return jsonify({"error": "Application not found."}), 404
        if a["on_roster"]:
            return jsonify({"error": f"That's {a['pilot_id']}'s joining record, kept while they're on the roster. "
                                     "Remove the pilot in Staff › Roster first if they've left."}), 409
        con.execute("DELETE FROM applications WHERE id=?", (aid,))
    return jsonify({"ok": True, "name": a["name"]})


@bp.post("/api/staff/applications/clear-old")
def staff_applications_clear_old():
    """Deletes every reviewed application whose pilot isn't on the roster: declined ones, and approved ones for pilots
    who have since been removed (test pilots, for example). Pending applications and current pilots' records stay."""
    with C["db"]() as con:
        n = con.execute(f"DELETE FROM applications WHERE {OLD_APPS}").rowcount
    return jsonify({"ok": True, "deleted": n})


@bp.get("/api/staff/pilots/<pid>/footprint")
def staff_pilot_footprint(pid):
    """What removing this pilot would affect, so staff can see before they decide."""
    with C["db"]() as con:
        if not con.execute("SELECT 1 FROM pilots WHERE id=?", (pid,)).fetchone():
            return jsonify({"error": "Pilot not found."}), 404
        n = lambda q: con.execute(q, (pid,)).fetchone()[0]
        return jsonify({"pilot_id": pid,
                        "pireps": n("SELECT COUNT(*) FROM pireps WHERE pilot_id=?"),
                        "hours": round((con.execute("SELECT COALESCE(SUM(block_min),0) FROM pireps WHERE pilot_id=? AND review_status!='Rejected'", (pid,)).fetchone()[0] or 0) / 60, 1),
                        "gallery": n("SELECT COUNT(*) FROM gallery WHERE pilot_id=?"),
                        "ratings": n("SELECT COUNT(*) FROM type_ratings WHERE pilot_id=?"),
                        "goals": n("SELECT COUNT(*) FROM goals WHERE pilot_id=?"),
                        "bookings": n("SELECT COUNT(*) FROM jobs WHERE pilot_id=? AND status='booked'")
                                   + n("SELECT COUNT(*) FROM live_missions WHERE pilot_id=? AND status='booked'"),
                        "staff": bool(con.execute("SELECT staff FROM pilots WHERE id=?", (pid,)).fetchone()[0])})


@bp.delete("/api/staff/pilots/<pid>")
def staff_pilot_delete(pid):
    """Remove a pilot. keep_flights=True (the default) leaves their flights in the airline's history with the pilot
    shown as a former pilot; keep_flights=False erases everything they ever did."""
    import auth
    b = request.get_json(silent=True) or {}
    keep = b.get("keep_flights", True)
    if b.get("confirm") != pid:
        return jsonify({"error": "Type the pilot ID to confirm."}), 400
    me = auth.current_id()
    with C["db"]() as con:
        r = con.execute("SELECT id, name, staff FROM pilots WHERE id=?", (pid,)).fetchone()
        if not r:
            return jsonify({"error": "Pilot not found."}), 404
        if pid == me:
            return jsonify({"error": "You can't remove your own account. Ask another staff member."}), 400
        if r["staff"] and con.execute("SELECT COUNT(*) FROM pilots WHERE staff=1").fetchone()[0] <= 1:
            return jsonify({"error": "That's the only staff account. Make someone else staff first."}), 400
        counts = {}
        if keep:   # the flights stay in PAC's history, no longer tied to a person
            counts["pireps_kept"] = con.execute("UPDATE pireps SET pilot_id=? WHERE pilot_id=?", (f"EX-{pid}", pid)).rowcount
            con.execute("UPDATE gallery SET pilot_id=? WHERE pilot_id=?", (f"EX-{pid}", pid))
        else:
            counts["pireps_deleted"] = con.execute("DELETE FROM pireps WHERE pilot_id=?", (pid,)).rowcount
            con.execute("DELETE FROM gallery WHERE pilot_id=?", (pid,))
        for t in ("type_ratings", "goals", "wallet", "invites", "api_keys"):
            con.execute(f"DELETE FROM {t} WHERE pilot_id=?", (pid,))
        for t in ("jobs", "live_missions", "urgent"):            # release anything they had booked
            con.execute(f"UPDATE {t} SET status='open', pilot_id=NULL WHERE pilot_id=? AND status='booked'", (pid,))
        con.execute("UPDATE airframes SET last_pilot=NULL WHERE last_pilot=?", (pid,))
        con.execute("UPDATE applications SET pilot_id=NULL WHERE pilot_id=?", (pid,))
        con.execute("DELETE FROM pilots WHERE id=?", (pid,))
    return jsonify({"ok": True, "pilot_id": pid, "name": r["name"], "kept_flights": bool(keep), **counts})


@bp.post("/api/staff/roster/<pid>")
def staff_roster(pid):
    b = request.json or {}
    with C["db"]() as con:
        if not con.execute("SELECT 1 FROM pilots WHERE id=?", (pid,)).fetchone():
            return jsonify({"error": "Pilot not found."}), 404
        if "transfer_hours" in b:
            con.execute("UPDATE pilots SET transfer_hours=? WHERE id=?", (max(0.0, C["num"](b["transfer_hours"])), pid))
        if b.get("status") in ("Active", "On leave", "Inactive"):
            con.execute("UPDATE pilots SET status=? WHERE id=?", (b["status"], pid))
        if b.get("checkride") in ("Pending", "Passed", "Waived"):
            con.execute("UPDATE pilots SET checkride=? WHERE id=?", (b["checkride"], pid))
        if b.get("hub") in LIVE_HUBS:          # the pilot's home hub (where they return to and are based)
            con.execute("UPDATE pilots SET hub=? WHERE id=?", (b["hub"], pid))
        if "rank_override" in b:
            ro = b["rank_override"] if b["rank_override"] in [r["name"] for r in RANKS] else None
            con.execute("UPDATE pilots SET rank_override=? WHERE id=?", (ro, pid))
        if "pra" in b:  # cleared to fly the Kodiak for Pagani Remote Aviation
            con.execute("UPDATE pilots SET pra=? WHERE id=?", (1 if b["pra"] else 0, pid))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- maintenance write-ups
ATA = {5: "Time limits and inspections", 21: "Air conditioning and pressurization", 22: "Autoflight", 23: "Communications",
       24: "Electrical power", 26: "Fire protection", 27: "Flight controls", 28: "Fuel", 29: "Hydraulic power",
       30: "Ice and rain protection", 31: "Indicating and recording", 32: "Landing gear and brakes", 33: "Lights", 34: "Navigation",
       36: "Pneumatic", 49: "APU", 50: "Cargo compartments", 52: "Doors", 53: "Fuselage", 71: "Power plant", 80: "Engine starting"}
DEFER_DAYS = {"B": 3, "C": 10}
GROUNDED = ("Maintenance", "Inspection", "A-check due", "Damaged", "Stored")


def create_item(con, reg, ata, description, severity="deferred", category="C", source="pilot", flight=None, pirep_id=None, when=None):
    """Opens a write-up on a tail. Grounding items take the aircraft out of service unless it's flying or already grounded."""
    now = when or time.time()
    severity = "grounding" if severity == "grounding" else "deferred"
    category = category if category in DEFER_DAYS else "C"
    due = None if severity == "grounding" else now + DEFER_DAYS[category] * 86400
    cur = con.execute("""INSERT INTO maint (reg, ata, description, severity, category, due, source, reported_by, flight, pirep_id, time)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (reg, int(ata) if str(ata).isdigit() else 5, C["clean_text"](description, 300), severity,
                                             None if severity == "grounding" else category, due, source, current_pilot_id(), flight, pirep_id, now))
    if severity == "grounding":
        con.execute("UPDATE airframes SET status='Maintenance', note=?, updated=? WHERE reg=? AND status='Available'",
                    (f"ATA {int(ata):02d}: {description}"[:200], now, reg))
    return cur.lastrowid


def open_items(reg=None, con=None):
    own = con is None
    con = con or C["db"]()
    q = "SELECT * FROM maint WHERE status='open'" + (" AND reg=?" if reg else "") + " ORDER BY severity DESC, time"
    rows = [dict(r) for r in con.execute(q, (reg,) if reg else ())]
    if own:
        con.close()
    for r in rows:
        r["ata_name"] = ATA.get(r["ata"], "")
        r["overdue"] = bool(r["due"] and r["due"] < time.time())
    return rows


def enforce_overdue():
    """A deferred item that runs past its deadline grounds the aircraft. Also moves AOG recoveries along."""
    now = time.time()
    events = []
    try:
        import aog
        with C["db"]() as con:
            events = [("aog_resolved", e) for e in aog.tick(con, now)]
            import heavy_check
            heavy_check.tick(con, now)
    except Exception as e:
        print("AOG tick:", e)
    try:
        import fleet_market, ceo
        def _news(title, body):
            with C["db"]() as c2:
                c2.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                           (time.time(), "news", title, body, 0, None, "PAC Management"))
        with C["db"]() as con:
            pending = []
            fleet_market.tick(con, lambda t, b: pending.append((t, b)), now)
            ceo.tick(con, lambda t, b: pending.append((t, b)), now)
            import growth
            growth.tick(con, now)
        for t, b in pending:
            _news(t, b)
    except Exception as e:
        print("Company tick:", e)
    _emit_bot(events)
    with C["db"]() as con:
        for r in con.execute("SELECT reg, ata, description FROM maint WHERE status='open' AND severity='deferred' AND due < ?", (now,)).fetchall():
            con.execute("UPDATE airframes SET status='Maintenance', note=?, updated=? WHERE reg=? AND status='Available'",
                        (f"Deferred item overdue: ATA {r['ata']:02d} {r['description']}"[:200], now, r["reg"]))


def clear_item(item_id, note="", by=None):
    with C["db"]() as con:
        it = con.execute("SELECT * FROM maint WHERE id=?", (item_id,)).fetchone()
        if not it:
            raise ValueError("Write-up not found.")
        con.execute("UPDATE maint SET status='cleared', cleared_time=?, cleared_by=?, note=? WHERE id=?",
                    (time.time(), by or current_pilot_id(), C["clean_text"](note, 300) or "Rectified", item_id))
        if it["ata"] == 5 and "A-check" in (it["description"] or ""):
            con.execute("UPDATE airframes SET hours_since_check=0 WHERE reg=?", (it["reg"],))
        still = con.execute("""SELECT COUNT(*) FROM maint WHERE reg=? AND status='open' AND (severity='grounding' OR (severity='deferred' AND due < ?))""",
                            (it["reg"], time.time())).fetchone()[0]
        if not still:
            con.execute("UPDATE airframes SET status='Available', note=NULL, updated=? WHERE reg=? AND status IN ('Maintenance','Inspection','A-check due','Damaged')",
                        (time.time(), it["reg"]))
            import aog
            aog.staff_cleared(con, it["reg"])
    return True


@bp.get("/api/maintenance")
def maintenance_list():
    reg = (request.args.get("reg") or "").upper() or None
    with C["db"]() as con:
        if request.args.get("all"):
            rows = [dict(r) for r in con.execute("SELECT * FROM maint" + (" WHERE reg=?" if reg else "") + " ORDER BY time DESC LIMIT 200",
                                                 (reg,) if reg else ())]
            for r in rows:
                r["ata_name"] = ATA.get(r["ata"], "")
                r["overdue"] = bool(r["status"] == "open" and r["due"] and r["due"] < time.time())
            return jsonify({"items": rows, "ata": ATA})
    return jsonify({"items": open_items(reg), "ata": ATA})


@bp.post("/api/maintenance")
def maintenance_report():
    """A pilot writes up a fault, from ACARS during the flight or from a PIREP afterwards."""
    b = request.json or {}
    reg = str(b.get("reg") or "").upper()
    desc = C["clean_text"](b.get("description"), 300)
    if not desc:
        return jsonify({"error": "Describe the fault."}), 400
    with C["db"]() as con:
        if not con.execute("SELECT 1 FROM airframes WHERE reg=?", (reg,)).fetchone():
            return jsonify({"error": "Write-ups go on PAC aircraft. For a partner aircraft, note the fault in your PIREP remarks."}), 400
        iid = create_item(con, reg, b.get("ata") or 5, desc, b.get("severity"), b.get("category") or "C", b.get("source") or "pilot",
                          b.get("flight"), int(b["pirep_id"]) if str(b.get("pirep_id") or "").isdigit() else None)
    return jsonify({"ok": True, "id": iid})


@bp.post("/api/staff/maintenance/<int:iid>")
def staff_maintenance(iid):
    b = request.json or {}
    try:
        if b.get("action") == "ground":
            with C["db"]() as con:
                it = con.execute("SELECT * FROM maint WHERE id=?", (iid,)).fetchone()
                con.execute("UPDATE maint SET severity='grounding', due=NULL, category=NULL WHERE id=?", (iid,))
                con.execute("UPDATE airframes SET status='Maintenance', note=?, updated=? WHERE reg=? AND status='Available'",
                            (f"ATA {it['ata']:02d}: {it['description']}"[:200], time.time(), it["reg"]))
        elif b.get("action") == "defer":
            cat = b.get("category") if b.get("category") in DEFER_DAYS else "C"
            with C["db"]() as con:
                it = con.execute("SELECT * FROM maint WHERE id=?", (iid,)).fetchone()
                con.execute("UPDATE maint SET severity='deferred', category=?, due=? WHERE id=?", (cat, time.time() + DEFER_DAYS[cat] * 86400, iid))
                others = con.execute("SELECT COUNT(*) FROM maint WHERE reg=? AND status='open' AND severity='grounding' AND id!=?", (it["reg"], iid)).fetchone()[0]
                if not others:
                    con.execute("UPDATE airframes SET status='Available', note=NULL WHERE reg=? AND status='Maintenance'", (it["reg"],))
        else:
            clear_item(iid, b.get("note", ""), "Staff")
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"ok": True})


# ---------------------------------------------------------------- company news and NOTAMs
def active_news(limit=10):
    now = time.time()
    with C["db"]() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM news WHERE expires IS NULL OR expires > ? ORDER BY important DESC, time DESC LIMIT ?", (now, limit))]


def active_notams():
    return [n for n in active_news(50) if n["kind"] == "notam"]


@bp.get("/api/news")
def news_list():
    return jsonify(active_news(int(request.args.get("limit") or 10)))


@bp.get("/api/staff/news")
def staff_news():
    with C["db"]() as con:
        return jsonify([dict(r) for r in con.execute("SELECT * FROM news ORDER BY time DESC")])


@bp.post("/api/staff/news")
def staff_news_save():
    b = request.json or {}
    title = C["clean_text"](b.get("title"), 120)
    body = C["clean_text"](b.get("body"), 2000)
    if not title:
        return jsonify({"error": "Give the post a title."}), 400
    kind = "notam" if b.get("kind") == "notam" else "news"
    days = C["num"](b.get("days"))
    expires = time.time() + days * 86400 if days else None
    author = C["clean_text"](b.get("author"), 60) or "PAC Operations"
    with C["db"]() as con:
        if b.get("id"):
            con.execute("UPDATE news SET kind=?, title=?, body=?, important=?, expires=? WHERE id=?",
                        (kind, title, body, 1 if b.get("important") else 0, expires, int(b["id"])))
        else:
            con.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                        (time.time(), kind, title, body, 1 if b.get("important") else 0, expires, author))
        year_start = dt.datetime(dt.datetime.now(dt.timezone.utc).year, 1, 1, tzinfo=dt.timezone.utc).timestamp()
        number = con.execute("SELECT COUNT(*) FROM news WHERE kind='notam' AND time >= ?", (year_start,)).fetchone()[0]
    # new posts go to Discord unless staff untick the box; an edit goes only when staff ask for it
    if b.get("discord", not b.get("id")) not in (False, "false", "0", "", None):
        import botlink
        botlink.emit("site_news", {"kind": kind, "title": title, "body": body, "important": bool(b.get("important")),
                                   "author": author, "updated": bool(b.get("id")),
                                   "number": f"{number:03d}/{dt.datetime.now(dt.timezone.utc):%y}" if kind == "notam" else None})
    return jsonify({"ok": True})


@bp.delete("/api/staff/news/<int:nid>")
def staff_news_delete(nid):
    with C["db"]() as con:
        con.execute("DELETE FROM news WHERE id=?", (nid,))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- screenshot gallery
GALLERY_MAX_BYTES = 15 * 1024 * 1024
IMAGE_MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}


def _gallery_dir():
    d = C["DATA"] / "gallery"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_screenshot(fileobj, pilot_id, pirep_id=None, caption=""):
    raw = fileobj.read(GALLERY_MAX_BYTES + 1)
    if len(raw) > GALLERY_MAX_BYTES:
        raise ValueError("Screenshots can be up to 15 MB each.")
    ext = next((e for m, e in IMAGE_MAGIC.items() if raw.startswith(m)), None)
    if not ext or (ext == "webp" and raw[8:12] != b"WEBP"):
        raise ValueError("Upload a JPG, PNG or WebP image.")
    import uuid
    name = f"{uuid.uuid4().hex}.{ext}"
    (_gallery_dir() / name).write_bytes(raw)
    thumb = name
    try:  # thumbnails when Pillow is available; the full image is used otherwise
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((720, 720))
        thumb = f"t_{name.rsplit('.', 1)[0]}.jpg"
        im.save(_gallery_dir() / thumb, "JPEG", quality=82)
    except Exception:
        pass
    with C["db"]() as con:
        cur = con.execute("INSERT INTO gallery (pilot_id, pirep_id, time, caption, file, thumb) VALUES (?,?,?,?,?,?)",
                          (pilot_id, pirep_id, time.time(), C["clean_text"](caption, 200), name, thumb))
        return cur.lastrowid


def gallery_rows(where="", args=(), limit=60):
    with C["db"]() as con:
        rows = con.execute(f"""SELECT g.*, p.flight_number, p.dep, p.arr, p.aircraft, r.name pilot FROM gallery g
            LEFT JOIN pireps p ON p.id=g.pirep_id LEFT JOIN pilots r ON r.id=g.pilot_id {where}
            ORDER BY g.featured DESC, g.time DESC LIMIT ?""", (*args, limit)).fetchall()
    return [{**dict(r), "url": f"/gallery/{r['file']}", "thumb_url": f"/gallery/{r['thumb'] or r['file']}"} for r in rows]


@bp.get("/api/gallery")
def gallery_list():
    pid = request.args.get("pirep")
    if pid:
        return jsonify(gallery_rows("WHERE g.pirep_id=?", (int(pid),)))
    return jsonify(gallery_rows(limit=int(request.args.get("limit") or 60)))


@bp.post("/api/gallery")
def gallery_upload():
    files = request.files.getlist("shots")
    if not files:
        return jsonify({"error": "Choose one or more screenshots."}), 400
    pirep = request.form.get("pirep_id")
    ids, errors = [], []
    for f in files[:10]:
        try:
            ids.append(save_screenshot(f.stream, current_pilot_id(), int(pirep) if pirep and pirep.isdigit() else None, request.form.get("caption", "")))
        except ValueError as e:
            errors.append(f"{f.filename}: {e}")
    if not ids:
        return jsonify({"error": " ".join(errors) or "Nothing uploaded."}), 400
    return jsonify({"ok": True, "added": len(ids), "errors": errors})


def _gallery_owner_or_staff(con, gid):
    """Pilots change their own screenshots; staff change anyone's."""
    import auth
    r = con.execute("SELECT pilot_id FROM gallery WHERE id=?", (gid,)).fetchone()
    if not r:
        return jsonify({"error": "That screenshot isn't there any more."}), 404
    if r["pilot_id"] != current_pilot_id() and not auth.is_staff():
        return jsonify({"error": "You can only change your own screenshots."}), 403
    return None


@bp.post("/api/gallery/<int:gid>")
def gallery_edit(gid):
    import auth
    b = request.json or {}
    with C["db"]() as con:
        refused = _gallery_owner_or_staff(con, gid)
        if refused:
            return refused
        if "featured" in b and not auth.is_staff():
            return jsonify({"error": "Staff choose the screenshots featured on the home page."}), 403
        if "caption" in b:
            con.execute("UPDATE gallery SET caption=? WHERE id=?", (C["clean_text"](b["caption"], 200), gid))
        if "featured" in b:
            con.execute("UPDATE gallery SET featured=? WHERE id=?", (1 if b["featured"] else 0, gid))
    return jsonify({"ok": True})


@bp.delete("/api/gallery/<int:gid>")
def gallery_delete(gid):
    with C["db"]() as con:
        refused = _gallery_owner_or_staff(con, gid)
        if refused:
            return refused
        r = con.execute("SELECT file, thumb FROM gallery WHERE id=?", (gid,)).fetchone()
        if r:
            for fn in {r["file"], r["thumb"]}:
                if fn:
                    try:
                        (_gallery_dir() / fn).unlink()
                    except FileNotFoundError:
                        pass
            con.execute("DELETE FROM gallery WHERE id=?", (gid,))
    return jsonify({"ok": True})


@bp.post("/api/staff/wallet/<pid>")
def staff_wallet(pid):
    b = request.json or {}
    amt = C["num"](b.get("amount"))
    if not amt:
        return jsonify({"error": "Enter an amount (negative to deduct)."}), 400
    add_tx(pid, "adjustment", amt, C["clean_text"](b.get("note"), 200) or "Staff adjustment")
    if b.get("location") and C["airport_obj"](b["location"]):
        set_location(pid, b["location"].upper())
    return jsonify({"ok": True, "balance": balance(pid)})


@bp.get("/api/pilot/me")
def pilot_me():
    pid = current_pilot_id()
    with C["db"]() as con:
        tx = [dict(r) for r in con.execute("SELECT * FROM wallet WHERE pilot_id=? ORDER BY time DESC LIMIT 30", (pid,))]
        earned = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id=? AND amount>0 AND kind!='adjustment'", (pid,)).fetchone()[0]
        spent = con.execute("SELECT COALESCE(SUM(-amount),0) FROM wallet WHERE pilot_id=? AND kind='jumpseat'", (pid,)).fetchone()[0]
        shop_spent = con.execute("SELECT COALESCE(SUM(-amount),0) FROM wallet WHERE pilot_id=? AND kind='shop'", (pid,)).fetchone()[0]
    car = career(pid)
    return jsonify({"location": C["airport_obj"](pilot_location(pid)), "balance": balance(pid), "transactions": tx,
                    "earned": round(earned, 2), "spent_travel": round(spent, 2), "spent_shop": round(shop_spent, 2), "rank": car["rank"],
                    "pay_rate": PAY_RATES.get(car["rank"], 55), "profit_share_pct": PROFIT_SHARE * 100,
                    "enforce_location": bool(C["settings"]().get("enforce_pilot_location", True)),
                    "activity": _activity(pid)})


def _overdue_count():
    try:
        import activity
        if not activity.policy()["enabled"]:
            return 0
        return sum(1 for x in activity.sweep() if x["state"] == "overdue")
    except Exception:
        return 0


def _activity(pid):
    try:
        import activity
        return activity.public(activity.state(pid))
    except Exception:
        return None


@bp.get("/api/pilot/wallet-transactions")
def pilot_wallet_transactions():
    pid = current_pilot_id()
    try:
        page = int(request.args.get("page", "1"))
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a valid transaction page."}), 400
    if page < 1 or page > 1000000:
        return jsonify({"error": "Choose a valid transaction page."}), 400
    per_page = 10
    with C["db"]() as con:
        total = con.execute("SELECT COUNT(*) FROM wallet WHERE pilot_id=?", (pid,)).fetchone()[0]
        pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, pages)
        transactions = [dict(r) for r in con.execute(
            "SELECT * FROM wallet WHERE pilot_id=? ORDER BY time DESC, id DESC LIMIT ? OFFSET ?",
            (pid, per_page, (page - 1) * per_page))]
    return jsonify({"transactions": transactions, "page": page, "pages": pages,
                    "per_page": per_page, "total": total})


@bp.post("/api/pilot/jumpseat/quote")
def jumpseat_quote():
    try:
        return jsonify(jumpseat_options(pilot_location(), (request.json or {}).get("to", ""), current_pilot_id()))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/api/pilot/jumpseat")
def jumpseat_go():
    b = request.json or {}
    try:
        return jsonify(jumpseat(current_pilot_id(), b.get("to", ""), b.get("kind", "")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/api/staff/airframes")
def staff_airframe_save():
    b = request.json or {}
    reg = "".join(ch for ch in str(b.get("reg") or "").upper() if ch.isalnum() or ch == "-")[:10]
    typ, loc = b.get("type"), str(b.get("location") or "").upper()
    if not reg or typ not in C["FLEET"]:
        return jsonify({"error": "Enter a registration and pick an aircraft type."}), 400
    if loc not in C["AIRPORTS"]:
        return jsonify({"error": f"{loc or 'That location'} isn't a known airport."}), 400
    status = b.get("status") if b.get("status") in ("Available", "Maintenance", "Inspection", "A-check due", "Damaged", "Stored") else "Available"
    with C["db"]() as con:
        old = con.execute("SELECT * FROM airframes WHERE reg=?", (reg,)).fetchone()
        if old and old["status"] == "Booked":
            return jsonify({"error": f"{reg} is booked on a flight. Finish or cancel that flight first."}), 409
        if old:
            reset = b.get("reset_check")
            con.execute("UPDATE airframes SET type=?, location=?, status=?, note=?, updated=?, hours_since_check=CASE WHEN ? THEN 0 ELSE hours_since_check END WHERE reg=?",
                        (typ, loc, status, None if status == "Available" else old["note"], time.time(), 1 if reset else 0, reg))
        else:
            con.execute("INSERT INTO airframes (reg, type, location, status, updated) VALUES (?,?,?,?,?)", (reg, typ, loc, status, time.time()))
    return jsonify(airframes())


def _clean_reg(v):
    return "".join(ch for ch in str(v or "").upper() if ch.isalnum() or ch == "-")[:10]


def _reg_pattern(old):
    return re.compile(r"(?<![A-Z0-9-])" + re.escape(old) + r"(?![A-Z0-9-])")


def _swap_reg(obj, old, new, pat=None):
    """Replaces the registration `old` wherever it appears as a whole word inside a JSON value, so both an
    airframe field ("N803PC") and a title ("Ferry N803PC to Miami") follow the rename, but "N803PCX" doesn't.
    Returns (value, changed)."""
    pat = pat or _reg_pattern(old)
    if isinstance(obj, str):
        out = pat.sub(new, obj)
        return out, out != obj
    if isinstance(obj, list):
        out, hit = [], False
        for x in obj:
            v, h = _swap_reg(x, old, new, pat)
            out.append(v)
            hit = hit or h
        return out, hit
    if isinstance(obj, dict):
        out, hit = {}, False
        for k, x in obj.items():
            v, h = _swap_reg(x, old, new, pat)
            out[k] = v
            hit = hit or h
        return out, hit
    return obj, False


RENAME_JSON_TABLES = ("live_missions", "jobs", "urgent", "events", "bot_events", "bookings")


def carry_reg_text(con, old, new):
    """Rewrites the registration inside missions, jobs, urgent requests, events and PIREP mission titles.
    Returns how many records changed. Also used by tools/fix_renamed_text.py for renames made before this existed."""
    pat, n = _reg_pattern(old), 0
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in RENAME_JSON_TABLES:
        if t not in tables:
            continue
        key = "id" if "id" in {c[1] for c in con.execute(f"PRAGMA table_info({t})")} else "rowid"
        for k, data in con.execute(f"SELECT {key}, data FROM {t} WHERE data LIKE ?", (f"%{old}%",)).fetchall():
            try:
                val, hit = _swap_reg(json.loads(data), old, new, pat)
            except (TypeError, ValueError):
                continue
            if hit:
                con.execute(f"UPDATE {t} SET data=? WHERE {key}=?", (json.dumps(val), k))
                n += 1
    for pid, title in con.execute("SELECT id, mission_title FROM pireps WHERE mission_title LIKE ?", (f"%{old}%",)).fetchall():
        fixed = pat.sub(new, title or "")
        if fixed != title:
            con.execute("UPDATE pireps SET mission_title=? WHERE id=?", (fixed, pid))
            n += 1
    return n


def rename_airframe(old, new):
    """Re-registers an airframe and carries everything with it: hours, cycles, location, name, its flight history,
    maintenance write-ups, and jobs or urgent requests that suggest it. Refuses while it's booked on a flight.
    Returns a summary of what moved; raises ValueError with a reason staff can read."""
    old, new = _clean_reg(old), _clean_reg(new)
    if not old or not new:
        raise ValueError("Enter the new registration.")
    if old == new:
        raise ValueError(f"{old} already has that registration.")
    with C["db"]() as con:
        row = con.execute("SELECT * FROM airframes WHERE reg=?", (old,)).fetchone()
        if not row:
            raise ValueError(f"{old} isn't in the fleet.")
        if row["status"] == "Booked":
            raise ValueError(f"{old} is booked on a flight. Finish or cancel that flight first, then rename it.")
        if con.execute("SELECT 1 FROM airframes WHERE reg=?", (new,)).fetchone():
            raise ValueError(f"{new} already exists in the fleet.")
        for (data,) in con.execute("SELECT data FROM bookings"):
            try:
                if _swap_reg(json.loads(data or "null"), old, new)[1]:
                    raise ValueError(f"A pilot has {old} on an open booking. Finish or cancel it first, then rename it.")
            except (TypeError, json.JSONDecodeError):
                pass
        moved = {"flights": 0, "write_ups": 0, "other": 0}
        con.execute("UPDATE airframes SET reg=?, updated=? WHERE reg=?", (new, time.time(), old))
        moved["flights"] = con.execute("UPDATE pireps SET airframe=? WHERE airframe=?", (new, old)).rowcount
        con.execute("UPDATE pireps SET registration=? WHERE registration=?", (new, old))
        moved["write_ups"] = con.execute("UPDATE maint SET reg=? WHERE reg=?", (new, old)).rowcount
        moved["other"] = carry_reg_text(con, old, new)
    return {"from": old, "to": new, **moved}


@bp.post("/api/staff/airframes/<reg>/rename")
def staff_airframe_rename(reg):
    try:
        out = rename_airframe(reg, (request.json or {}).get("to"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"renamed": out, "airframes": airframes()})


@bp.delete("/api/staff/airframes/<reg>")
def staff_airframe_delete(reg):
    with C["db"]() as con:
        row = con.execute("SELECT status FROM airframes WHERE reg=?", (reg,)).fetchone()
        if row and row["status"] == "Booked":
            return jsonify({"error": f"{reg} is booked on a flight."}), 409
        con.execute("DELETE FROM airframes WHERE reg=?", (reg,))
    return jsonify(airframes())


@bp.post("/api/staff/events")
def staff_event_save():
    b = request.json or {}
    ct = C["clean_text"]
    name = ct(b.get("name"), 80)
    try:
        start, end = dt.date.fromisoformat(b.get("start")), dt.date.fromisoformat(b.get("end"))
    except (TypeError, ValueError):
        return jsonify({"error": "Enter start and end dates."}), 400
    if not name or end < start:
        return jsonify({"error": "Give the event a name and an end date on or after the start."}), 400
    mult = max(1.0, min(3.0, C["num"](b.get("multiplier"), 1.25)))
    lst = lambda k: [ct(x, 40) for x in (b.get(k) or []) if ct(x)]
    eid = ct(b.get("id"), 60) or f"{name.lower().replace(' ', '-')}-{start.isoformat()}"
    e = {"id": eid, "name": name, "start": start.isoformat(), "end": end.isoformat(), "multiplier": round(mult, 2),
         "categories": lst("categories"), "regions": lst("regions"), "airports": [a.upper() for a in lst("airports")],
         "description": ct(b.get("description"), 500)}
    with C["db"]() as con:
        con.execute("INSERT OR REPLACE INTO events (id, data) VALUES (?,?)", (eid, json.dumps(e)))
    return jsonify(e)


@bp.delete("/api/staff/events/<eid>")
def staff_event_delete(eid):
    with C["db"]() as con:
        con.execute("DELETE FROM events WHERE id=?", (eid,))
    return jsonify({"ok": True})


@bp.post("/api/staff/site")
def staff_site():
    b = request.json or {}
    s = {k: C["clean_text"](b.get(k), 3000) for k in DEFAULT_SITE if k in b}
    if "discord_widget" in s:   # accepts the server ID or the whole widget code from Discord
        _m = re.search(r"\d{17,20}", s["discord_widget"]); s["discord_widget"] = _m.group(0) if _m else ""
    C["save_json"](C["DATA"] / "site.json", {**C["load_json"](C["DATA"] / "site.json", {}), **s})
    return jsonify(site())


# Request paths only read stored offers; mission_worker owns generation and expiry.
def _board_read(sql, params=()):
    import sqlite3
    from contextlib import closing
    from pathlib import Path
    with closing(sqlite3.connect((Path(C["DATA"]) / "logbook.db").resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as con:
        return [json.loads(r[0]) for r in con.execute(sql, params)]


def mission_board():
    board = _board_read("SELECT data FROM live_missions WHERE (status='open' AND expires>=?) OR (status='booked' AND pilot_id=?) ORDER BY created DESC", (time.time(), current_pilot_id()))
    ck = C["MISSIONS"].get(CHECKRIDE_ID)
    return ([ck] if ck else []) + board


def jobs_today():
    rows = _board_read("SELECT data FROM jobs WHERE (status='open' AND (day=? OR kind='contract')) OR (status='booked' AND pilot_id=?)", (_day(), current_pilot_id()))
    # Booked jobs must remain visible even after the offer's original expiry.
    booked = set()
    import sqlite3
    from contextlib import closing
    from pathlib import Path
    with closing(sqlite3.connect((Path(C["DATA"]) / "logbook.db").resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as con:
        booked = {r[0] for r in con.execute("SELECT id FROM jobs WHERE status='booked' AND pilot_id=?", (current_pilot_id(),))}
    return [r for r in rows if r.get("id") in booked or r.get("expires", float('inf')) >= time.time()]


def urgent_missions():
    return _board_read("SELECT data FROM urgent WHERE status='open' AND expires>=? ORDER BY created", (time.time(),))



@bp.get('/api/training/options')
def training_options():
    return jsonify(training.options(__import__(__name__)))

@bp.post('/api/training/preview')
def training_preview():
    try:return jsonify(training.resolve(__import__(__name__), request.get_json(silent=True)))
    except ValueError as e:return jsonify({'error':str(e)}),400
