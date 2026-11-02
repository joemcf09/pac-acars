"""Live aviation weather for PAC ACARS.

Reports come from the US Aviation Weather Center (aviationweather.gov), which
publishes worldwide METARs and TAFs without an account. We ask for the raw
report text and decode it ourselves, so nothing depends on the service's JSON
layout. Results are cached for 10 minutes.
"""
from __future__ import annotations

import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://aviationweather.gov/api/data"
TTL = 600
_cache = {}
_lock = threading.Lock()

WX_WORDS = {"MI": "shallow", "PR": "partial", "BC": "patches of", "DR": "drifting", "BL": "blowing", "SH": "showers of", "TS": "thunderstorm",
            "FZ": "freezing", "DZ": "drizzle", "RA": "rain", "SN": "snow", "SG": "snow grains", "IC": "ice crystals", "PL": "ice pellets",
            "GR": "hail", "GS": "small hail", "UP": "precipitation", "BR": "mist", "FG": "fog", "FU": "smoke", "VA": "volcanic ash",
            "DU": "dust", "SA": "sand", "HZ": "haze", "PY": "spray", "PO": "dust whirls", "SQ": "squalls", "FC": "funnel cloud",
            "SS": "sandstorm", "DS": "duststorm"}
WX_RE = re.compile(r"^(\+|-|VC)?(MI|PR|BC|DR|BL|SH|TS|FZ)?((?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)+)?$")
COVER = {"FEW": "few", "SCT": "scattered", "BKN": "broken", "OVC": "overcast", "VV": "vertical visibility"}


class WeatherError(Exception):
    pass


FAIL_TTL = 120          # after a failure, don't ask again for two minutes: pages answer at once instead of waiting
TIMEOUT = 6
_down = {"until": 0.0, "why": ""}


def _get(url):
    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
        if time.time() < _down["until"]:          # the service failed a moment ago: don't make every page wait for it again
            raise WeatherError(_down["why"])
    req = urllib.request.Request(url, headers={"User-Agent": "PAC-ACARS/1.0 (flight simulation virtual airline)"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        why = f"Weather service returned HTTP {e.code}."
        if e.code >= 500 or e.code == 429:
            with _lock:
                _down.update(until=time.time() + FAIL_TTL, why=why)
        raise WeatherError(why)
    except (urllib.error.URLError, TimeoutError, OSError):
        why = "Weather is unavailable right now (no connection to aviationweather.gov)."
        with _lock:
            _down.update(until=time.time() + FAIL_TTL, why=why)
        raise WeatherError(why)
    with _lock:
        _cache[url] = (time.time(), text)
        if len(_cache) > 2000:                   # keep memory in check: drop the oldest reports
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:500]:
                _cache.pop(k, None)
    return text


def _ids(ids):
    return [i.strip().upper() for i in ids if i and re.fullmatch(r"[A-Za-z0-9]{3,4}", i.strip())]


def metars(ids):
    """{icao: decoded METAR} for the stations that have one."""
    ids = _ids(ids)
    out = {}
    chunks = [ids[i:i + 80] for i in range(0, len(ids), 80)]
    urls = [f"{BASE}/metar?" + urllib.parse.urlencode({"ids": ",".join(c), "format": "raw"}) for c in chunks]
    if len(urls) > 1:                             # the whole network: ask for the chunks at the same time, not one after another
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(6, len(urls))) as ex:
            texts = list(ex.map(_get, urls))
    else:
        texts = [_get(u) for u in urls]
    for chunk, text in zip(chunks, texts):
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            d = decode_metar(line)
            if d and d["station"] in chunk and d["station"] not in out:
                out[d["station"]] = d
    return out


def taf(icao):
    icao = (_ids([icao]) or [None])[0]
    if not icao:
        return None
    text = _get(f"{BASE}/taf?" + urllib.parse.urlencode({"ids": icao, "format": "raw"})).strip()
    if not text or icao not in text:
        return None
    raw = " ".join(text.split())
    lines = re.sub(r"\s(?=(FM\d{6}|BECMG|TEMPO|PROB\d{2}(?!\s*TEMPO)|PROB\d{2}\sTEMPO))", "\n", raw).split("\n")
    return {"station": icao, "raw": raw, "lines": [l.strip() for l in lines if l.strip()]}


