"""Online network recognition: is the pilot connected to VATSIM or IVAO right now?

Uses the networks' public data feeds. Parsing is tolerant: it searches the feed
for the pilot's network ID rather than relying on one exact layout.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

FEEDS = {"VATSIM": "https://data.vatsim.net/v3/vatsim-data.json",
         "IVAO": "https://api.ivao.aero/v2/tracker/whazzup"}
ID_KEYS = {"VATSIM": ("cid",), "IVAO": ("userId", "vid", "userid")}
_cache, _lock = {}, threading.Lock()


def _feed(net):
    with _lock:
        hit = _cache.get(net)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
    req = urllib.request.Request(FEEDS[net], headers={"User-Agent": "PAC-ACARS/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    with _lock:
        _cache[net] = (time.time(), data)
    return data


def _find(node, keys, wanted):
    """Depth-first search for a dict whose ID key matches the pilot."""
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            for k in keys:
                if k in n and str(n[k]).strip() == wanted:
                    return n
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
    return None


def find_pilot(net, network_id, feed=None):
    if not network_id:
        return None
    data = feed if feed is not None else _feed(net)
    hit = _find(data.get("pilots") if net == "VATSIM" and isinstance(data, dict) and "pilots" in data else data,
                ID_KEYS[net], str(network_id).strip())
    if not hit:
        return None
    return {"network": net, "callsign": hit.get("callsign") or "", "id": str(network_id)}


def check(settings):
    """Returns the first network the pilot is connected to, or None. Raises nothing."""
    for net, key in (("VATSIM", "vatsim_cid"), ("IVAO", "ivao_vid")):
        nid = str(settings.get(key) or "").strip()
        if not nid:
            continue
        try:
            hit = find_pilot(net, nid)
        except Exception:
            continue
        if hit:
            return hit
    return None



# ---------------------------------------------------------------- live traffic for the ACARS map
def traffic(net, south, west, north, east, limit=800):
    """Pilots on VATSIM or IVAO inside a map area: callsign, position, altitude, speed, heading, type and route.
    The feeds are cached for a minute (shared with the online bonus check)."""
    data = _feed(net)
    if net == "VATSIM":
        raw = data.get("pilots") or []
        def norm(p):
            fp = p.get("flight_plan") or {}
            return {"cs": p.get("callsign"), "lat": p.get("latitude"), "lon": p.get("longitude"), "alt": p.get("altitude"),
                    "gs": p.get("groundspeed"), "hdg": p.get("heading"), "type": fp.get("aircraft_short") or (fp.get("aircraft") or "")[:4],
                    "dep": fp.get("departure"), "arr": fp.get("arrival")}
    else:
        clients = data.get("clients") or {}
        raw = clients.get("pilots") or [] if isinstance(clients, dict) else []
        def norm(p):
            tr, fp = p.get("lastTrack") or {}, p.get("flightPlan") or {}
            ac = fp.get("aircraft") or {}
            return {"cs": p.get("callsign"), "lat": tr.get("latitude"), "lon": tr.get("longitude"), "alt": tr.get("altitude"),
                    "gs": tr.get("groundSpeed"), "hdg": tr.get("heading"),
                    "type": (ac.get("icaoCode") if isinstance(ac, dict) else None) or fp.get("aircraftId"),
                    "dep": fp.get("departureId"), "arr": fp.get("arrivalId")}
    out = []
    for p in raw:
        try:
            t = norm(p)
            lat, lon = float(t["lat"]), float(t["lon"])
        except (TypeError, ValueError, AttributeError):
            continue
        in_lon = west <= lon <= east if west <= east else (lon >= west or lon <= east)  # views across the date line
        if south <= lat <= north and in_lon:
            out.append({**t, "lat": lat, "lon": lon})
            if len(out) >= limit:
                break
    return out
