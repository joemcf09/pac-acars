"""The PAC shop: pilots spend their wallet earnings on patches, crew-badge frames, jumpseat passes, aircraft
repositions and naming rights for an airframe. Every purchase is a wallet transaction of kind 'shop'."""
import json
import re
import time

from flask import Blueprint, jsonify, request

import va

bp = Blueprint("shop", __name__)

# Patches show on the pilot's profile and crew badge. Prices are in wallet dollars: a typical flight pays a few
# hundred to a few thousand, so a patch is a few flights and gold is a real goal.
PATCHES = {
    "night_cargo": {"name": "Night Cargo", "price": 3000, "colour": "#1d2a4a", "accent": "#f2c94c", "mark": "moon",
                    "blurb": "For the pilots who fly while the world sleeps."},
    "relief_wings": {"name": "Relief Wings", "price": 3000, "colour": "#0f5132", "accent": "#ffffff", "mark": "cross",
                     "blurb": "Humanitarian flying: medicine, shelter and relief, on time."},
    "heavy_metal": {"name": "Heavy Metal", "price": 5000, "colour": "#3a3a3a", "accent": "#c0c0c0", "mark": "jet",
                    "blurb": "Widebody freighters and the people who fly them."},
    "polar_route": {"name": "Polar Route", "price": 5000, "colour": "#0b4f6c", "accent": "#bfe9ff", "mark": "star",
                    "blurb": "Over the top: Anchorage and the long way round."},
    "cincinnati_hub": {"name": "CVG Hub Crew", "price": 4000, "colour": "#c80000", "accent": "#ffffff", "mark": "hub",
                       "blurb": "Home base pride: Cincinnati/Northern Kentucky."},
    "founders_era": {"name": "Founders' Era 2026", "price": 10000, "colour": "#111111", "accent": "#d4af37", "mark": "crown",
                     "until": "2026-12-31", "blurb": "Only on sale during PAC's first year. Never sold again."},
}
PATCHES.update({'miami_ramp': {'name': 'Miami Ramp Crew', 'price': 1500, 'colour': '#087e8b', 'accent': '#ffe7a8', 'mark': 'palm', 'blurb': 'Sunshine, salt air and cargo out of Miami.'}, 'anchorage_crew': {'name': 'Anchorage Crew', 'price': 2000, 'colour': '#173c50', 'accent': '#c5f6ec', 'mark': 'mountain', 'blurb': 'Northern skies and the Anchorage cargo crossroads.'}, 'milan_cargo': {'name': 'Milan Cargo Club', 'price': 2000, 'colour': '#174b36', 'accent': '#f1e6ce', 'mark': 'hub', 'blurb': 'Italian roots and freight through Malpensa.'}, 'island_hopper': {'name': 'Island Hopper', 'price': 1800, 'colour': '#164d83', 'accent': '#ffe087', 'mark': 'palm', 'blurb': 'A little Caribbean color for your crew badge.'}, 'classic_trijet': {'name': 'Classic Trijet', 'price': 2500, 'colour': '#73372e', 'accent': '#f4d49a', 'mark': 'jet', 'blurb': 'Three engines and a soft spot for classic freighters.'}, 'cargo_express': {'name': 'Cargo Express', 'price': 2200, 'colour': '#3c295d', 'accent': '#eacfff', 'mark': 'box', 'blurb': 'For the crew who keep freight moving.'}, 'ocean_crossing': {'name': 'Ocean Crossing', 'price': 3000, 'colour': '#172f50', 'accent': '#91d5ef', 'mark': 'waves', 'blurb': 'Open water, distant shores and long-haul cargo.'}, 'dawn_patrol': {'name': 'Dawn Patrol', 'price': 1800, 'colour': '#682c4e', 'accent': '#ffce82', 'mark': 'sun', 'blurb': 'First light on the ramp. Another day carrying cargo.'}})