def _vis_sm(tok, prev=None):
    """Visibility token to statute miles. Returns (sm, consumed_prev) where prev may hold the whole part of '1 1/2SM'."""
    m = re.fullmatch(r"([PM])?(\d{1,2})SM", tok)
    if m:
        return float(m.group(2)), False
    m = re.fullmatch(r"([PM])?(\d)/(\d{1,2})SM", tok)
    if m:
        frac = int(m.group(2)) / int(m.group(3))
        if prev and prev.isdigit() and len(prev) == 1:
            return int(prev) + frac, True
        return frac, False
    return None, False


def decode_metar(raw):
    toks = raw.replace("=", "").split()
    if not toks:
        return None
    if toks[0] in ("METAR", "SPECI"):
        toks = toks[1:]
    if not toks or not re.fullmatch(r"[A-Z0-9]{4}", toks[0]):
        return None
    d = {"station": toks[0], "raw": raw.strip(), "time": None, "wind": None, "vis_sm": None, "vis_text": "", "clouds": [],
         "ceiling_ft": None, "temp_c": None, "dew_c": None, "altim_inhg": None, "altim_hpa": None, "wx": [], "wx_text": "", "cavok": False}
    prev = None
    for tok in toks[1:]:
        if tok in ("RMK", "TEMPO", "BECMG", "NOSIG"):
            break
        if re.fullmatch(r"\d{6}Z", tok):
            d["time"] = tok
        elif (m := re.fullmatch(r"(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?(KT|MPS|KMH)", tok)):
            k = {"KT": 1, "MPS": 1.94384, "KMH": 0.539957}[m.group(4)]
            d["wind"] = {"dir": None if m.group(1) == "VRB" else int(m.group(1)), "vrb": m.group(1) == "VRB",
                         "spd": round(int(m.group(2)) * k), "gust": round(int(m.group(3)) * k) if m.group(3) else None, "var": None}
        elif re.fullmatch(r"\d{3}V\d{3}", tok) and d["wind"]:
            d["wind"]["var"] = tok
        elif tok == "CAVOK":
            d.update(cavok=True, vis_sm=10.0, vis_text="10 km or more, no significant cloud")
        elif re.fullmatch(r"\d{4}(NDV)?", tok) and d["vis_sm"] is None and d["wind"] is not None:
            meters = int(tok[:4])
            d["vis_sm"] = 10.0 if meters >= 9999 else round(meters / 1609.34, 2)
            d["vis_text"] = "10 km or more" if meters >= 9999 else f"{meters:,} m"
        elif tok.endswith("SM"):
            sm, used_prev = _vis_sm(tok, prev)
            if sm is not None:
                d["vis_sm"] = min(sm, 10.0) if not tok.startswith("P") else max(sm, 6.0)
                d["vis_text"] = (f"{'more than ' if tok.startswith('P') else 'less than ' if tok.startswith('M') else ''}"
                                 f"{(prev + ' ') if used_prev else ''}{tok[:-2].lstrip('PM')} SM")
        elif (m := re.fullmatch(r"(FEW|SCT|BKN|OVC|VV)(\d{3}|///)(CB|TCU|///)?", tok)):
            base = int(m.group(2)) * 100 if m.group(2).isdigit() else None
            d["clouds"].append({"cover": m.group(1), "base_ft": base, "type": m.group(3) if m.group(3) and m.group(3) != "///" else ""})
        elif tok in ("SKC", "CLR", "NSC", "NCD"):
            d["clouds"] = []
        elif (m := re.fullmatch(r"(M?\d{2})/(M?\d{2})?", tok)):
            conv = lambda s: -int(s[1:]) if s.startswith("M") else int(s)
            d["temp_c"] = conv(m.group(1))
            d["dew_c"] = conv(m.group(2)) if m.group(2) else None
        elif (m := re.fullmatch(r"A(\d{4})", tok)):
            d["altim_inhg"] = int(m.group(1)) / 100
            d["altim_hpa"] = round(d["altim_inhg"] * 33.8639)
        elif (m := re.fullmatch(r"Q(\d{4})", tok)):
            d["altim_hpa"] = int(m.group(1))
            d["altim_inhg"] = round(d["altim_hpa"] / 33.8639, 2)
        elif tok not in ("AUTO", "COR", "NIL") and WX_RE.fullmatch(tok) and any(c.isalpha() for c in tok) and len(tok) >= 2:
            d["wx"].append(tok)
        prev = tok
    ceilings = [c["base_ft"] for c in d["clouds"] if c["cover"] in ("BKN", "OVC", "VV") and c["base_ft"] is not None]
    d["ceiling_ft"] = min(ceilings) if ceilings else None
    d["category"] = flight_category(d["vis_sm"], d["ceiling_ft"])
    d["wx_text"] = ", ".join(describe_wx(w) for w in d["wx"])
    d["summary"] = summary(d)
    return d


