"""The weekly PAC group flight: one route, one departure time, everyone flies it together.

Runs itself: with no staff input, it alternates out of Cincinnati and back again on 737-friendly scheduled routes
(250 to 1,000 nm), departing on the configured weekday and time (UTC). Staff can switch it off, move the day and
time, or set this week's route, title and briefing themselves. Pilots sign up with one click; the page shows who's
coming and, afterward, who flew it (an accepted PIREP on that route within 18 hours of the start).
Visitors can see the page too: it's a recruitment tool.
"""
import datetime as dt
import hashlib
import json
import sqlite3
import time
from contextlib import closing

from flask import jsonify, request

HOME = "KCVG"
DEFAULTS = {"enabled": True, "weekday": 5, "time": "23:00", "network": "VATSIM",
            "voice": "PAC Discord · Group flight voice channel",
            "briefing": "Meet on Discord 15 minutes before departure. Book the flight on the website, sign the release and "
                        "push back together. Fly at your own pace after takeoff; we regroup on the ground at the "
                        "destination for screenshots and landing rates."}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NETWORKS = ("VATSIM", "IVAO", "Either network", "Offline")


def register(app, g):
    def db():
        c = sqlite3.connect(g["DB_PATH"], timeout=10)
        c.row_factory = sqlite3.Row
        return c

    with closing(db()) as c, c:
        c.execute("CREATE TABLE IF NOT EXISTS group_flight_config (key TEXT PRIMARY KEY, data TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS group_flight_signups (event TEXT NOT NULL, pilot TEXT NOT NULL, name TEXT NOT NULL, "
                  "aircraft TEXT NOT NULL DEFAULT '', joined REAL NOT NULL, PRIMARY KEY (event, pilot))")

    def get(key, default):
        with closing(db()) as c:
            r = c.execute("SELECT data FROM group_flight_config WHERE key=?", (key,)).fetchone()
        return {**default, **json.loads(r["data"])} if r and isinstance(default, dict) else (json.loads(r["data"]) if r else default)

    def put(key, data):
        with closing(db()) as c, c:
            c.execute("INSERT OR REPLACE INTO group_flight_config (key, data) VALUES (?,?)", (key, json.dumps(data)))

    def config():
        return get("config", DEFAULTS)

    def start_for(day, cfg):
        hh, mm = (int(x) for x in cfg["time"].split(":"))
        return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=dt.timezone.utc)

    def upcoming(cfg, now=None, offset=0):
        """The next start whose flight is still on (it stays 'current' until 4 hours after departure)."""
        now = now or dt.datetime.now(dt.timezone.utc)
        d = now.date() - dt.timedelta(days=7)
        while d.weekday() != cfg["weekday"]:
            d += dt.timedelta(days=1)
        while start_for(d, cfg) + dt.timedelta(hours=4) < now:
            d += dt.timedelta(days=7)
        return start_for(d + dt.timedelta(days=7 * offset), cfg)

    def pairs():
        """Out-and-back pairs from Cincinnati: KCVG to X one week, X back to KCVG the next, so the pilots and aircraft
        that flew out are already in place for the return. Both legs are in the scheduled network and 737-friendly."""
        by = {(r["origin"]["icao"], r["destination"]["icao"]): r for r in g["ROUTES"].values()}
        ok = lambda r: r and "B738F" in r.get("aircraft", []) and 250 <= r.get("distance_nm", 0) <= 1000
        out = [(r, by.get((r["destination"]["icao"], HOME))) for r in g["ROUTES"].values() if r["origin"]["icao"] == HOME and ok(r)]
        return sorted([(a, b) for a, b in out if ok(b)], key=lambda x: x[0]["id"])

    def auto_route(event_id):
        ps = pairs()
        if not ps:
            return None
        week = (dt.date.fromisoformat(event_id) - dt.date(2026, 1, 3)).days // 7   # week 0: the first Saturday of 2026
        h = int(hashlib.md5(f"group-flight-pair-{week // 2}".encode()).hexdigest(), 16)
        out, back = ps[h % len(ps)]
        return out if week % 2 == 0 else back

    def airport(icao):
        a = g["AIRPORTS"].get(icao) or {}
        return {"icao": icao, "name": a.get("name", icao), "city": a.get("city", ""), "country": a.get("country", ""),
                "lat": a.get("lat"), "lon": a.get("lon")}

    def event_for(start, cfg):
        eid = start.date().isoformat()
        o = get("event:" + eid, {})
        if o.get("time"):
            hh, mm = (int(x) for x in o["time"].split(":"))
            start = start.replace(hour=hh, minute=mm)
        route = g["ROUTES"].get(o.get("route_id")) if o.get("route_id") else None
        if not route and not (o.get("dep") and o.get("arr")):
            route = auto_route(eid)
        if route:
            dep, arr = route["origin"]["icao"], route["destination"]["icao"]
            aircraft = [a for a in route["aircraft"] if a in g["FLEET"] and not g["FLEET"][a].get("retired")]
            dist, cargo, rid = route.get("distance_nm"), route.get("cargo", ""), route["id"]
        else:
            dep, arr, rid, cargo = o["dep"], o["arr"], None, o.get("cargo", "General cargo")
            aircraft = [a for a in (o.get("aircraft") or ["B738F"]) if a in g["FLEET"]]
            a1, a2 = airport(dep), airport(arr)
            from sim_sources import gc_distance_nm
            dist = round(gc_distance_nm(a1["lat"], a1["lon"], a2["lat"], a2["lon"])) if None not in (a1["lat"], a2["lat"]) else None
        da, aa = airport(dep), airport(arr)
        city = lambda a, c: (a["city"] or c).split(" / ")[0]
        title = o.get("title") or f"{city(da, dep)} to {city(aa, arr)}"
        return {"id": eid, "start": int(start.timestamp()), "dep": da, "arr": aa, "distance_nm": dist, "route_id": rid, "cargo": cargo,
                "aircraft": [{"code": a, "name": g["FLEET"][a].get("name", a)} for a in aircraft],
                "title": title, "briefing": o.get("briefing") or cfg["briefing"], "network": o.get("network") or cfg["network"],
                "voice": cfg["voice"], "custom": bool(o)}

    def signups(eid):
        with closing(db()) as c:
            return [dict(r) for r in c.execute("SELECT pilot, name, aircraft, joined FROM group_flight_signups WHERE event=? ORDER BY joined", (eid,))]

    def flown(ev):
        s = ev["start"]
        with closing(db()) as c:
            rows = c.execute("SELECT DISTINCT p.pilot_id, pl.name FROM pireps p LEFT JOIN pilots pl ON pl.id=p.pilot_id "
                             "WHERE p.dep=? AND p.arr=? AND p.filed_at BETWEEN ? AND ? AND p.demo=0 AND p.status!='Failed' "
                             "AND p.review_status!='Rejected'", (ev["dep"]["icao"], ev["arr"]["icao"], s - 3600, s + 18 * 3600)).fetchall()
        return [{"pilot": r["pilot_id"], "name": g["va"].short_name(r["name"] or r["pilot_id"])} for r in rows]

    def public(ev, me=None):
        su = signups(ev["id"])
        done = flown(ev) if ev["start"] < time.time() else []
        out = {**ev, "signups": [{"name": g["va"].short_name(x["name"]), "aircraft": x["aircraft"]} for x in su],
               "count": len(su), "flown": [x["name"] for x in done]}
        if me:
            mine = next((x for x in su if x["pilot"] == me["id"]), None)
            out["me"] = {"signed_up": bool(mine), "aircraft": mine["aircraft"] if mine else "", "flew": any(x["pilot"] == me["id"] for x in done)}
        return out

    def announcement(ev, site):
        ac = ", ".join(a["name"] for a in ev["aircraft"][:4])
        dist = f" · {ev['distance_nm']:,} nm" if ev.get("distance_nm") else ""
        return (f"**✈️ PAC weekly group flight: {ev['title']}**\n"
                f"**{ev['dep']['icao']} → {ev['arr']['icao']}**{dist}\n"
                f"🕒 <t:{ev['start']}:F> (<t:{ev['start']}:R>), shown in your own time zone\n"
                f"🛫 Aircraft: {ac}\n🌐 Network: {ev['network']}\n🎧 {ev['voice']}\n\n"
                f"{ev['briefing']}\n\nSign up and book it here: {site.rstrip('/')}/#groupflight\n"
                f"New to PAC? Joining is free: {site.rstrip('/')}")

    def site_url():
        import auth
        return auth.site_address(g["va"].site().get("public_url", "")) or "https://pac-va.com"

    @app.get("/api/public/group-flight")
    def group_flight_public():
        import auth
        cfg = config()
        me = auth.current()
        if not cfg["enabled"]:
            r = {"enabled": False}
        else:
            now = dt.datetime.now(dt.timezone.utc)
            cur = upcoming(cfg, now)
            ev = event_for(cur, cfg)
            nxt = [event_for(upcoming(cfg, now, i), cfg) for i in (1, 2)]
            past = []
            for i in range(1, 5):
                ps = cur - dt.timedelta(days=7 * i)
                pe = event_for(ps, cfg)
                past.append({"id": pe["id"], "start": pe["start"], "title": pe["title"], "dep": pe["dep"]["icao"], "arr": pe["arr"]["icao"],
                             "signed": len(signups(pe["id"])), "flew": len(flown(pe))})
            r = {"enabled": True, "event": public(ev, me), "next": [{k: e[k] for k in ("id", "start", "title")} | {"dep": e["dep"]["icao"], "arr": e["arr"]["icao"]} for e in nxt],
                 "past": past, "schedule": f"Every {DAYS[cfg['weekday']]} at {cfg['time']} UTC"}
        if me and me.get("staff"):
            r["staff"] = {"config": cfg, "days": DAYS, "networks": NETWORKS}
            if r.get("enabled"):
                r["staff"]["override"] = get("event:" + r["event"]["id"], {})
                r["staff"]["announcement"] = announcement(r["event"], site_url())
                r["staff"]["signups"] = signups(r["event"]["id"])
                r["staff"]["discord"] = bool(g["settings"]().get("discord_webhook"))
        resp = jsonify(r)
        resp.headers["Cache-Control"] = "private, no-store"
        return resp

    def current_event():
        cfg = config()
        if not cfg["enabled"]:
            raise ValueError("There's no group flight scheduled right now.")
        return event_for(upcoming(cfg), cfg)

    @app.post("/api/group-flight/<action>")
    def group_flight_signup(action):
        import auth
        p = auth.current()
        if not p:
            return jsonify({"error": "Sign in to sign up.", "signin": True}), 401
        try:
            ev = current_event()
            if ev["start"] + 3600 < time.time():
                raise ValueError("This flight has already departed. Sign up for next week's soon.")
            with closing(db()) as c, c:
                if action == "join":
                    ac = str((request.get_json(silent=True) or {}).get("aircraft") or "")[:20]
                    if ac and ac not in {a["code"] for a in ev["aircraft"]}:
                        raise ValueError("Choose one of this week's aircraft.")
                    c.execute("INSERT OR REPLACE INTO group_flight_signups (event, pilot, name, aircraft, joined) VALUES (?,?,?,?,COALESCE("
                              "(SELECT joined FROM group_flight_signups WHERE event=? AND pilot=?),?))",
                              (ev["id"], p["id"], p.get("name") or p["id"], ac, ev["id"], p["id"], time.time()))
                elif action == "leave":
                    c.execute("DELETE FROM group_flight_signups WHERE event=? AND pilot=?", (ev["id"], p["id"]))
                else:
                    raise ValueError("Unknown action.")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return group_flight_public()

    @app.post("/api/staff/group-flight")
    def group_flight_staff():
        b = request.get_json(silent=True) or {}
        ct = g["clean_text"]
        try:
            cfg = config()
            if "config" in b:
                x = b["config"] or {}
                t = str(x.get("time", cfg["time"]))
                hh, mm = t.split(":")
                if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                    raise ValueError
                wd = int(x.get("weekday", cfg["weekday"]))
                if not 0 <= wd <= 6:
                    raise ValueError
                net = x.get("network", cfg["network"])
                cfg = {"enabled": bool(x.get("enabled", cfg["enabled"])), "weekday": wd, "time": f"{int(hh):02d}:{int(mm):02d}",
                       "network": net if net in NETWORKS else cfg["network"], "voice": ct(x.get("voice", cfg["voice"]), 120),
                       "briefing": ct(x.get("briefing", cfg["briefing"]), 1200) or DEFAULTS["briefing"]}
                put("config", cfg)
            if "override" in b:
                ev = event_for(upcoming(cfg), cfg)
                x = b["override"] or {}
                o = {}
                rid = ct(x.get("route_id"), 20).upper()
                if rid:
                    if rid not in g["ROUTES"]:
                        raise ValueError("That route number isn't in the scheduled network.")
                    o["route_id"] = rid
                else:
                    dep, arr = ct(x.get("dep"), 4).upper(), ct(x.get("arr"), 4).upper()
                    if dep or arr:
                        if dep == arr or dep not in g["AIRPORTS"] or arr not in g["AIRPORTS"]:
                            raise ValueError("Enter a route number, or two different known ICAO airports.")
                        ac = [a for a in (x.get("aircraft") or []) if a in g["FLEET"] and not g["FLEET"][a].get("retired")]
                        o.update(dep=dep, arr=arr, aircraft=ac or ["B738F"], cargo=ct(x.get("cargo"), 80) or "General cargo")
                for k, n in (("title", 80), ("briefing", 1200)):
                    if ct(x.get(k), n):
                        o[k] = ct(x.get(k), n)
                if x.get("network") in NETWORKS:
                    o["network"] = x["network"]
                put("event:" + ev["id"], o)
        except (ValueError, TypeError) as e:
            msg = str(e) if isinstance(e, ValueError) and str(e) else "Check the day and time (HH:MM, UTC)."
            return jsonify({"error": msg}), 400
        return group_flight_public()

    @app.post("/api/staff/group-flight/discord")
    def group_flight_discord():
        url = g["settings"]().get("discord_webhook")
        if not url:
            return jsonify({"error": "Add the Discord webhook under Staff › Site and rules first, or copy the announcement instead."}), 400
        try:
            ev = current_event()
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        ok, err = g["discord_post"].post(url, {"content": announcement(ev, site_url())[:1990]}, wait=True)
        return jsonify({"ok": True}) if ok else (jsonify({"error": err}), 502)

    @app.get("/api/group-flight.ics")
    def group_flight_ics():
        try:
            ev = current_event()
        except ValueError as e:
            return str(e), 404
        st = dt.datetime.fromtimestamp(ev["start"], dt.timezone.utc)
        stamp = lambda d: d.strftime("%Y%m%dT%H%M%SZ")
        esc = lambda s: str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
        body = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pagani Air Cargo//Group flight//EN", "BEGIN:VEVENT",
                            f"UID:pac-group-{ev['id']}@pac-va.com", f"DTSTAMP:{stamp(dt.datetime.now(dt.timezone.utc))}",
                            f"DTSTART:{stamp(st)}", f"DTEND:{stamp(st + dt.timedelta(hours=3))}",
                            f"SUMMARY:{esc('PAC group flight: ' + ev['dep']['icao'] + ' to ' + ev['arr']['icao'])}",
                            f"DESCRIPTION:{esc(ev['briefing'] + chr(10) + chr(10) + site_url().rstrip('/') + '/#groupflight')}",
                            f"URL:{site_url().rstrip('/')}/#groupflight", "END:VEVENT", "END:VCALENDAR"]) + "\r\n"
        return app.response_class(body, mimetype="text/calendar",
                                  headers={"Content-Disposition": f"attachment; filename=PAC-group-flight-{ev['id']}.ics"})
