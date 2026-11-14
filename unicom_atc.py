"""Is a controller online for my flight? (for the Unicom generator's "contact ATC" nudge)

When no ATC is online you self-announce on Unicom. But a controller can connect mid-flight — and then you must call them
instead. This checks the live VATSIM or IVAO network feed for a controller covering the flight's departure or arrival
field, and reports any match so the website can nudge the pilot.

It is deliberately conservative: it only matches field controllers (Delivery, Ground, Tower, Approach/Departure) whose
callsign names the departure or arrival airport. Enroute Centre/FSS coverage is not matched, because sector boundaries
can't be judged from a callsign reliably across regions, and a wrong "contact ATC" nudge is worse than none.

It fails safe: any network or parsing problem returns "no controllers found", never an error, so a flight is never
disrupted by this check."""
from __future__ import annotations

import json
import time
import urllib.request

FEEDS = {"vatsim": "https://data.vatsim.net/v3/vatsim-data.json",
         "ivao": "https://api.ivao.aero/v2/tracker/whazzup"}
FACILITY = {2: "Delivery", 3: "Ground", 4: "Tower", 5: "Approach", 6: "Centre"}   # VATSIM facility ids
SUFFIX = {"DEL": "Delivery", "GND": "Ground", "TWR": "Tower", "APP": "Approach", "DEP": "Departure", "ATIS": "ATIS"}
FIELD_TYPES = {"Delivery", "Ground", "Tower", "Approach", "Departure"}            # not Centre/FSS/ATIS
_CACHE = {}                 # net -> (fetched_at, [controllers])
TTL = 60


def _fetch(net):
    url = FEEDS.get(net)
    if not url:
        return []
    now = time.time()
    hit = _CACHE.get(net)
    if hit and now - hit[0] < TTL:
        return hit[1]
    out = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PAC-Unicom/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if net == "vatsim":
            for ctl in d.get("controllers", []) or []:
                out.append({"callsign": ctl.get("callsign", ""), "freq": _freq(ctl.get("frequency")),
                            "type": FACILITY.get(ctl.get("facility"), "ATC"), "name": ctl.get("name", "")})
        else:
            atcs = ((d.get("clients") or {}).get("atcs")) or d.get("atcs") or []
            for a in atcs:
                cs = a.get("callsign", "")
                out.append({"callsign": cs, "freq": _freq(a.get("frequency")), "type": _type_from_cs(cs),
                            "name": str(a.get("userId") or "")})
    except Exception as e:
        print("unicom_atc fetch:", net, e)
        return hit[1] if hit else []       # keep the last good list briefly on a blip
    _CACHE[net] = (now, out)
    return out


def _freq(v):
    if v is None:
        return None
    s = str(v)
    try:
        f = float(s)
        return f"{f:.3f}" if f > 50 else None
    except ValueError:
        return s


def _type_from_cs(cs):
    suf = cs.rsplit("_", 1)[-1].upper() if "_" in cs else ""
    if suf in SUFFIX:
        return SUFFIX[suf]
    if suf in ("CTR", "FSS"):
        return "Centre"
    return "ATC"


def _prefixes(icao):
    """Callsign prefixes that would name this airport: the ICAO, the ICAO without a leading K/P/C, and the last 3."""
    icao = (icao or "").upper()
    p = {icao}
    if len(icao) == 4 and icao[0] in "KPC":
        p.add(icao[1:])
    if len(icao) >= 3:
        p.add(icao[-3:])
    return {x for x in p if x}


def covering(net, dep, arr):
    """Field controllers (Del/Gnd/Twr/App/Dep) online for the departure or arrival airport, newest-relevant first."""
    want = {"departure": _prefixes(dep), "arrival": _prefixes(arr)}
    out = []
    for c in _fetch(net):
        if c["type"] not in FIELD_TYPES:
            continue
        pref = c["callsign"].split("_", 1)[0].upper()
        for where, prefs in want.items():
            if pref in prefs:
                out.append({**c, "where": where})
                break
    order = {"Approach": 0, "Departure": 1, "Tower": 2, "Ground": 3, "Delivery": 4}
    out.sort(key=lambda c: order.get(c["type"], 9))
    return out


def selftest(net):
    """For staff: can the server reach the feed, and how many controllers did it parse? Changes nothing."""
    _CACHE.pop(net, None)
    try:
        ctl = _fetch(net)
        return {"net": net, "reachable": net in _CACHE, "controllers_parsed": len(ctl),
                "sample": [c["callsign"] for c in ctl[:8]]}
    except Exception as e:
        return {"net": net, "reachable": False, "error": str(e)}
