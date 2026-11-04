"""ACARS logic shared by the PAC website and the PAC ACARS app.

Everything that happens during a tracked flight lives here: weather uplinks,
the loadsheet and stand, online-network checks, and messages to and from PAC
Operations (OCC). It works on a FlightRecorder and has no dependency on the
website, so the same code runs in the website (built-in tracking) and in the
standalone ACARS app.
"""
from __future__ import annotations

import random
import re
import threading
import time

import weather
from sim_sources import gc_distance_nm
from tracker import zulu

EXCUSED_DELAYS = {"ATC": "ATC", "WEATHER": "weather", "GROUND HANDLING": "ground handling", "LATE CARGO": "late cargo",
                  "TECHNICAL": "a technical fault"}
DIVERT_REASONS = ("WEATHER", "MEDICAL", "TECHNICAL", "FUEL", "SECURITY", "RUNWAY CLOSED")


def clean(s, n=200):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def stand(flight, icao=None, aircraft=None):
    """The arrival stand: PAC's own stand at stations with a guide (KCVG P1-P8, and stands at the other PAC hubs, sized for the
    aircraft), otherwise the airport's cargo ramp. PAC doesn't make up a stand number there: a made-up one is usually a
    passenger gate at the real airport. The same flight always gets the same stand."""
    rng = random.Random(f"{flight}|{icao}")
    try:
        import stations
        own = stations.stand_for(icao, aircraft, rng) if icao else None
    except ImportError:
        own = None
    if own:  # Cincinnati is PAC's own facility; elsewhere PAC uses stands on the airport's cargo apron
        return f"PAC CARGO CENTER STAND {own}" if icao == "KCVG" else f"PAC CARGO STAND {own}"
    return "CARGO RAMP, ANY FREE CARGO STAND"


def wx_line(m):
    raw = m["raw"].split(" RMK")[0]
    for pre in ("METAR ", "SPECI "):
        if raw.startswith(pre):
            raw = raw[len(pre):]
    return f"WX {raw}  [{m['category']}]"


def wx_send(rec, icao, m, force=False):
    """Posts a weather uplink unless the same report was already sent in the last 20 minutes."""
    sent = getattr(rec, "wx_sent", None)
    if sent is None:
        sent = rec.wx_sent = {}
    now = time.time()
    if not force and sent.get(icao, (None, 0))[0] == m["raw"] and now - sent[icao][1] < 1200:
        return
    sent[icao] = (m["raw"], now)
    rec.msg(rec.last.t if rec.last else now, wx_line(m), "wx")


def _now(rec):
    return rec.last.t if rec.last else time.time()


def weather_job(rec, jobs, lock, nearest_airport=None):
    """Background jobs raised by the recorder: loadsheet at OUT, stand and weather at top of descent, wind at touchdown."""
    try:
        bk = rec.booking or {}
        ids = [rec.dest["icao"]] + ([rec.alternate["icao"]] if rec.alternate else [])
        if "out" in jobs:
            ofp, m_ = bk.get("ofp") or {}, bk.get("mission") or {}
            f = lambda v: f"{v:,.0f}" if v else "----"
            with lock:
                rec.msg(_now(rec), f"PAC OCC  LOADSHEET FINAL {bk.get('flight_number', '')}  PAYLOAD {f(ofp.get('payload_lbs') or m_.get('payload_lbs'))}  "
                                   f"ZFW {f(ofp.get('zfw_lbs'))}  TOW {f(ofp.get('tow_lbs'))}  FOB {f(rec.last.fuel_lbs if rec.last else None)}", "ul")
        if "tod" in jobs:
            with lock:
                arr = bk.get("arr_stand") or {}
                where = ((f"PAC CARGO CENTER STAND {arr['stand']}" if arr.get("icao") == "KCVG" else f"PAC CARGO STAND {arr['stand']}")
                         if arr.get("stand") and arr.get("icao") == rec.dest["icao"]
                         else stand(bk.get('flight_number', rec.dest['icao']), rec.dest['icao'], bk.get('aircraft')))
                rec.msg(_now(rec), f"PAC OCC  ARRIVAL {rec.dest['icao']} {where}. HANDLING READY.", "ul")
            got = weather.metars(ids)
            with lock:
                for icao in ids:
                    if icao in got:
                        wx_send(rec, icao, got[icao])
        if "landing" in jobs and rec.landing:
            near = (nearest_airport(rec.landing["lat"], rec.landing["lon"]) if nearest_airport else None) or rec.dest["icao"]
            got = weather.metars([near])
            if near in got:
                with lock:
                    rec.landing_wx = got[near]
    except (weather.WeatherError, OSError):
        pass
    except Exception as e:  # never let a weather problem affect tracking
        print("Weather job failed:", e)


