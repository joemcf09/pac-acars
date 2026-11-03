"""Landing analysis for PAC ACARS.

Works from the high-rate samples the recorder keeps around touchdown:
[t, agl_ft, vs_fpm, ias, g, lat, lon, hdg, on_ground, gs]
"""
from __future__ import annotations

import json
import math
from pathlib import Path

FT_PER_M = 3.28084
_RUNWAYS = None


def runways(data_dir: Path):
    global _RUNWAYS
    if _RUNWAYS is None:
        try:
            _RUNWAYS = json.loads((data_dir / "runways.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            _RUNWAYS = {}
    return _RUNWAYS


def _enu(lat0, lon0, lat, lon):
    """Meters east/north of (lat0, lon0). Accurate enough over a few kilometers."""
    k = 111_320.0
    return (lon - lon0) * k * math.cos(math.radians(lat0)), (lat - lat0) * k


def _angdiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def match_runway(rw_list, lat, lon, hdg):
    best = None
    for r in rw_list or []:
        ends = [(r[0], r[1], r[2], r[3], r[4]), (r[5], r[6], r[7], r[8], r[9])]
        length_m, width_m = (r[10] or 0) / FT_PER_M, (r[11] or 150) / FT_PER_M
        for ident, tlat, tlon, thdg, disp_ft in ends:
            if _angdiff(hdg, thdg) > 35:
                continue
            e, n = _enu(tlat, tlon, lat, lon)
            h = math.radians(thdg)
            along = e * math.sin(h) + n * math.cos(h)
            cross = e * math.cos(h) - n * math.sin(h)  # + = right of centerline
            if along < -300 or (length_m and along > length_m + 300) or abs(cross) > max(120, width_m * 2):
                continue
            cand = {"runway": ident, "along_m": along - (disp_ft or 0) / FT_PER_M, "cross_m": cross,
                    "length_ft": r[10], "width_ft": r[11], "heading": thdg, "threshold": [tlat, tlon], "displaced_ft": disp_ft}
            if best is None or abs(cross) < abs(best["cross_m"]):
                best = cand
    return best


def verdict(rate):
    if rate is None:
        return "–"
    if rate >= -100:
        return "Butter"
    if rate >= -250:
        return "Smooth"
    if rate >= -400:
        return "Firm"
    if rate >= -600:
        return "Heavy"
    return "Hard"


SUSTAIN_S = 3   # seconds a descent rate must last to count against a stable approach


def sustained_min(points, secs):
    """The most negative value that lasted at least `secs`. Each window of that length counts at its least-negative
    value, and the result is the worst window. A lone sample with no neighbor inside its window counts on its own
    (sparse data), so a real steep descent is never missed."""
    pts = sorted(points)
    if not pts:
        return 0
    worst = None
    for i, (t0, _v) in enumerate(pts):
        if worst is not None and pts[-1][0] - t0 < secs:
            break                                   # the remaining tail is shorter than a window: already covered
        level = max(v for t, v in pts[i:] if t - t0 <= secs)
        worst = level if worst is None else min(worst, level)
    return worst


def analyze_landing(series, td_t, rate, g, airports_to_try, data_dir, gc_distance_nm):
    if not series:
        return None
    series = sorted(series, key=lambda x: x[0])
    td = min(series, key=lambda x: abs(x[0] - td_t))
    lat, lon, hdg = td[5], td[6], td[7]
    out = {"rate_fpm": rate, "g": g, "verdict": verdict(rate), "ias": round(td[3]), "heading": round(hdg)}

    # runway and touchdown point
    rws = runways(data_dir)
    for icao in airports_to_try:
        m = match_runway(rws.get(icao), lat, lon, hdg)
        if m:
            out.update(airport=icao, runway=m["runway"], runway_length_ft=m["length_ft"], runway_width_ft=m["width_ft"],
                       touchdown_ft=round(m["along_m"] * FT_PER_M), centerline_ft=round(m["cross_m"] * FT_PER_M),
                       runway_heading=m["heading"], threshold=m["threshold"])
            break

    before = [x for x in series if x[0] <= td[0]]
    after = [x for x in series if x[0] >= td[0]]

    # float: from 50 ft to touchdown
    above50 = [x for x in before if x[1] >= 50]
    if above50:
        out["float_s"] = round(td[0] - above50[-1][0], 1)

    # approach stability below 1,000 ft
    # after a go-around, only the approach that ended in the landing counts: start after the last sustained climb
    # (500 fpm or more for 4 s, the same test the tracker uses to call a go-around)
    start_i, run_t = 0, None
    for i, x in enumerate(before):
        if x[8] == 0 and x[2] > 500:
            run_t = x[0] if run_t is None else run_t
            if x[0] - run_t >= 4:
                start_i = i + 1
        else:
            run_t = None
    final = before[start_i:]
    app = [x for x in final if 50 <= x[1] <= 1000 and x[8] == 0]  # 1,000 ft gate down to the flare
    if len(app) >= 3:
        ias = [x[3] for x in app]
        low = [x for x in app if x[1] <= 500]
        out["approach"] = {
            "ias_min": round(min(ias)), "ias_max": round(max(ias)),
            "max_descent_fpm": round(min(x[2] for x in app)),
            "ias_500": round(low[0][3]) if low else None, "vs_500": round(low[0][2]) if low else None,
        }
        spread = max(ias) - min(ias)
        # a stable approach is about the SUSTAINED descent rate: a one-second spike in the sim's vertical speed
        # (turbulence, X-Plane's ground height jumping over uneven terrain) no longer fails an otherwise steady approach
        # the seconds just before the 500 ft gate count too: a steep descent still going as you pass 500 ft is unstable
        gate_t = low[0][0] if low else None
        judged = [x for x in app if gate_t is not None and x[0] >= gate_t - SUSTAIN_S]
        worst_low = sustained_min([(x[0], x[2]) for x in judged], SUSTAIN_S)
        out["approach"]["sustained_descent_500_fpm"] = round(worst_low)
        out["stable"] = spread <= 20 and worst_low >= -1100
        out["stability_note"] = ("Stable approach" if out["stable"] else
                                 "Speed varied by %d kt between 1,000 ft and the flare" % spread if spread > 20 else
                                 "Descent over 1,100 fpm for %d seconds or more below 500 ft" % SUSTAIN_S)

    # rollout: distance from touchdown to 40 kt
    dist_m, prev = 0.0, after[0] if after else None
    for x in after[1:]:
        e, n = _enu(prev[5], prev[6], x[5], x[6])
        dist_m += math.hypot(e, n)
        prev = x
        if x[9] <= 40:
            out["rollout_ft"] = round(dist_m * FT_PER_M)
            break
    post_g = [x[4] for x in after if x[0] - td[0] <= 3]
    if post_g:
        out["g"] = round(max(post_g + [g or 0]), 2)

    # chart series: seconds relative to touchdown
    pts = [x for x in series if -150 <= x[0] - td[0] <= 45]
    step = max(1, len(pts) // 400)
    out["series"] = [[round(x[0] - td[0], 1), round(x[1]), x[2], round(x[3]), round(x[9])] for x in pts[::step]]
    return out


def analyze_takeoff(series, off_t, airports_to_try, data_dir, tail_limit=None):
    """Rotation, liftoff, tail-strike margin, runway used and initial climb from the takeoff samples.
    Sample: [t, agl, vs, ias, g, lat, lon, hdg, on_ground, gs, pitch]"""
    if not series or len(series) < 5:
        return None
    series = sorted(series, key=lambda x: x[0])
    # pitch sign sanity: nose-up must be positive once climbing
    climbing = [x[10] for x in series if x[10] is not None and x[8] == 0 and x[2] > 800]
    if climbing and sorted(climbing)[len(climbing) // 2] < 0:
        series = [x[:10] + [-x[10] if x[10] is not None else None] for x in series]
    has_pitch = any(x[10] is not None for x in series)
    lo_i = None
    for i, x in enumerate(series):
        if x[8] == 0 and all(y[8] == 0 for y in series[i:i + 8] if y[0] - x[0] <= 2):
            lo_i = i
            break
    if lo_i is None:
        return None
    lo = series[lo_i]
    roll = [x for x in series[:lo_i] if x[8] == 1]
    out = {"liftoff_ias": round(lo[3]), "liftoff_gs": round(lo[9]), "heading": round(lo[7])}
    if has_pitch and roll:
        p0 = sorted(x[10] for x in roll[: max(1, len(roll) // 2)] if x[10] is not None)
        p0 = p0[len(p0) // 2] if p0 else 0.0
        # rotation is confirmed once pitch is 2° above the roll attitude, but it started earlier:
        # walk back to the last sample still within 0.5° of the roll attitude
        ri = next((i for i, x in enumerate(roll) if x[10] is not None and x[10] > p0 + 2.0), None)
        if ri is not None:
            j = ri
            while j > 0 and roll[j - 1][10] is not None and roll[j - 1][10] > p0 + 0.5:
                j -= 1
            rot = roll[j]
            out["rotate_ias"] = round(rot[3])
            # rate while the nose is coming up: from rotation start to 90% of the pitch reached at liftoff
            target = p0 + 0.9 * ((lo[10] or 0) - p0)
            k = next((x for x in series if x[0] > rot[0] and x[10] is not None and x[10] >= target), lo)
            out["rotation_rate"] = round(((k[10] or 0) - p0) / max(0.5, k[0] - rot[0]), 1)
        out["liftoff_pitch"] = round(lo[10] or 0, 1)
        ground = [x[10] for x in series if x[10] is not None and (x[8] == 1 or x[1] < 5)]
        out["max_pitch_ground"] = round(max(ground), 1) if ground else None
        if tail_limit:
            out["tail_limit"] = tail_limit
            out["tail_margin"] = round(tail_limit - (out["max_pitch_ground"] or 0), 1)
            out["tail_strike"] = out["max_pitch_ground"] is not None and out["max_pitch_ground"] >= tail_limit
    # roll distance along the path
    dist_m = 0.0
    for a, b in zip(roll, roll[1:] + [lo]):
        e, n = _enu(a[5], a[6], b[5], b[6])
        dist_m += math.hypot(e, n)
    out["roll_ft"] = round(dist_m * FT_PER_M) if roll else None
    # runway: match from the start of the roll
    start = roll[0] if roll else lo
    rws = runways(data_dir)
    for icao in airports_to_try:
        m = match_runway(rws.get(icao), start[5], start[6], lo[7])
        if m:
            mlo = match_runway([r for r in rws.get(icao, []) if m["runway"] in (r[0], r[5])], lo[5], lo[6], lo[7])
            out.update(airport=icao, runway=m["runway"], runway_length_ft=m["length_ft"], runway_width_ft=m["width_ft"],
                       start_ft=round(max(0, m["along_m"]) * FT_PER_M),
                       liftoff_ft=round(mlo["along_m"] * FT_PER_M) if mlo else None)
            if mlo and m["length_ft"]:
                out["remaining_ft"] = max(0, round(m["length_ft"] - mlo["along_m"] * FT_PER_M))
            if out.get("liftoff_ft") is not None and out["liftoff_ft"] > out["start_ft"]:
                out["roll_ft"] = out["liftoff_ft"] - out["start_ft"]  # along the runway, not the turn onto it
            break
    # touch-back: airborne at some point in the roll, then back on the runway before the sustained liftoff,
    # or back on the ground within 30 s after it
    first_air = next((i for i, x in enumerate(series) if x[8] == 0 and x[1] > 3), None)
    after = series[lo_i:]
    out["touchback"] = (first_air is not None and first_air < lo_i and any(x[8] == 1 for x in series[first_air:lo_i])) \
        or any(x[8] == 1 for x in after if x[0] - lo[0] <= 30)
    climb = [x for x in after if 50 <= x[1] <= 1000]
    if climb:
        out["climb_fpm"] = round(sum(x[2] for x in climb) / len(climb))
    k = next((x for x in after if x[1] >= 1000), None)
    if k:
        out["time_to_1000_s"] = round(k[0] - lo[0])
    out["max_g"] = round(max(x[4] for x in series if abs(x[0] - lo[0]) <= 10), 2)
    pts = [x for x in series if -40 <= x[0] - lo[0] <= 60]
    step = max(1, len(pts) // 300)
    out["series"] = [[round(x[0] - lo[0], 1), round(x[1]), x[2], round(x[3]), x[10] if x[10] is not None else None] for x in pts[::step]]
    return out


# ---------------------------------------------------------------- approach profile (for the chart)
GLIDE_DEG = 3.0
DOT_DEG = 0.35       # one dot of glideslope deviation on an ILS
TCH_FT = 50          # threshold crossing height


def approach_profile(profile, la, gc_nm, max_nm=12.0):
    """The final approach from a PIREP's flight profile, measured along the runway's extended centerline.
    profile rows: [t, lat, lon, alt, agl, ias, gs, vs, hdg]. Needs the landing analysis' threshold and runway heading.
    Returns points (distance to threshold in nm, height above ground, speeds), the ideal 3-degree path,
    and how the flight crossed the 1,000, 500 and 200 ft gates."""
    if not profile or not la or not la.get("threshold") or la.get("runway_heading") is None:
        return None
    thr_lat, thr_lon = la["threshold"]
    rwy = la["runway_heading"]
    rows = [r for r in profile if len(r) >= 9]
    # the final touchdown: after the last time above 1,000 ft, the first sample at the ground
    last_high = max((i for i, r in enumerate(rows) if r[4] > 1000), default=None)
    if last_high is None:
        return None
    td = next((i for i in range(last_high, len(rows)) if rows[i][4] <= 5), None)
    if td is None:
        return None

    def along(lat, lon):
        d = gc_nm(thr_lat, thr_lon, lat, lon)
        y = math.sin(math.radians(lon - thr_lon)) * math.cos(math.radians(lat))
        x = (math.cos(math.radians(thr_lat)) * math.sin(math.radians(lat))
             - math.sin(math.radians(thr_lat)) * math.cos(math.radians(lat)) * math.cos(math.radians(lon - thr_lon)))
        brg = (math.degrees(math.atan2(y, x)) + 360) % 360
        return d * math.cos(math.radians(brg - (rwy + 180)))  # positive: before the threshold, on the approach side

    pts = []
    for r in rows[:td + 1]:
        a = along(r[1], r[2])
        if -0.5 <= a <= max_nm and r[4] <= 4500:
            pts.append({"nm": round(a, 3), "agl": r[4], "ias": r[5], "gs": r[6], "vs": r[7]})
    # only the continuous final segment (ignore earlier passes, e.g. before a go-around)
    seg = []
    for p in reversed(pts):
        if seg and p["nm"] < seg[-1]["nm"] - 0.05:
            break
        seg.append(p)
    pts = list(reversed(seg))
    if len(pts) < 4:
        return None
    ideal = lambda nm: max(0.0, nm * 6076.12 * math.tan(math.radians(GLIDE_DEG)) + TCH_FT)

    gates = []
    for gate in (1000, 500, 200):
        for a, b in zip(pts, pts[1:]):
            if a["agl"] >= gate > b["agl"] and a["agl"] != b["agl"]:
                f = (a["agl"] - gate) / (a["agl"] - b["agl"])
                nm = a["nm"] + (b["nm"] - a["nm"]) * f
                ias = a["ias"] + (b["ias"] - a["ias"]) * f
                vs = a["vs"] + (b["vs"] - a["vs"]) * f
                # the glideslope angle is measured from where the path meets the runway (the glidepath origin,
                # about 950 ft past the threshold for a 50 ft threshold crossing height), as an ILS measures it
                gpi_ft = TCH_FT / math.tan(math.radians(GLIDE_DEG))
                angle = math.degrees(math.atan2(gate, max(0.01, nm) * 6076.12 + gpi_ft))
                gates.append({"ft": gate, "nm": round(nm, 2), "dev_ft": round(gate - ideal(nm)), "dots": round((angle - GLIDE_DEG) / DOT_DEG, 1),
                              "ias": round(ias), "vs": round(vs)})
                break
    return {"runway": la.get("runway"), "airport": la.get("airport"), "glide_deg": GLIDE_DEG, "dot_deg": DOT_DEG, "tch_ft": TCH_FT,
            "points": pts, "gates": gates, "max_nm": max(p["nm"] for p in pts)}
