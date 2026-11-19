"""PAC ACARS 1.2: block time segments, plan-versus-actual time checks, the engine start review, and the ACARS log
messages that go with them. All of it is informational and must never touch a score."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import flight_timing as ft  # noqa: E402
from tracker import FlightRecorder  # noqa: E402
from test_acars_config_capture import _booking, _telemetry  # noqa: E402

T0 = 1_800_000_000.0   # an arbitrary epoch second; only differences matter


def _oooi(out=0, off=15, on=70, in_=80):
    """Minutes after T0 for OUT, OFF, ON, IN."""
    return {"out": T0 + out * 60, "off": T0 + off * 60, "on": T0 + on * 60, "in": T0 + in_ * 60}


def _check(res, cid):
    return next(c for c in res["checks"] if c["id"] == cid)


# ------------------------------------------------------------------ block segments
def test_segments_add_up():
    s = ft.block_segments(_oooi())
    assert (s["taxi_out_min"], s["airborne_min"], s["taxi_in_min"], s["block_min"]) == (15.0, 55.0, 10.0, 80.0)
    assert s["zulu"]["out"] and s["zulu"]["in"]


def test_missing_times_stay_none():
    s = ft.block_segments({"out": T0, "off": T0 + 600, "on": None, "in": None})
    assert s["taxi_out_min"] == 10.0 and s["airborne_min"] is None and s["block_min"] is None


def test_no_out_time_gives_no_checks():
    assert ft.time_checks({"out": None, "off": None, "on": None, "in": None}, {}) is None


# ------------------------------------------------------------------ departure window
def _ofp(planned_out_min=0, enroute=55, block=75):
    return {"departure_time_utc": str(int(T0 + planned_out_min * 60)), "est_enroute_min": enroute, "est_block_min": block}


def test_departure_inside_the_window_is_on_time_either_side():
    for planned in (-9, 0, 9):   # actual out is T0, so these are 9 minutes early, exact and 9 late
        assert _check(ft.time_checks(_oooi(), _ofp(planned)), "departure")["status"] == "ok"


def test_departure_outside_the_window_is_flagged_late_or_early():
    assert _check(ft.time_checks(_oooi(), _ofp(-25)), "departure")["status"] == "late"    # planned 25 min before OUT
    assert _check(ft.time_checks(_oooi(), _ofp(25)), "departure")["status"] == "early"


def test_plan_for_another_day_is_not_compared():
    c = _check(ft.time_checks(_oooi(), _ofp(-60 * 20)), "departure")
    assert c["status"] == "na" and "another day" in c["text"]


def test_no_simbrief_plan_is_not_a_failure():
    res = ft.time_checks(_oooi(), {})
    assert _check(res, "departure")["status"] == "na"
    assert _check(res, "block")["status"] == "na"


# ------------------------------------------------------------------ taxi allowance by airport size
def test_taxi_allowance_follows_airport_size():
    assert ft.taxi_allowance("L") == (20, 30) and ft.taxi_allowance("S") == (6, 10)
    assert ft.taxi_allowance("?") == ft.taxi_allowance("M")   # unknown size falls back to medium


def test_long_taxi_is_over_at_a_small_airport_but_fine_at_a_large_one():
    o = _oooi(off=18)   # 18 minute taxi out
    assert _check(ft.time_checks(o, {}, dep_size="S", arr_size="S"), "taxi_out")["status"] == "over"
    assert _check(ft.time_checks(o, {}, dep_size="L", arr_size="L"), "taxi_out")["status"] == "ok"


# ------------------------------------------------------------------ airborne, arrival and block
def test_airborne_tolerance_and_text():
    assert _check(ft.time_checks(_oooi(on=15 + 58), _ofp(enroute=55)), "airborne")["status"] == "ok"      # +3 min
    c = _check(ft.time_checks(_oooi(on=15 + 70), _ofp(enroute=55)), "airborne")                            # +15 min
    assert c["status"] == "over" and "+15 min" in c["text"]


def test_arrival_is_measured_from_takeoff_not_from_a_late_departure():
    # left the gate 40 minutes after the plan, but flew the planned 55 and taxied in 8: arrival is still fine
    res = ft.time_checks(_oooi(out=0, off=15, on=70, in_=78), _ofp(planned_out_min=-40, enroute=55, block=75), "L", "L")
    assert _check(res, "departure")["status"] == "late"
    assert _check(res, "arrival")["status"] == "ok"


def test_arrival_late_when_the_flight_was_slow_after_takeoff():
    # takeoff at 15 + 55 planned enroute + 30 minute large-airport taxi-in allowance = 100; on the stand at 120 is 20 late
    res = ft.time_checks(_oooi(out=0, off=15, on=95, in_=120), _ofp(enroute=55), "L", "L")
    assert _check(res, "arrival")["status"] == "late"
    # on the stand at 108 is 8 after the expected 100, inside the 10 minute window
    assert _check(ft.time_checks(_oooi(out=0, off=15, on=95, in_=108), _ofp(enroute=55), "L", "L"), "arrival")["status"] == "ok"


def test_block_check_explains_where_the_minutes_went():
    # planned: 55 airborne + 20 taxi = 75. actual: 15 + 60 + 12 = 87 (+12): airborne +5, taxi +7
    res = ft.time_checks(_oooi(out=0, off=15, on=75, in_=87), _ofp(enroute=55, block=75), "L", "L")
    c = _check(res, "block")
    assert c["status"] == "late" and c["diff_min"] == 12.0
    assert "Airborne +5 min" in c["text"] and "taxi +7 min" in c["text"]


def test_time_checks_never_carry_a_score():
    res = ft.time_checks(_oooi(), _ofp())
    assert res["informational"] is True
    assert not any("score" in c or "penalty" in c for c in res["checks"])


# ------------------------------------------------------------------ engine start review
def _starts(order, gap=60.0):
    return [{"n": n, "t": 1000.0 + i * gap, "z": "1200Z", "phase": "PUSHBACK", "seq": i + 1} for i, n in enumerate(order)]


def test_no_starts_gives_no_review():
    assert ft.engine_review([], 2) is None


def test_twin_sequences_both_listed():
    for order in ([1, 2], [2, 1]):
        r = ft.engine_review(_starts(order), 2)
        assert r["sequence"]["status"] == "listed" and r["order"] == order


def test_quad_sequence_listed_and_unlisted():
    assert ft.engine_review(_starts([2, 4, 1, 3]), 4)["sequence"]["status"] == "listed"
    r = ft.engine_review(_starts([1, 2, 3, 4]), 4)
    assert r["sequence"]["status"] == "unlisted" and "Informational only" in r["sequence"]["text"]


def test_three_engine_has_no_defined_sequence_yet():
    assert ft.engine_review(_starts([1, 2, 3]), 3)["sequence"]["status"] == "none_defined"


def test_incomplete_start_is_reported_with_the_reason():
    r = ft.engine_review(_starts([1]), 2)
    assert r["sequence"]["status"] == "incomplete" and r["started"] == 1 and r["expected"] == 2
    assert r["notes"] and "already running" in r["notes"][0]


def test_total_start_time_against_the_target():
    assert ft.engine_review(_starts([1, 2], gap=120), 2)["timing"]["status"] == "ok"
    slow = ft.engine_review(_starts([1, 2], gap=400), 2)
    assert slow["timing"]["status"] == "slow" and slow["span_s"] == 400.0 and slow["gaps_s"] == [400.0]


# ------------------------------------------------------------------ ACARS log messages (client side)
def _texts(rec):
    return [m["text"] for m in rec.messages]


def test_each_engine_start_and_the_all_running_summary_reach_the_log():
    rec = FlightRecorder(_booking())
    rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))
    for t in (1001.0, 1002.0, 1003.0):
        rec.update(_telemetry(t=t, eng1_running=True, eng2_running=False))
    for t in (1060.0, 1061.0, 1062.0, 1063.0):
        rec.update(_telemetry(t=t, eng1_running=True, eng2_running=True))
    texts = _texts(rec)
    assert sum(1 for x in texts if x.startswith("ENG ") and " START " in x) == 2
    summary = [x for x in texts if x.startswith("ALL ENGINES RUNNING")]
    assert len(summary) == 1 and "ORDER 1-2" in summary[0]


def test_message_helper_failure_never_breaks_recording():
    rec = FlightRecorder(_booking())
    rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))   # logon and baseline with a working log
    rec.msg = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("log broke"))
    for t in (1001.0, 1002.0, 1003.0):
        rec.update(_telemetry(t=t, eng1_running=True, eng2_running=False))
    assert len(rec.eng_starts) == 1


def test_block_summary_message_when_going_on_block():
    rec = FlightRecorder(_booking())
    rec.oooi.update({"out": 1000.0, "off": 1900.0, "on": 5200.0, "in": None})
    rec._in(5800.0, _telemetry(t=5800.0))
    block = [x for x in _texts(rec) if x.startswith("BLOCK ")]
    assert block == ["BLOCK 1:20  TAXI OUT 0:15  AIR 0:55  TAXI IN 0:10"]


# ------------------------------------------------------------------ wording and the single-engine taxi check
def test_a_very_short_taxi_reads_well_under_the_allowance():
    c = _check(ft.time_checks(_oooi(out=0, off=15, on=70, in_=72), {}, "L", "L"), "taxi_in")
    assert c["status"] == "ok" and "well under the 30 minute allowance" in c["text"]


def test_single_engine_taxi_is_dropped_when_all_engines_started_together():
    import app as A
    quad = [{"n": n, "t": 1000.0 + i * 18, "phase": "PUSHBACK" if i < 2 else "TAXI_OUT"} for i, n in enumerate((4, 3, 1, 2))]
    assert A.single_engine_taxi_plausible(quad, 4) is False          # all four up within a minute: a normal start
    twin = [{"n": 1, "t": 1000.0, "phase": "PUSHBACK"}, {"n": 2, "t": 1400.0, "phase": "TAXI_OUT"}]
    assert A.single_engine_taxi_plausible(twin, 2) is True            # second engine started minutes into taxi
    assert A.single_engine_taxi_plausible(quad[:2], 4) is True        # incomplete record: trust ACARS
