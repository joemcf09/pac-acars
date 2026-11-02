"""Scripted flights for automated tests.

Builds a realistic telemetry stream on real runway geometry: stand, pushback,
taxi, takeoff roll and rotation, climb, cruise, descent, a 3-degree approach on
the extended centreline, flare, rollout and taxi-in. Options inject the
situations real flights run into (bounce, hard landing, touch-back after
liftoff, sim-rate acceleration, long pause, overspeed below FL100).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from sim_sources import Telemetry

DATA = Path(__file__).resolve().parent.parent / "data"
NM = 1852.0
FT = 0.3048


def runway_end(icao, ident):
    for r in json.loads((DATA / "runways.json").read_text(encoding="utf-8"))[icao]:
        if r[0] == ident:
            return {"lat": r[1], "lon": r[2], "hdg": r[3], "elev": 0}
        if r[5] == ident:
            return {"lat": r[6], "lon": r[7], "hdg": r[8], "elev": 0}
    raise KeyError(f"{icao} {ident}")


def offset(lat, lon, hdg, dist_m):
    """Point dist_m along heading hdg (true) from lat/lon (flat earth, fine over tens of km)."""
    h = math.radians(hdg)
    dlat = dist_m * math.cos(h) / 111320
    dlon = dist_m * math.sin(h) / (111320 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def bearing(a, b):
    p1, p2, dl = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    return (math.degrees(math.atan2(math.sin(dl) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) + 360) % 360


def gc_nm(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    return 2 * 3440.065 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def fly(dep_icao, dep_rwy, arr_icao, arr_rwy, elev_dep=900, elev_arr=750, vr=150, vlof=158, vref=135,
        rotate_rate=2.5, lof_pitch=8.0, td_fpm=-150, td_ft=1200, bounce=False, touchback=False, sim_rate_s=0,
        pause_s=0, overspeed_s=0, cruise_ft=34000, t0=1_790_000_000.0, burn_pph=5000, fuel0=20000, go_around_dive=False):
    out = []
    t = t0
    fuel = fuel0
    D = runway_end(dep_icao, dep_rwy)
    A = runway_end(arr_icao, arr_rwy)
    stand = offset(D["lat"], D["lon"], D["hdg"] + 90, 400)

    def emit(lat, lon, alt, agl, ias, gs, vs, hdg, ground, dt, pitch=2.0, brake=False, eng=True, rate=1.0, paused=False, g=1.0):
        nonlocal t, fuel
        fuel -= burn_pph * dt / 3600 * (0.15 if ground else 1.0)
        out.append(Telemetry(t=t, lat=lat, lon=lon, alt_ft=alt, agl_ft=agl, ias=ias, gs=gs, vs_fpm=vs, hdg=hdg % 360, on_ground=ground,
                             engines_running=eng, parking_brake=brake, fuel_lbs=fuel, weight_lbs=110000 + fuel, gear_down=True,
                             flaps=0.2, g=g, pitch=pitch, sim_rate=rate, paused=paused))
        t += dt

    # stand, pushback, taxi to the runway end
    for _ in range(40):
        emit(*stand, elev_dep, 0, 0, 0, 0, D["hdg"], True, 0.5, brake=True)
    pos = stand
    for i in range(60):
        pos = offset(pos[0], pos[1], D["hdg"] - 90, 1.5 * 0.5)
        emit(*pos, elev_dep, 0, 3, 3, 0, D["hdg"], True, 0.5)
    brg = bearing(pos, (D["lat"], D["lon"]))
    dist = gc_nm(pos, (D["lat"], D["lon"])) * NM
    steps = int(dist / (15 * 0.514 * 0.5)) + 1
    for i in range(steps):
        f = (i + 1) / steps
        emit(pos[0] + (D["lat"] - pos[0]) * f, pos[1] + (D["lon"] - pos[1]) * f, elev_dep, 0, 15, 15, 0, brg, True, 0.5)
    for _ in range(12):  # lined up, holding
        emit(D["lat"], D["lon"], elev_dep, 0, 0, 0, 0, D["hdg"], True, 0.5)

    # takeoff roll and rotation (4 Hz)
    v, along, pitch = 0.0, 0.0, 0.5
    airborne, agl, lifted_t, tb_done = False, 0.0, None, False
    while True:
        dt = 0.25
        v += 3.2 * dt
        along += v * 0.514 * dt
        if v >= vr:
            pitch = min(lof_pitch + 3, pitch + rotate_rate * dt)
        if not airborne and v >= vlof and pitch >= lof_pitch:
            airborne, lifted_t = True, t
        if airborne:
            agl += 1500 / 60 * dt
            if touchback and not tb_done and 0.75 < t - lifted_t < 1.5:
                agl = 0.0
                if t - lifted_t > 1.25:
                    tb_done = True
        lat, lon = offset(D["lat"], D["lon"], D["hdg"], along)
        ground = not airborne or agl <= 0
        emit(lat, lon, elev_dep + agl, agl, v, v, 0 if ground else 1500, D["hdg"], ground, dt, pitch=pitch)
        if agl > 400:
            break

    # climb and cruise toward a fix 14 nm out on the arrival runway's extended centreline
    fix = offset(A["lat"], A["lon"], A["hdg"] + 180, 14 * NM)
    here = (lat, lon)
    alt = elev_dep + agl
    total = gc_nm(here, fix)
    flown = 0.0
    phase_t = 0.0
    while flown < total:
        remaining = total - flown
        desc_start = (alt - (elev_arr + 3000)) / 1000 * 3.2 if alt > elev_arr + 3000 else 0
        if remaining < max(desc_start, 25) and alt > elev_arr + 3000:
            vs = -2200 if alt > 12000 else -1400
            ias = 280 if alt > 11000 else 245
        elif alt < cruise_ft - 50 and remaining > 40:
            vs = 2200 if alt < 10000 else 1500
            ias = 245 if alt < 10000 else 290
        else:
            vs = 0
            ias = 280
        if overspeed_s and 3000 < alt < 9000 and vs < 0 and phase_t < overspeed_s:
            ias = 285
            phase_t += 1
        gs = ias * (1 + alt / 1000 * 0.018)
        dt = 1.0 if alt < 12000 else 5.0
        rate, paused = 1.0, False
        if vs == 0 and sim_rate_s > 0:
            rate, sim_rate_s = 4.0, sim_rate_s - dt
        elif vs == 0 and pause_s > 0:
            paused, pause_s = True, pause_s - dt
        step = 0 if paused else gs * dt / 3600
        flown = min(total, flown + step)
        if not paused:
            alt = max(elev_arr + 3000, min(cruise_ft, alt + vs * dt / 60))
        brg = bearing(here, fix)
        here = offset(here[0], here[1], brg, step * NM)
        emit(here[0], here[1], alt, alt - elev_dep, ias, gs, 0 if paused else vs, brg, False, dt, pitch=2.5, rate=rate, paused=paused)

    # final approach: 3 degrees from the fix to the touchdown point, then flare
    tdz = td_ft * FT
    dist = 14 * NM + tdz
    agl = alt - elev_arr
    d_left = dist
    off_ft, stage, stage_t = 0.0, 0, 0.0  # go-around at ~850 ft, then a steep descent to get back down (PAC9545 at JFK)
    while agl > 30:
        dt = 0.5
        gs = vref
        d_left -= gs * 0.514 * dt
        base = max(30, (d_left) * math.tan(math.radians(3)) / FT)
        vs = -700
        if go_around_dive:
            if stage == 0 and base < 700:
                stage = 1
            if stage == 1:                      # go around: climb at 1,500 fpm for 8 s
                off_ft += 1500 / 60 * dt + 700 / 60 * dt; vs = 1500; stage_t += dt
                if stage_t >= 8: stage = 2
            elif stage == 2:                    # then dive to get back onto the path
                off_ft = max(0.0, off_ft - 1500 / 60 * dt); vs = -2200
                if off_ft <= 0: stage = 3
        agl = max(30, base + off_ft)
        lat, lon = offset(A["lat"], A["lon"], A["hdg"], tdz - d_left)
        emit(lat, lon, elev_arr + agl, agl, vref, gs, vs, A["hdg"], False, dt, pitch=2.5)
    # flare: vertical speed eases to the touchdown rate
    vs = -700.0
    while agl > 0:
        dt = 0.25
        vs = min(td_fpm, vs + (td_fpm - (-700)) * dt / 2.5) if td_fpm > -700 else td_fpm
        agl = max(0.0, agl + vs * dt / 60)
        d_left -= vref * 0.514 * dt
        lat, lon = offset(A["lat"], A["lon"], A["hdg"], tdz - d_left)
        emit(lat, lon, elev_arr + agl, agl, vref - 3, vref - 3, vs if agl > 0 else vs, A["hdg"], agl <= 0, dt, pitch=4.0,
             g=1.0 if agl > 0 else (1.1 if td_fpm > -300 else 1.6))
    if bounce:
        for k in range(8):  # back in the air for two seconds
            d_left -= vref * 0.514 * 0.25
            lat, lon = offset(A["lat"], A["lon"], A["hdg"], tdz - d_left)
            emit(lat, lon, elev_arr + 6, 6, vref - 5, vref - 5, 200 if k < 4 else -300, A["hdg"], False, 0.25, pitch=4.0)
    # rollout and taxi in
    v = vref - 3
    along = tdz - d_left
    while v > 12:
        dt = 0.25
        v -= 5 * dt
        along += v * 0.514 * dt
        lat, lon = offset(A["lat"], A["lon"], A["hdg"], along)
        emit(lat, lon, elev_arr, 0, v, v, 0, A["hdg"], True, dt, pitch=1.0)
    for i in range(240):
        lat, lon = offset(lat, lon, A["hdg"] + 90, 8 * 0.514 * 0.5)
        emit(lat, lon, elev_arr, 0, 8, 8, 0, A["hdg"] + 90, True, 0.5)
    for i in range(60):
        emit(lat, lon, elev_arr, 0, 0, 0, 0, A["hdg"] + 90, True, 0.5, brake=True)
    for i in range(20):
        emit(lat, lon, elev_arr, 0, 0, 0, 0, A["hdg"] + 90, True, 0.5, brake=True, eng=False)
    return out