# Frames go round the profile photo and the crew badge. A pilot owns any number and wears one.
FRAMES = {
    "red_stripe": {"name": "PAC Red Stripe", "price": 4000, "blurb": "The livery cheatline, round your crew badge."},
    "carbon": {"name": "Carbon", "price": 6000, "blurb": "Dark, woven and understated."},
    "silver": {"name": "Silver", "price": 12000, "blurb": "Brushed metal for the seasoned crew member."},
    "gold": {"name": "Gold", "price": 25000, "blurb": "For the pilots who've flown a lot of freight."},
}
# Passes: things that bend PAC's rules a little, priced so they stay special.
PERKS = {
    "ferry_discount_pass": {"name": "Ferry discount pass", "price": 20, "max": 3, "icon": "🎟️", "blurb": "25% off one paid aircraft reposition. Applied automatically; used only on success. No expiry. Hold up to three. Example: a $300 ferry becomes $225; including this $20 pass, you save $55. Free checkride travel needs no pass."},
    "jumpseat_pass": {"name": "Jumpseat pass", "price": 300, "max": 5, "icon": "🎫",
                      "blurb": "One free trip to any airport, used from the Jumpseat window. Hold up to five."},
    "hard_landing_pass": {"name": "Hard landing pass", "price": 10000, "max": 3, "icon": "🛬",
                          "blurb": "Turns one of your PIREPs held or rejected only for its landing (hard, bounced, high G or a low "
                                   "score) into an accepted, paid flight. Within 14 days of filing. Hold up to three."},
}
# Timed passes: active for a number of days from purchase; buying again adds the days on.
TIMED = {
    "fleet_pass_7": {"name": "Fleet pass · 7 days", "price": 1500, "days": 7, "icon": "🗝️",
                     "blurb": "Fly any PAC aircraft for a week, whatever your rank or type ratings. Your line checkride still comes first."},
    "fleet_pass_30": {"name": "Fleet pass · 30 days", "price": 5000, "days": 30, "icon": "🗝️",
                      "blurb": "A month of any aircraft in the fleet, from the 727 to the 747-8F, without the type ratings."},
}
# Pilot gear: each piece adds a percentage to the pay of every flight you file while it lasts (all gear together tops out at
# GEAR_CAP). Prices are a few flights for the small things and a real goal for the big ones.
GEAR = {
    "logbook_set": {"name": "Leather logbook & pen", "price": 1000, "bonus": 1, "days": 90, "icon": "📔",
                    "blurb": "Every hour in neat ink. +1% flight pay for 90 days."},
    "flight_bag": {"name": "Captain's flight bag", "price": 2500, "bonus": 1, "days": 180, "icon": "💼",
                   "blurb": "Charts, headset, snacks and the spare pen. +1% flight pay for 180 days."},
    "efb_tablet": {"name": "EFB tablet", "price": 6000, "bonus": 2, "days": 180, "icon": "📱",
                   "blurb": "Charts, performance and the OFP on your kneeboard. +2% flight pay for 180 days."},
    "anr_headset": {"name": "ANR headset", "price": 8000, "bonus": 2, "days": 180, "icon": "🎧",
                    "blurb": "Active noise reduction for the long freight legs. +2% flight pay for 180 days."},
    "chronograph": {"name": "Pilot's chronograph", "price": 20000, "bonus": 3, "days": 230, "icon": "⌚",
                    "blurb": "Block out, block in, to the second. +3% flight pay for 230 days."},
    "crew_motorbike": {"name": "Crew motorbike", "price": 25000, "bonus": 3, "days": 180, "icon": "🏍️",
                       "blurb": "From the crew car park to the ramp in style. +3% flight pay for 180 days."},
    "hypercar": {"name": "Hypercar", "price": 250000, "bonus": 5, "days": 365, "icon": "🏎️",
                 "blurb": "Hand-built in Italy, much like the airline's name. +5% flight pay for a year."},
}
COLLECTIBLES = {'mug': {'name': 'Night shift mug', 'price': 250, 'art': 'mug', 'blurb': 'A little company for those early departures.'}, 'tag': {'name': 'PAC flight bag tag', 'price': 400, 'art': 'tag', 'blurb': 'A small piece of the ramp, wherever you go.'}, 'uld': {'name': 'Mini cargo container', 'price': 1200, 'art': 'uld', 'blurb': 'Your favorite freight, scaled down for the shelf.'}, 'model737': {'name': '737 freighter desk model', 'price': 3500, 'art': 'plane', 'blurb': 'The everyday workhorse in PAC red.'}, 'model727': {'name': '727 classics desk model', 'price': 3500, 'art': 'plane', 'blurb': 'Three engines. Plenty of character. A tribute to the classics.'}, 'pennant': {'name': 'CVG home base pennant', 'price': 750, 'art': 'pennant', 'blurb': 'A little hometown pride for your crew corner.'}, 'miami': {'name': 'Miami crew pennant', 'price': 750, 'art': 'pennant', 'blurb': 'Sunshine, palm trees and another load ready to go.'}, 'plaque': {'name': 'Cargo crew desk plaque', 'price': 2000, 'art': 'plaque', 'blurb': 'For the crew who keep things moving.'}}

