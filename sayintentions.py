"""SayIntentions.AI VA-Link.

PAC is in the SayIntentions.AI Virtual Airline Alliance. Through VA-Link, PAC tells each pilot's AI dispatcher,
cabin crew, co-pilot and SkyOps about the airline and about the flight they've booked, so the voices in the cockpit
know the flight number, the cargo, the deadline, the aircraft, the stand and PAC's procedures.

Two keys are needed for every update (see the VA-Link documentation):
  * PAC's VA key (va_api_key): a staff setting, kept on the server and never sent to a browser or to PAC ACARS.
  * the pilot's own SayIntentions API key (api_key): PAC ACARS reads it from the pilot's
    %LOCALAPPDATA%\\SayIntentionsAI\\flight.json, or the pilot pastes it on the Downloads page.

Updates go to https://apipri.sayintentions.ai/sapi/importVAData whenever a pilot books, changes or finishes a
flight, in the background so the website never waits on SayIntentions."""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://apipri.sayintentions.ai/sapi/importVAData"
KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")
MAX_FIELD = 12000            # keep each section a sensible size for the AI's context

C = {}                        # context from app.py: db, settings, FLEET, AIRPORTS, load_booking, load_profile, va
_status = {}                  # pilot id -> {"time", "ok", "error", "reason"}
_lock = threading.Lock()
_pending = {}                 # pilot id -> timer, so a burst of changes becomes one update


def init(ctx):
    C.update(ctx)
    with C["db"]() as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(pilots)")}
        if "si_key" not in cols:
            con.execute("ALTER TABLE pilots ADD COLUMN si_key TEXT")       # the pilot's SayIntentions API key


def settings():
    return C["settings"]()


def ready(st=None):
    st = st or settings()
    return bool(st.get("si_enabled") and (st.get("si_va_key") or "").strip())


def pilot_key(pid):
    with C["db"]() as con:
        r = con.execute("SELECT si_key FROM pilots WHERE id=?", (pid,)).fetchone()
    return (r["si_key"] or "").strip() if r else ""


def set_pilot_key(pid, key):
    key = str(key or "").strip()
    if key and not KEY_RE.match(key):
        raise ValueError("That doesn't look like a SayIntentions API key. Copy it from your SayIntentions account page.")
    with C["db"]() as con:
        old = con.execute("SELECT si_key FROM pilots WHERE id=?", (pid,)).fetchone()
        con.execute("UPDATE pilots SET si_key=? WHERE id=?", (key or None, pid))
    return key != ((old and old["si_key"]) or "")


def status(pid):
    st = settings()
    s = dict(_status.get(pid) or {})
    return {"enabled": bool(st.get("si_enabled")), "ready": ready(st), "key_set": bool(pilot_key(pid)),
            "coupon": (st.get("si_coupon") or "").strip(), "frequency": (st.get("si_dispatcher_freq") or "").strip(),
            "last": s.get("time"), "ok": s.get("ok"), "error": s.get("error"), "reason": s.get("reason")}


# ---------------------------------------------------------------- what the AI is told
def _clip(text):
    text = text.strip()
    return text if len(text) <= MAX_FIELD else text[:MAX_FIELD - 20].rstrip() + "\n[…]"


def _airport(icao):
    a = C["AIRPORTS"].get(icao) or {}
    return f"{icao} ({a.get('name') or a.get('city') or icao})"


def _hm(minutes):
    minutes = int(minutes or 0)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _airline_block(st):
    notes = (st.get("si_notes") or "").strip()
    return "\n".join(x for x in [
        "Virtual airline: Pagani Air Cargo (PAC), a cargo airline. ICAO PAC, radio callsign PAGANI.",
        "Slogan: \"Move the Impossible!\"",
        "Main hub: Cincinnati/Northern Kentucky International (KCVG). Operations Control is in Cincinnati.",
        "What PAC flies: humanitarian relief, cold-chain medicine, AOG aircraft parts, heavy lift, premium and live "
        "animal charters, and scheduled freight, across a worldwide network.",
        "PAC is all-cargo: there are never passengers. People on board besides the pilots are crew or supernumeraries "
        "travelling with the cargo (grooms with horses, couriers with art, keepers with animals, loadmasters).",
        "Company contact: PAC Operations Control, ops@pac-va.com.",
        f"Airline notes from PAC staff:\n{notes}" if notes else "",
    ] if x)


