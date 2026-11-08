"""PAC9644 (MD-11F, KCVG-KCLT): a soft landing that PAC scored -366 fpm with a bounce.

The recorded data showed one sample about every 0.85 s; the last airborne one, 0.8 s and ~5 ft before contact,
read -366 fpm while the flare was still easing the descent. The MD-11's height above ground reads ~17 ft with
the wheels on the runway, so a brief "on ground" flicker counted as a bounce. Landing Stats showed -61 fpm, 1.3 G.

This replays that profile at the old slow rate and at the new fast landing rate.
Run from the PAC folder: python tests/test_landing_pac9644.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim_sources import Telemetry  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


GROUND_AGL = 17.0       # MD-11 reference point above the runway with the wheels down
KCLT = {"icao": "KCLT", "lat": 35.214, "lon": -80.943}


def tel(t, agl, vs, on_ground, g=1.0, td=None, ias=137.0):
    return Telemetry(t=t, lat=35.2216, lon=-80.9670, alt_ft=748 + agl, agl_ft=agl, ias=ias, gs=ias - 4, vs_fpm=vs,
                     hdg=176, on_ground=on_ground, engines_running=True, parking_brake=False, fuel_lbs=18211,
                     weight_lbs=440000, gear_down=True, flaps=1.0, g=g, touchdown_fpm=td, true_alt_ft=748 + agl)


def profile(dt):
    """The flare: -470 fpm at 31 ft easing to -60 fpm at contact (t=0), a flicker off the ground at +0.3 s
    that never climbs, G 1.3 at contact, then the rollout."""
    out, t = [], -3.2
    while t < 0:
        frac = (t + 3.2) / 3.2
        vs = -470 + (470 - 60) * frac ** 2
        agl = GROUND_AGL + max(0.2, 14 * (1 - frac) ** 1.6)
        out.append(tel(round(t, 2), agl, vs, False))
        t += dt
    out.append(tel(0.0, GROUND_AGL, -60, True, g=1.3))
    out.append(tel(0.3, GROUND_AGL + 0.4, 10, False, g=1.05))     # strut rebound: off the ground briefly, never climbs
    t = 0.3 + dt
    while t < 6:
        out.append(tel(round(t, 2), GROUND_AGL, 0, True, ias=137 - 3 * t))
        t += dt
    return out


def land(samples):
    r = FlightRecorder({"flight_number": "PAC9644", "aircraft": "MD11F", "mission": {"origin": KCLT, "destination": KCLT}})
    r.phase, r.oooi["off"], r.start_t = "APPROACH", -3600, -4000
    r.last = samples[0]
    for s in samples:
        r.update(s)
    return r


print("Old sample rate (one every 0.85 s), as on PAC9644")
slow = land(profile(0.85))
L = slow.landing or {}
check("a landing was recorded", bool(L), slow.phase)
check("the PIREP shows how far before contact the rate was taken", (L.get("contact_gap_s") or 0) >= 0.5, L)
check("a strut flicker on the runway is not a bounce", slow.bounces == 0, slow.bounces)

print("New fast landing rate (about 6 samples a second)")
fast = land(profile(0.16))
L = fast.landing or {}
check("the rate is taken within 0.2 s of contact", (L.get("contact_gap_s") if L.get("contact_gap_s") is not None else 9) <= 0.2, L)
check("a soft landing scores soft (under 150 fpm)", -150 <= L.get("rate_fpm", -999) < 0, L)
check("the G peak at contact is kept (1.3 G, not 1.0)", L.get("g") == 1.3, L)
check("still no bounce", fast.bounces == 0, fast.bounces)

print("A real bounce still counts")
real = profile(0.16)
i = next(k for k, s in enumerate(real) if s.t == 0.3)
bounce = [tel(0.3 + 0.16 * n, GROUND_AGL + 1 + 2.5 * n, 300 - 120 * n, False) for n in range(4)]
real = real[:i] + bounce + [tel(0.95 + 0.16 * n, GROUND_AGL + 6 - 2.5 * n, -250, False) for n in range(3)] \
    + [tel(1.5, GROUND_AGL, -250, True, g=1.4)] + [s for s in real[i + 1:] if s.t > 1.5]
rb = land(real)
check("climbing 5+ ft off the runway is a bounce", rb.bounces == 1, rb.bounces)
check("the landing rate stays the first contact's", -150 <= (rb.landing or {}).get("rate_fpm", -999) < 0, rb.landing)

print()
print("All PAC9644 landing checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