GEAR_CAP = 10                                   # most extra pay all gear together can add, in per cent
REPOSITION = {"base": 100, "per_nm": 0.20}      # have a PAC aircraft ferried to you, no flying needed
NAMING_PRICE = 40000                            # name an airframe: shown wherever its registration is
NAME_RE = re.compile(r"^[A-Za-z0-9 '.\-&]{3,24}$")


def _db():
    return va.C["db"]()


def _enabled():
    return bool(va.C["settings"]().get("shop_enabled", True))


def init_db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS shop_owned (pilot_id TEXT, item TEXT, qty INTEGER DEFAULT 1, bought REAL,
        PRIMARY KEY (pilot_id, item))""")
    if "expires" not in {r[1] for r in con.execute("PRAGMA table_info(shop_owned)")}:
        con.execute("ALTER TABLE shop_owned ADD COLUMN expires REAL")          # timed passes and gear
    cols = {r[1] for r in con.execute("PRAGMA table_info(airframes)")}
    if "name" not in cols:
        con.execute("ALTER TABLE airframes ADD COLUMN name TEXT")
        con.execute("ALTER TABLE airframes ADD COLUMN named_by TEXT")


def owned(pid, con=None):
    """What the pilot has: one-off items and passes by count, timed items only while they last."""
    con = con or _db()
    now = time.time()
    return {r["item"]: r["qty"] for r in con.execute("SELECT item, qty, expires FROM shop_owned WHERE pilot_id=? AND qty>0", (pid,))
            if not r["expires"] or r["expires"] > now}


def expiries(pid, con=None):
    con = con or _db()
    return {r["item"]: r["expires"] for r in con.execute("SELECT item, expires FROM shop_owned WHERE pilot_id=? AND expires>?",
                                                          (pid, time.time()))}


def gear_bonus(pid):
    """Extra flight pay from the pilot's active gear, in per cent (capped)."""
    try:
        have = owned(pid)
    except Exception:
        return 0
    return min(GEAR_CAP, sum(v["bonus"] for k, v in GEAR.items() if k in have))


def fleet_pass(pid):
    """When the pilot's fleet pass runs out (a timestamp), or None."""
    try:
        exp = expiries(pid)
    except Exception:
        return None
    t = max([exp[k] for k in TIMED if k in exp] or [0])
    return t or None


def pay_gear_bonus(pirep_id):
    """Called once a PIREP is paid: add the pilot's gear bonus on top of their flight pay and profit share."""
    with _db() as con:
        r = con.execute("SELECT pilot_id, flight_number FROM pireps WHERE id=?", (pirep_id,)).fetchone()
        if not r or con.execute("SELECT 1 FROM wallet WHERE pirep_id=? AND kind='gear_bonus'", (pirep_id,)).fetchone():
            return
        pct = gear_bonus(r["pilot_id"])
        if not pct:
            return
        base = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pirep_id=? AND kind IN ('flight_pay','profit_share')",
                           (pirep_id,)).fetchone()[0]
        extra = round(base * pct / 100, 2)
        if extra > 0:
            va.add_tx(r["pilot_id"], "gear_bonus", extra, f"Pilot gear bonus +{pct}% on {r['flight_number']}", pirep_id, con)


LANDING_FLAG = re.compile(r"^(Hard landing|Landing load|\d+ bounces|Score \d+ below)", re.I)
PASS_WINDOW_S = 14 * 86400