SOPS = """PAC standard operating procedures:
- Every flight is planned in SimBrief with ICAO PAC and flown from stand to stand: PAC's assigned stand where there is one, otherwise a cargo stand on the cargo ramp, never a passenger gate.
- 250 kt or less below 10,000 ft. Stable approach by 1,000 ft above the runway.
- Target a landing softer than 400 fpm with no bounce. PAC ACARS records the flight and scores it automatically.
- On-time delivery matters: the block time target is in the briefing. Late deliveries earn less.
- Fuel: plan with SimBrief; PAC pays for fuel, so carry what's needed, not tankering for its own sake.
- Faults found before or during the flight are reported in PAC ACARS so maintenance can follow up."""


def _flight_block(pid, booking):
    st = settings()
    FLEET, va = C["FLEET"], C["va"]
    m = booking["mission"]
    ac = FLEET.get(booking.get("aircraft"), {})
    ofp = booking.get("ofp") or {}
    fn = booking.get("flight_number") or m.get("id", "")
    num = re.sub(r"\D", "", str(fn))
    lines = [f"Booked flight: {fn} (callsign PAGANI {num or fn})",
             f"Mission: {m.get('title', '')}",
             f"Route: {_airport(m['origin']['icao'])} to {_airport(m['destination']['icao'])}"]
    if m.get("category") or m.get("priority"):
        lines.append(f"Kind of flight: {m.get('category') or 'Freight'}, priority {m.get('priority') or 'Standard'}")
    if m.get("cargo"):
        lines.append(f"Cargo: {m['cargo']}, {int(m.get('payload_lbs') or 0):,} lb")
    if m.get("briefing"):
        lines.append(f"Briefing: {m['briefing']}")
    if m.get("target_block_min"):
        lines.append(f"Block time target: {_hm(m['target_block_min'])}")
    if m.get("deadline"):
        lines.append(f"Deadline: {time.strftime('%d %b %H:%MZ', time.gmtime(m['deadline']))}")
    lines.append(f"Aircraft: {ac.get('name', booking.get('aircraft', ''))}"
                 + (f", registration {booking['airframe']}" if booking.get("airframe") else ""))
    reg = booking.get("airframe")
    if reg:
        try:
            with C["db"]() as con:
                a = con.execute("SELECT name FROM airframes WHERE reg=?", (reg,)).fetchone()
                mx = [dict(r) for r in con.execute("SELECT ata, description, severity FROM maint WHERE reg=? AND status='open'", (reg,))]
            if a and a["name"]:
                lines.append(f"Aircraft name: \"{a['name']}\"")
            if mx:
                lines.append("Open maintenance items (deferred, flight may proceed): "
                             + "; ".join(f"ATA {int(i['ata'] or 0):02d} {i['description']} ({i['severity']})" for i in mx[:6]))
        except Exception:
            pass
        for which, icao in (("dep", m["origin"]["icao"]), ("arr", m["destination"]["icao"])):
            try:
                s = va.assign_stand(icao, booking.get("aircraft"), fn, which, reg if which == "dep" else None)
            except Exception:
                s = None
            if s and s.get("stand"):
                lines.append(f"{'Departure' if which == 'dep' else 'Arrival'} stand at {icao}: PAC stand {s['stand']}")
            elif which == "arr":
                lines.append(f"Arrival stand at {icao}: a cargo stand on the cargo ramp, never a passenger gate (this is a freighter)")
    if ofp:
        if ofp.get("route"):
            lines.append(f"Filed route: {ofp['route']}")
        if ofp.get("cruise_ft"):
            lines.append(f"Cruise: FL{int(ofp['cruise_ft']) // 100}")
        if ofp.get("alternate"):
            alt = ofp["alternate"]
            lines.append(f"Alternate: {alt.get('icao') if isinstance(alt, dict) else alt}")
        fuel = [(k, ofp.get(f"{k}_fuel_lbs")) for k in ("taxi", "trip", "reserve", "block")]
        if any(v for _, v in fuel):
            lines.append("Fuel plan (lb): " + ", ".join(f"{k} {int(v):,}" for k, v in fuel if v))
        w = [(k.upper(), ofp.get(f"{k}_lbs")) for k in ("zfw", "tow", "ldw")]
        if any(v for _, v in w):
            lines.append("Weights (lb): " + ", ".join(f"{k} {int(v):,}" for k, v in w if v))
        if ofp.get("est_block_min"):
            lines.append(f"Planned block time: {_hm(ofp['est_block_min'])}")
    else:
        lines.append("No SimBrief plan imported into PAC yet.")
    price = st.get("fuel_price_gal")
    if price:
        lines.append(f"PAC's contract jet fuel price: ${float(price):.2f} per US gallon")
    return "\n".join(lines)