def online_job(rec, lock, settings):
    """Every few minutes in the air: is the pilot connected to VATSIM or IVAO?"""
    import online
    if not (settings.get("vatsim_cid") or settings.get("ivao_vid")):
        return
    hit = online.check(settings)
    with lock:
        on = getattr(rec, "online", None) or {"checks": 0, "hits": 0}
        on["checks"] += 1
        if hit:
            if not on.get("hits"):
                rec.msg(_now(rec), f"ONLINE ON {hit['network']} AS {hit['callsign'] or '?'}", "phase")
            on["hits"] += 1
            on.update(network=hit["network"], callsign=hit["callsign"])
        rec.online = on


def request_weather(rec, lock, ids):
    """WX button: current METARs for destination and alternate into the ACARS log."""
    got = weather.metars(ids)
    if rec and rec.start_t:
        with lock:
            for icao in dict.fromkeys(ids[:2]):
                if icao in got:
                    wx_send(rec, icao, got[icao], force=True)
    return got


def occ_reply(rec, lock, text, delay=None):
    """PAC Operations answers after a short, realistic pause."""
    def send():
        for _ in range(10):  # the lock may be busy for a moment: try again rather than lose the reply
            try:
                with lock:
                    rec.msg(time.time() if not rec.last else rec.last.t + 0.01, f"PAC OCC  {text}", "ul")
                return
            except Exception:
                time.sleep(1)
    t = threading.Timer(delay if delay is not None else random.uniform(5, 12), send)
    t.daemon = True
    t.start()


def eta(rec):
    last = rec.last
    if not last:
        return None, None
    dtg = gc_distance_nm(last.lat, last.lon, rec.dest["lat"], rec.dest["lon"])
    if last.on_ground or last.gs < 80:
        return None, dtg
    return time.time() + dtg / max(last.gs, 150) * 3600 + 8 * 60, dtg