def landing_pass_eligible(pid, con=None):
    """The pilot's own recent PIREPs held or rejected only because of the landing."""
    con = con or _db()
    out = []
    for r in con.execute("""SELECT id, flight_number, dep, arr, filed_at, landing_rate, score, flags, review_status FROM pireps
            WHERE pilot_id=? AND demo=0 AND review_status IN ('Pending','Rejected') AND filed_at>? ORDER BY filed_at DESC""",
                         (pid, time.time() - PASS_WINDOW_S)):
        try:
            flags = json.loads(r["flags"] or "[]")
        except ValueError:
            flags = []
        if flags and all(LANDING_FLAG.match(str(f)) for f in flags):
            out.append({k: r[k] for k in ("id", "flight_number", "dep", "arr", "filed_at", "landing_rate", "score", "review_status")})
    return out


def use_landing_pass(pid, pirep_id):
    with _db() as con:
        ok = {p["id"] for p in landing_pass_eligible(pid, con)}
        if pirep_id not in ok:
            raise ValueError("A hard landing pass works on your own PIREPs from the last 14 days that were held or rejected "
                             "only because of the landing.")
        if not con.execute("UPDATE shop_owned SET qty=qty-1 WHERE pilot_id=? AND item='hard_landing_pass' AND qty>0",
                           (pid,)).rowcount:
            raise ValueError("You don't have a hard landing pass. They're in the PAC shop.")
        con.execute("UPDATE pireps SET review_status='Accepted', review_note=?, reviewed_at=? WHERE id=?",
                    ("Accepted with a hard landing pass from the PAC shop.", time.time(), pirep_id))
    va.pay_pirep(pirep_id)
    return catalogue(pid)


def _prefs(pid, con):
    r = con.execute("SELECT prefs FROM pilots WHERE id=?", (pid,)).fetchone()
    try:
        p = json.loads((r and r["prefs"]) or "{}")
    except (ValueError, TypeError):
        p = {}
    return p if isinstance(p, dict) else {}


def flair(pid):
    """What a pilot wears: their patches and the frame they've chosen. Shown on their profile and crew badge."""
    try:
        with _db() as con:
            have = owned(pid, con)
            frame = _prefs(pid, con).get("frame")
            shelf = _shelf(pid, con, have)
            featured = _featured_patches(pid, con, have)
    except Exception:
        return {"patches": [], "frame": None}
    patches = [{"id": k, **{x: v[x] for x in ("name", "colour", "accent", "mark", "blurb")}} for k, v in PATCHES.items() if k in have]
    return {"patches": [next(p for p in patches if p["id"] == k) for k in featured], "patch_count": len(patches), "frame": frame if frame in FRAMES and frame in have else None,
            "shelf": [{"id": k, **COLLECTIBLES[k]} for k in shelf]}


def _on_sale(item):
    until = item.get("until")
    return not until or time.strftime("%Y-%m-%d", time.gmtime()) <= until


def catalogue(pid):
    with _db() as con:
        have = owned(pid, con)
        frame = _prefs(pid, con).get("frame")
        shelf = _shelf(pid, con, have)
        featured = _featured_patches(pid, con, have)
        named = [dict(r) for r in con.execute("SELECT reg, type, name FROM airframes WHERE named_by=? AND name IS NOT NULL", (pid,))]
        exp = expiries(pid, con)
        eligible = landing_pass_eligible(pid, con)
    def entry(kind, k, v, **extra):
        return {"id": k, "kind": kind, "name": v["name"], "price": v["price"], "blurb": v["blurb"], "owned": have.get(k, 0),
                "on_sale": _on_sale(v), "until": v.get("until"), "icon": v.get("icon"), "expires": exp.get(k), **extra}
    return {"enabled": _enabled(), "balance": va.balance(pid),
            "collectibles": [entry("collectible", k, v, art=v["art"], displayed=k in shelf) for k,v in COLLECTIBLES.items()],
            "shelf": shelf, "featured_patches": featured,
            "patches": [entry("patch", k, v, colour=v["colour"], accent=v["accent"], mark=v["mark"]) for k, v in PATCHES.items()],
            "frames": [entry("frame", k, v, worn=frame == k) for k, v in FRAMES.items()],
            "perks": [entry("perk", k, v, max=v["max"]) for k, v in PERKS.items()],
            "timed": [entry("timed", k, v, days=v["days"]) for k, v in TIMED.items()],
            "gear": [entry("gear", k, v, bonus=v["bonus"], days=v["days"]) for k, v in GEAR.items()],
            "gear_bonus": gear_bonus(pid), "gear_cap": GEAR_CAP, "fleet_pass": fleet_pass(pid), "landing_eligible": eligible,
            "reposition": REPOSITION, "naming_price": NAMING_PRICE, "named": named, "location": va.pilot_location(pid)}