def _pilot_block(pid):
    va = C["va"]
    try:
        prof = C["load_profile"](pid)
        car = va.career(pid)
    except Exception:
        return ""
    bits = [f"Captain: {prof.get('name', pid)}, PAC pilot {pid}, rank {car.get('rank', '')}",
            f"PAC experience: {car.get('flights', 0)} accepted flights, {car.get('hours', 0)} block hours"
            + (f", average score {car['avg_score']}" if car.get("avg_score") else "")]
    if prof.get("base"):
        bits.append(f"Home base: {prof['base']}")
    return "\n".join(bits)


def build(pid):
    """The four VA-Link sections for this pilot, from their PAC booking (if any) and the airline."""
    st = settings()
    booking = C["load_booking"](pid)
    airline, pilot = _airline_block(st), _pilot_block(pid)
    flight = _flight_block(pid, booking) if booking else "The pilot has no PAC flight booked right now."
    category = ((booking or {}).get("mission") or {}).get("category") or ""
    crew = "\n\n".join([airline, pilot, flight,
        "Cabin crew guidance: this is a freighter, so there's no passenger service. Speak to the pilots and any "
        "supernumeraries as fellow PAC crew: friendly, professional, brief. Mention the cargo and why it matters "
        "when it suits the moment (relief and medicine reach people who need them). Safety briefings are for the "
        "people actually on board."])
    dispatcher = "\n\n".join([airline, flight, pilot, SOPS,
        "Dispatcher guidance: you are PAC Operations Control in Cincinnati. Answer questions about this flight, the "
        "cargo, fuel, stands, the aircraft and PAC procedures from the information above. If something isn't here, "
        "say so plainly rather than inventing it."])
    copilot = "\n\n".join([airline, pilot, flight, SOPS,
        "First officer guidance: a calm, capable PAC first officer who knows the cargo and the deadline, flies by "
        "PAC's procedures, speaks up about safety, and takes pride in delivering on time."])
    skyops = "\n\n".join([airline, flight,
        f"SkyOps guidance: treat {category.lower() or 'this'} flying as a mission with a clear objective: get the "
        "cargo there safely and on time. Humanitarian and medical loads come first; heavy-lift loads need smooth "
        "handling; live animals need gentle climbs and descents."])
    return {k: _clip(v) for k, v in (("crew_data", crew), ("dispatcher_data", dispatcher),
                                     ("copilot_data", copilot), ("skyops_data", skyops))}


# ---------------------------------------------------------------- sending
def _post(api_key, va_key, data, timeout=15):
    body = urllib.parse.urlencode({"api_key": api_key, "payload": json.dumps({"va_api_key": va_key, **data})}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/x-www-form-urlencoded",
                                                               "User-Agent": "PAC-VA/1.0 (+https://pac-va.com)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        return False, f"SayIntentions answered {e.code}: {text[:200] or e.reason}"
    except Exception as e:
        return False, f"Couldn't reach SayIntentions ({e.__class__.__name__})."
    try:
        j = json.loads(text)
    except ValueError:
        return False, f"Unexpected answer from SayIntentions: {text[:200]}"
    if str(j.get("status", "")).upper() == "OK":
        return True, None
    return False, str(j.get("error") or j.get("message") or j.get("status") or text)[:300]


def push_now(pid, reason=""):
    """Send this pilot's flight and PAC's details to SayIntentions. Returns (ok, error)."""
    st = settings()
    if not ready(st):
        return False, "SayIntentions isn't set up: staff add PAC's VA-Link key in Staff › Site and rules."
    key = pilot_key(pid)
    if not key:
        return False, "No SayIntentions API key for this pilot yet."
    try:
        data = build(pid)
    except Exception as e:
        ok, err = False, f"PAC couldn't put the flight details together ({e.__class__.__name__})."
    else:
        ok, err = _post(key, st["si_va_key"].strip(), data)
    with _lock:
        _status[pid] = {"time": time.time(), "ok": ok, "error": err, "reason": reason}
    if not ok:
        print(f"SayIntentions update for {pid} failed: {err}")
    return ok, err


def notify(pid, reason="", delay=2.0):
    """Ask for an update soon, in the background. Several changes in a row become one update."""
    if not pid or not ready() or not pilot_key(pid):
        return
    with _lock:
        t = _pending.pop(pid, None)
        if t:
            t.cancel()
        t = threading.Timer(delay, lambda: (_pending.pop(pid, None), push_now(pid, reason)))
        t.daemon = True
        _pending[pid] = t
        t.start()