def handle_message(rec, lock, body, airports):
    """A downlink from the flight deck. Records it (and its effect on scoring) and queues OCC's reply.
    Returns an error message, or None when sent."""
    booking = rec.booking or {}
    kind = body.get("type")
    now = _now(rec)
    reg = booking.get("airframe")
    op = (booking.get("mission") or {}).get("operator")
    if kind == "delay":
        mins = max(1, min(600, int(number(body.get("minutes")))))
        reason = str(body.get("reason") or "").upper()
        if reason not in EXCUSED_DELAYS:
            return "Choose a delay reason."
        with lock:
            rec.reported_delays = (getattr(rec, "reported_delays", None) or []) + [{"t": now, "minutes": mins, "reason": reason}]
            rec.msg(now, f"DELAY {mins} MIN {reason}", "dl")
        e, _ = eta(rec)
        occ_reply(rec, lock, f"DELAY {mins} MIN {reason} NOTED. " + (f"REVISED ETA {zulu(e)}. " if e else "") + "CUSTOMER ADVISED. THANKS FOR THE HEADS-UP.")
    elif kind == "divert":
        icao = str(body.get("icao") or "").upper()
        reason = str(body.get("reason") or "").upper()
        if icao not in airports:
            return "Enter the ICAO code of the diversion airport."
        if reason not in DIVERT_REASONS:
            return "Choose a diversion reason."
        with lock:
            rec.declared_diversion = {"icao": icao, "reason": reason, "t": now}
            rec.msg(now, f"DIVERTING {icao} {reason}", "dl")
        occ_reply(rec, lock, f"DIVERSION TO {icao} ACKNOWLEDGED. HANDLING AGENT ADVISED, CARGO WILL BE TRUCKED ON. "
                             f"{'MAINTENANCE CONTROL STANDING BY. ' if reason == 'TECHNICAL' else ''}SEND ETA WHEN ABLE.")
    elif kind == "fuel":
        last = rec.last
        if not last:
            return "No data from the simulator yet."
        ofp = booking.get("ofp") or {}
        with lock:
            rec.msg(now, f"FUEL CHECK FOB {last.fuel_lbs:,.0f}LB", "dl")
        text = f"FOB {last.fuel_lbs:,.0f} LB RECEIVED."
        if ofp.get("trip_fuel_lbs") and rec.fuel.get("off") is not None:
            total = gc_distance_nm(rec.origin["lat"], rec.origin["lon"], rec.dest["lat"], rec.dest["lon"]) or 1
            flown = max(0.0, total - gc_distance_nm(last.lat, last.lon, rec.dest["lat"], rec.dest["lon"]))
            expected = rec.fuel["off"] - ofp["trip_fuel_lbs"] * min(1.0, flown / total)
            diff = last.fuel_lbs - expected
            text = (f"FOB {last.fuel_lbs:,.0f} LB, PLAN AT THIS POINT ABOUT {expected:,.0f}. " +
                    ("ON PLAN." if abs(diff) < 500 else f"{abs(diff):,.0f} LB {'ABOVE' if diff > 0 else 'BELOW'} PLAN." +
                     (" MONITOR AND ADVISE IF DIVERSION LIKELY." if diff < -1500 else "")))
        occ_reply(rec, lock, text)
    elif kind == "eta":
        e, dtg = eta(rec)
        with lock:
            rec.msg(now, "REQ ETA", "dl")
        occ_reply(rec, lock, f"ETA {rec.dest['icao']} {zulu(e)}, {dtg:,.0f} NM TO GO." if e else
                  f"ETA AVAILABLE ONCE AIRBORNE. {rec.dest['icao']} {dtg:,.0f} NM." if dtg is not None else "ETA NOT AVAILABLE.")
    elif kind == "fault":
        desc = clean(body.get("description"), 300)
        ata = int(number(body.get("ata")) or 5)
        sev = "grounding" if body.get("severity") == "grounding" else "deferred"
        cat = body.get("category") if body.get("category") in ("B", "C") else "C"
        if not desc:
            return "Describe the fault."
        with lock:
            rec.faults = (getattr(rec, "faults", None) or []) + [{"ata": ata, "description": desc, "severity": sev, "category": cat, "t": now}]
            rec.msg(now, f"MX WRITE-UP ATA {ata:02d} {desc.upper()}", "dl")
        if op:
            occ_reply(rec, lock, f"MX CONTROL: NOTED. REPORT IT TO {op['name'].upper()} MAINTENANCE ON ARRIVAL. IT WILL BE IN YOUR PIREP.")
        elif sev == "grounding":
            occ_reply(rec, lock, f"MX CONTROL: {reg or 'AIRCRAFT'} WILL BE GROUNDED ON ARRIVAL FOR RECTIFICATION. CONTINUE IF SAFE, ELSE ADVISE DIVERSION.")
        else:
            occ_reply(rec, lock, f"MX CONTROL: WRITE-UP ACCEPTED FOR {reg or 'AIRCRAFT'}. DEFERRED CAT {cat}, {3 if cat == 'B' else 10} DAYS. CONTINUE.")
    elif kind == "text":
        txt = clean(body.get("text"), 160).upper()
        if not txt:
            return "Type a message."
        with lock:
            rec.msg(now, f"MSG {txt}", "dl")
        low = txt.lower()
        e, _ = eta(rec)
        if any(k in low for k in ("stand", "gate", "parking", "ramp")):
            reply = f"{rec.dest['icao']} {stand(booking.get('flight_number', ''), rec.dest['icao'], booking.get('aircraft'))}. HANDLING READY."
        elif "hotel" in low or "crew car" in low or "transport" in low:
            reply = f"CREW TRANSPORT AND HOTEL BOOKED AT {rec.dest['icao']}. DETAILS ON ARRIVAL."
        elif any(k in low for k in ("maint", "mx", "fault", "inop", "fail")):
            reply = "MX CONTROL STANDING BY. SEND A WRITE-UP FROM THE FAULT BUTTON SO IT'S LOGGED AGAINST THE AIRCRAFT."
        elif "eta" in low:
            reply = f"ETA {rec.dest['icao']} {zulu(e)}." if e else "ETA AVAILABLE ONCE AIRBORNE."
        elif any(k in low for k in ("fuel", "tanker")):
            reply = "FUEL QUERIES: SEND A FUEL CHECK AND WE'LL COMPARE WITH YOUR PLAN."
        elif any(k in low for k in ("cargo", "load", "pallet", "dg", "notoc")):
            reply = "LOAD CONTROL: LOAD AS PER MANIFEST. REFER TO THE NOTOC FOR DANGEROUS GOODS POSITIONS."
        elif any(k in low for k in ("thank", "thx", "cheers")):
            reply = "YOU'RE WELCOME. HAVE A GOOD FLIGHT."
        else:
            reply = "MSG RCVD. WILL ADVISE."
        occ_reply(rec, lock, reply)
    else:
        return "Unknown message type."
    return None