def _charge(con, pid, price, what):
    bal = va.balance(pid, con)
    if bal < price:
        raise ValueError(f"{what} costs ${price:,} and your wallet has ${bal:,.0f}. A few more flights and it's yours.")
    va.add_tx(pid, "shop", -price, what, None, con)


def buy(pid, item_id):
    if not _enabled():
        raise ValueError("The PAC shop is closed at the moment.")
    item = PATCHES.get(item_id) or FRAMES.get(item_id) or PERKS.get(item_id) or TIMED.get(item_id) or GEAR.get(item_id) or COLLECTIBLES.get(item_id)
    if not item:
        raise ValueError("That isn't in the PAC shop.")
    if not _on_sale(item):
        raise ValueError(f"{item['name']} is no longer on sale.")
    if item.get("days"):                          # timed: buying again adds the days on
        with _db() as con:
            con.execute("BEGIN IMMEDIATE")
            _charge(con, pid, item["price"], f"PAC shop: {item['name']}")
            cur = con.execute("SELECT expires FROM shop_owned WHERE pilot_id=? AND item=?", (pid, item_id)).fetchone()
            start = max(time.time(), (cur and cur["expires"]) or 0)
            con.execute("""INSERT INTO shop_owned (pilot_id, item, qty, bought, expires) VALUES (?,?,1,?,?)
                ON CONFLICT(pilot_id, item) DO UPDATE SET qty=1, bought=excluded.bought, expires=excluded.expires""",
                        (pid, item_id, time.time(), start + item["days"] * 86400))
        if item_id in GEAR:
            _announce(pid, item["name"], "gear")
        return catalogue(pid)
    with _db() as con:
        con.execute("BEGIN IMMEDIATE")
        have = owned(pid, con).get(item_id, 0)
        limit = item.get("max", 1)
        if have >= limit:
            raise ValueError(f"You already have {item['name']}." if limit == 1 else f"You can hold up to {limit} {item['name'].lower()}es.")
        _charge(con, pid, item["price"], f"PAC shop: {item['name']}")
        con.execute("""INSERT INTO shop_owned (pilot_id, item, qty, bought) VALUES (?,?,1,?)
            ON CONFLICT(pilot_id, item) DO UPDATE SET qty=qty+1, bought=excluded.bought""", (pid, item_id, time.time()))
        if item_id in FRAMES and not _prefs(pid, con).get("frame"):
            _wear(con, pid, item_id)          # the first frame bought goes straight on
    if item_id in PATCHES or item_id in FRAMES:
        _announce(pid, item["name"], "patch" if item_id in PATCHES else "frame")
    return catalogue(pid)


def _announce(pid, name, kind, extra=""):
    try:
        import botlink
        botlink.shop_purchase(pid, name, kind, extra)
    except Exception as e:
        print(f"Discord shop announcement skipped: {e}")


def _wear(con, pid, frame):
    p = _prefs(pid, con)
    if frame:
        p["frame"] = frame
    else:
        p.pop("frame", None)
    con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(p), pid))


def wear(pid, frame):
    with _db() as con:
        if frame and (frame not in FRAMES or not owned(pid, con).get(frame)):
            raise ValueError("Buy that frame first.")
        _wear(con, pid, frame or None)
    return catalogue(pid)


def use_pass(con, pid):
    """Spend one jumpseat pass. Returns False if the pilot has none."""
    cur = con.execute("UPDATE shop_owned SET qty=qty-1 WHERE pilot_id=? AND item='jumpseat_pass' AND qty>0", (pid,))
    return cur.rowcount > 0


