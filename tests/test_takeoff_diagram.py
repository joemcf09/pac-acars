"""The takeoff runway diagram needs start_ft, liftoff_ft and runway_length_ft. A liftoff far past the runway end used to
leave liftoff_ft empty, which silently removed the diagram. These tests pin the behavior with synthetic KONT 26L departures."""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import analysis  # noqa: E402

DATA = ROOT / "data"
FT = 0.3048


def _end26l():
    rws = analysis.runways(DATA)
    rec = next(r for r in rws["KONT"] if "26L" in (r[0], r[5]))
    return rec[6], rec[7], rec[8]   # threshold lat, lon, heading of the 26L end


def _pos(tlat, tlon, thdg, along_ft):
    d, h = along_ft * FT, math.radians(thdg)
    return tlat + d * math.cos(h) / 111320.0, tlon + d * math.sin(h) / (111320.0 * math.cos(math.radians(tlat)))


def _series(start_ft, liftoff_ft):
    """[t, agl, vs, ias, g, lat, lon, hdg, on_ground, gs, pitch] at 4 Hz: a ground roll, then 10 s airborne."""
    tlat, tlon, thdg = _end26l()
    rows, t, n = [], 0.0, 120
    for i in range(n):
        a = start_ft + (liftoff_ft - start_ft) * (i / (n - 1)) ** 1.6
        la, lo = _pos(tlat, tlon, thdg, a)
        ias = 20 + 200 * (i / (n - 1))
        rows.append([t, 0, 0, ias, 1.0, la, lo, thdg, 1, ias, 1.5 + (4 if i > n - 15 else 0)])
        t += 0.25
    for i in range(40):
        la, lo = _pos(tlat, tlon, thdg, liftoff_ft + i * 40)
        rows.append([t, 5 + i * 10, 1400, 225 + i, 1.1, la, lo, thdg, 0, 230, 12.0])
        t += 0.25
    return rows


def _analyze(start_ft, liftoff_ft):
    return analysis.analyze_takeoff(_series(start_ft, liftoff_ft), 0, ["KONT"], DATA, tail_limit=11.5)


def _diagram_inputs_present(ta):
    return ta.get("start_ft") is not None and bool(ta.get("runway_length_ft")) and ta.get("liftoff_ft") is not None


def test_liftoff_inside_runway_is_measured_not_estimated():
    ta = _analyze(200, 9000)
    assert _diagram_inputs_present(ta)
    assert ta["liftoff_ft"] == 9000 and ta["remaining_ft"] == 1200
    assert not ta.get("liftoff_estimated")


def test_liftoff_just_past_runway_end_keeps_the_diagram():
    ta = _analyze(0, 10393)
    assert _diagram_inputs_present(ta)
    assert ta["remaining_ft"] == 0


def test_liftoff_far_past_runway_end_keeps_the_diagram_and_is_marked_estimated():
    ta = _analyze(0, 12200)   # beyond the matcher's tolerance: this used to drop liftoff_ft
    assert _diagram_inputs_present(ta)
    assert ta["liftoff_estimated"] is True
    assert ta["liftoff_ft"] > ta["runway_length_ft"]
    assert ta["remaining_ft"] == 0
    assert ta["roll_ft"] > 0