# ---------------------------------------------------------------- PAC ACARS 1.1: landing debrief in the app
def landing_debrief(rec, td, runways_dir, nearest_airport=None):
    """A coaching card for one touchdown, right after it happens: the same measurements the website makes
    (sink rate, touchdown point, centerline, float, stable approach), plus plain-English tips."""
    import analysis
    from sim_sources import gc_distance_nm
    series = [x for x in (getattr(rec, "landing_series", None) or []) if abs(x[0] - td["t"]) <= 200]
    airports = [a for a in (rec.dest.get("icao"), (rec.alternate or {}).get("icao"),
                            nearest_airport(td["lat"], td["lon"]) if nearest_airport else None, rec.origin.get("icao")) if a]
    out = None
    if series:
        try:
            out = analysis.analyze_landing(series, td["t"], td["rate_fpm"], td["g"], list(dict.fromkeys(airports)), runways_dir, gc_distance_nm)
        except Exception as e:
            print("Landing debrief failed:", e)
    out = out or {"rate_fpm": td["rate_fpm"], "g": td["g"], "verdict": analysis.verdict(td["rate_fpm"]), "ias": td["ias"]}
    out.pop("series", None)
    out["n"] = td.get("n", 1)
    out["t"] = td["t"]
    out["z"] = zulu(td["t"])
    out["tips"] = landing_tips(out, getattr(rec, "bounces", 0))
    out["ok"] = out["rate_fpm"] >= -400 and out.get("stable") is not False and \
        (out.get("touchdown_ft") is None or 500 <= out["touchdown_ft"] <= 3000)
    return out


def landing_tips(d, bounces=0):
    tips = []
    rate, fl, tdz, cl = d.get("rate_fpm"), d.get("float_s"), d.get("touchdown_ft"), d.get("centerline_ft")
    app = d.get("approach") or {}
    if rate is not None and rate < -600:
        tips.append("Hard landing. Keep the descent near 700 fpm on final, and start the flare at about 30 ft: thrust to idle and raise the nose about 2 to 3 degrees.")
    elif rate is not None and rate < -400:
        tips.append("Firmer than PAC's 400 fpm limit. Begin the flare a little earlier (about 30 ft) and don't let the nose drop as you close the thrust.")
    elif rate is not None and rate >= -100 and fl and fl > 8:
        tips.append("Very soft, but you held it off a long time. A positive touchdown in the zone is better than a butter landing far down the runway.")
    if fl is not None and fl > 8:
        tips.append(f"You floated {fl:g} seconds from 50 ft to touchdown. Cross the threshold at Vref + 5 kt and close the thrust by 20 ft.")
    if tdz is not None and tdz > 3000:
        tips.append(f"Long landing: {tdz:,} ft past the threshold. Aim for the touchdown zone markers, 1,000 to 2,000 ft down the runway.")
    elif tdz is not None and tdz < 500:
        tips.append(f"Short: you touched down {tdz:,} ft past the threshold. Keep the aiming point steady until the flare.")
    if cl is not None and abs(cl) > 15:
        tips.append(f"{abs(cl)} ft {'right' if cl > 0 else 'left'} of the centerline. Small rudder inputs in the flare keep you lined up, especially in a crosswind.")
    if d.get("stable") is False:
        spread = (app.get("ias_max") or 0) - (app.get("ias_min") or 0)
        if spread > 20:
            tips.append(f"Speed varied {spread} kt below 1,000 ft. Be fully configured and on speed by 1,000 ft, and let the autothrottle or small thrust changes hold it.")
        else:
            tips.append("Descent was steeper than 1,100 fpm below 500 ft. Get established on the glidepath earlier so the last 500 ft is steady.")
    if bounces:
        tips.append("You bounced. Hold the attitude after touchdown and deploy the spoilers; don't pull up again.")
    if not tips:
        tips.append("Nicely done: on speed, in the zone and within limits. Keep doing exactly that.")
    return tips[:3]