def reposition_quote(reg, to, pid=None, con=None):
    if con is None:
        from contextlib import closing
        with closing(_db()) as connection:
            return reposition_quote(reg, to, pid, connection)
    a = con.execute("SELECT * FROM airframes WHERE reg=?", (reg,)).fetchone()
    if not a: raise ValueError("That aircraft isn't in the PAC fleet.")
    if a['location'] == to: raise ValueError(f"{reg} is already at {to}.")
    if a['status'] != 'Available': raise ValueError(f"{reg} is {a['status'].lower()}, so it can't be moved now.")
    f,t=va.C['airport_obj'](a['location']),va.C['airport_obj'](to)
    if not f or not t: raise ValueError('Unknown airport.')
    nm=va.C['gc_distance_nm'](f['lat'],f['lon'],t['lat'],t['lon'])
    regular=round(REPOSITION['base']+REPOSITION['per_nm']*nm)
    use=bool(pid and owned(pid,con).get('ferry_discount_pass',0))
    cost=round(regular*.75) if use else regular
    return dict(reg=reg,type=a['type'], **{'from':a['location']},to=to,distance_nm=round(nm),regular_cost=regular,cost=cost,savings=regular-cost,use_pass=use)


def reposition(pid, reg, expected=None):
    if not _enabled(): raise ValueError('The PAC shop is closed at the moment.')
    from contextlib import closing
    with closing(_db()) as con, con:
        con.execute('BEGIN IMMEDIATE')
        to=va.pilot_location(pid)
        q=reposition_quote(reg,to,pid,con)
        if not isinstance(expected,dict) or any(expected.get(k)!=q[k] for k in ('from','to','cost','use_pass')):
            raise ValueError('Your ferry quote has changed or expired. Please request a new quote before paying.')
        note=f"PAC shop: {reg} ferried {q['from']} to {to} ({q['distance_nm']:,} nm)"
        if q['use_pass']: note+=f" â€” ferry pass saved ${q['savings']}"
        _charge(con,pid,q['cost'],note)
        cur=con.execute("UPDATE airframes SET location=?,updated=?,stand=NULL WHERE reg=? AND status='Available' AND location=?",(to,time.time(),reg,q['from']))
        if cur.rowcount!=1: raise ValueError('Aircraft is no longer available. No charge or pass was used.')
        if q['use_pass']:
            cur=con.execute("UPDATE shop_owned SET qty=qty-1 WHERE pilot_id=? AND item='ferry_discount_pass' AND qty>0",(pid,))
            if cur.rowcount!=1: raise ValueError('Pass is no longer available. Please request a new quote.')
    return {**q,'balance':va.balance(pid)}


def name_airframe(pid, reg, name):
    if not _enabled():
        raise ValueError("The PAC shop is closed at the moment.")
    name = " ".join(str(name or "").split())
    if not NAME_RE.match(name):
        raise ValueError("Names are 3 to 24 letters, numbers, spaces and simple punctuation.")
    with _db() as con:
        a = con.execute("SELECT reg, name, named_by FROM airframes WHERE reg=?", (reg,)).fetchone()
        if not a:
            raise ValueError("That aircraft isn't in the PAC fleet.")
        if a["name"] and a["named_by"] != pid:
            raise ValueError(f"{reg} is already named “{a['name']}”.")
        if con.execute("SELECT 1 FROM airframes WHERE lower(name)=lower(?) AND reg!=?", (name, reg)).fetchone():
            raise ValueError("Another PAC aircraft already has that name.")
        renaming = a["name"] and a["named_by"] == pid
        _charge(con, pid, 0 if renaming else NAMING_PRICE, f"PAC shop: naming rights to {reg} (“{name}”)")
        con.execute("UPDATE airframes SET name=?, named_by=? WHERE reg=?", (name, pid, reg))
    if not renaming:
        _announce(pid, name, "naming", reg)
    return catalogue(pid)


# ---------------------------------------------------------------- routes
def _err(e, code=400):
    return jsonify({"error": str(e)}), code


@bp.get("/api/shop")
def shop_get():
    return jsonify(catalogue(va.current_pilot_id()))


@bp.post("/api/shop/buy")
def shop_buy():
    try:
        return jsonify(buy(va.current_pilot_id(), str((request.json or {}).get("item") or "")))
    except ValueError as e:
        return _err(e)