def describe_wx(tok):
    m = WX_RE.fullmatch(tok)
    if not m:
        return tok
    inten = {"+": "heavy", "-": "light", "VC": "nearby"}.get(m.group(1) or "", "")
    desc = WX_WORDS.get(m.group(2) or "", "")
    phen = m.group(3) or ""
    words = [WX_WORDS.get(phen[i:i + 2], phen[i:i + 2]) for i in range(0, len(phen), 2)]
    if m.group(2) == "TS":
        return " ".join(x for x in [inten, "thunderstorm", ("with " + " and ".join(words)) if words else ""] if x)
    return " ".join(x for x in [inten, desc, " and ".join(words)] if x)


def flight_category(vis_sm, ceiling_ft):
    v = 10 if vis_sm is None else vis_sm
    c = 99999 if ceiling_ft is None else ceiling_ft
    if c < 500 or v < 1:
        return "LIFR"
    if c < 1000 or v < 3:
        return "IFR"
    if c <= 3000 or v <= 5:
        return "MVFR"
    return "VFR"


def wind_text(w):
    if not w:
        return "—"
    if w["spd"] == 0:
        return "Calm"
    d = "Variable" if w["vrb"] else f"{w['dir']:03d}°"
    return f"{d} at {w['spd']} kt" + (f", gusting {w['gust']}" if w.get("gust") else "")


def summary(d):
    parts = [wind_text(d["wind"]), d["vis_text"] or "", d["wx_text"] or ""]
    if d["cavok"]:
        parts.append("")
    elif d["ceiling_ft"] is not None:
        parts.append(f"ceiling {d['ceiling_ft']:,} ft")
    elif d["clouds"]:
        parts.append(f"{COVER[d['clouds'][0]['cover']]} at {d['clouds'][0]['base_ft'] or 0:,} ft")
    else:
        parts.append("sky clear")
    if d["temp_c"] is not None:
        parts.append(f"{d['temp_c']}°C")
    if d["altim_hpa"]:
        parts.append(f"QNH {d['altim_hpa']} / {d['altim_inhg']:.2f}")
    return " · ".join(p for p in parts if p)


def components(wind, runway_heading):
    """Head/crosswind for a runway (true headings; METAR winds are true)."""
    if not wind or wind.get("vrb") or wind.get("dir") is None or runway_heading is None:
        return None
    ang = math.radians(wind["dir"] - runway_heading)
    head = wind["spd"] * math.cos(ang)
    cross = wind["spd"] * math.sin(ang)
    out = {"head_kt": round(head), "cross_kt": round(abs(cross)), "cross_from": "right" if cross > 0 else "left"}
    if wind.get("gust"):
        out["gust_cross_kt"] = round(abs(wind["gust"] * math.sin(ang)))
    return out