@bp.post("/api/shop/use")
def shop_use():
    b = request.json or {}
    if b.get("item") != "hard_landing_pass":
        return _err("That item is used elsewhere: jumpseat passes in the Jumpseat window, fleet passes and gear work by themselves.")
    try:
        return jsonify(use_landing_pass(va.current_pilot_id(), int(b.get("pirep_id") or 0)))
    except ValueError as e:
        return _err(e)


@bp.post("/api/shop/wear")
def shop_wear():
    try:
        return jsonify(wear(va.current_pilot_id(), (request.json or {}).get("frame")))
    except ValueError as e:
        return _err(e)


@bp.post("/api/shop/reposition/quote")
def shop_reposition_quote():
    try:
        return jsonify(reposition_quote(str((request.json or {}).get("reg") or "").upper(), va.pilot_location(), va.current_pilot_id()))
    except ValueError as e:
        return _err(e)


@bp.post("/api/shop/reposition")
def shop_reposition():
    try:
        return jsonify(reposition(va.current_pilot_id(), str((request.json or {}).get("reg") or "").upper(), (request.json or {}).get("quote")))
    except ValueError as e:
        return _err(e)


@bp.post("/api/shop/name")
def shop_name():
    b = request.json or {}
    try:
        return jsonify(name_airframe(va.current_pilot_id(), str(b.get("reg") or "").upper(), b.get("name")))
    except ValueError as e:
        return _err(e)


@bp.post("/api/staff/shop/name")
def staff_clear_name():
    """Staff remove an airframe's name (no refund), e.g. if it isn't suitable."""
    reg = str((request.json or {}).get("reg") or "").upper()
    with _db() as con:
        con.execute("UPDATE airframes SET name=NULL, named_by=NULL WHERE reg=?", (reg,))
    return jsonify({"ok": True})


def _shelf(pid, con, have):
    saved = _prefs(pid, con).get("shelf", [])
    if not isinstance(saved, list):
        return []
    result = []
    for k in saved:
        if isinstance(k, str) and k in COLLECTIBLES and have.get(k) and k not in result:
            result.append(k)
    return result[:3]


def set_shelf(pid, items):
    if not isinstance(items, list) or len(items) > 3 or any(not isinstance(k, str) for k in items):
        raise ValueError("Choose up to three owned collectibles.")
    if len(set(items)) != len(items):
        raise ValueError("Each collectible can appear only once.")
    with _db() as con:
        con.execute("BEGIN IMMEDIATE")
        have = owned(pid, con)
        if any(k not in COLLECTIBLES or not have.get(k) for k in items):
            raise ValueError("Buy each collectible before displaying it.")
        prefs = _prefs(pid, con)
        prefs["shelf"] = items
        con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(prefs), pid))
    return catalogue(pid)


@bp.post("/api/shop/shelf")
def shop_shelf():
    body = request.get_json(silent=True)
    try:
        return jsonify(set_shelf(va.current_pilot_id(), body.get("items") if isinstance(body, dict) else None))
    except ValueError as e:
        return _err(e)




def _featured_patches(pid, con, have):
    saved = _prefs(pid, con).get("featured_patches")
    if saved is None:
        return [k for k in PATCHES if have.get(k)][:3]
    if not isinstance(saved, list):
        return []
    result = []
    for k in saved:
        if isinstance(k, str) and k in PATCHES and have.get(k) and k not in result:
            result.append(k)
    return result[:3]


def set_featured_patches(pid, items):
    if not isinstance(items, list) or len(items) > 3 or any(not isinstance(k, str) for k in items):
        raise ValueError("Choose up to three owned patches.")
    if len(set(items)) != len(items):
        raise ValueError("Each patch can appear only once.")
    with _db() as con:
        con.execute("BEGIN IMMEDIATE")
        have = owned(pid, con)
        if any(k not in PATCHES or not have.get(k) for k in items):
            raise ValueError("You can only feature patches you own.")
        prefs = _prefs(pid, con)
        prefs["featured_patches"] = items
        con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(prefs), pid))
    return catalogue(pid)


@bp.post("/api/shop/featured-patches")
def shop_featured_patches():
    body = request.get_json(silent=True)
    try:
        return jsonify(set_featured_patches(va.current_pilot_id(), body.get("items") if isinstance(body, dict) else None))
    except ValueError as e:
        return _err(e)
