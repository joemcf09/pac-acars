"""
PAC ACARS 1.2 -- Configuration Capture tests
Covers: engine startup tracking, single-engine taxi, dep/arr config snapshots,
        exception isolation, and from_export() round-trip.

These tests are INFORMATIONAL only; they never touch scoring or the existing
FlightRecorder attribute set.
"""
import pytest
from unittest.mock import patch
from tracker import FlightRecorder, _config_snapshot, expected_engines
from sim_sources import Telemetry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _booking(aircraft="B737", engines=None):
    """Minimal booking dict matching the structure FlightRecorder.__init__ expects."""
    return {
        "flight_number": "PAC001",
        "aircraft": aircraft,
        "aircraft_info": {"icao": aircraft, "engines": engines or 2},
        "mission": {
            "origin":      {"icao": "EGLL", "lat": 51.47, "lon": -0.46, "elevation": 83},
            "destination": {"icao": "EGCC", "lat": 53.35, "lon": -2.27, "elevation": 257},
        },
        "ofp": {},
    }


def _telemetry(**kw):
    """Build a Telemetry snapshot with safe defaults.
    Uses the actual Telemetry dataclass field names."""
    defaults = dict(
        t=1000.0, lat=51.47, lon=-0.46, alt_ft=0, agl_ft=0,
        ias=0.0, gs=0.0, vs_fpm=0.0, hdg=90.0,
        on_ground=True, weight_lbs=100000, fuel_lbs=20000,
        gear_down=True, flaps=0.0, bank=0.0, g=1.0,
        engines_running=False, num_engines=2,
        eng1_running=False, eng2_running=False,
        eng3_running=None, eng4_running=None,
        # Lighting fields (None = not available from this sim/aircraft)
        beacon=None, nav_lights=None, strobe=None,
        landing_lights=None, taxi_light=None,
        # Other optional fields
        parking_brake=None, touchdown_fpm=None, slew=None,
        pitch=None, sim_rate=None, paused=None, true_alt_ft=None,
        cg_pct=None,
    )
    defaults.update(kw)
    return Telemetry(**defaults)


def _make_rec(aircraft="B737"):
    """Create a FlightRecorder in PREFLIGHT with the first sample already committed."""
    rec = FlightRecorder(_booking(aircraft))
    s0 = _telemetry(t=1000.0)
    rec.update(s0)          # logon + baseline
    return rec


def _advance(rec, s):
    """Call update() and return rec for chaining."""
    rec.update(s)
    return rec


# ---------------------------------------------------------------------------
# 1. dep_config and arr_config snapshots
# ---------------------------------------------------------------------------

class TestConfigSnapshot:
    def test_snapshot_preserves_none_lights(self):
        s = _telemetry(beacon=None, nav_lights=True, strobe=False,
                       landing_lights=None, taxi_light=True)
        snap = _config_snapshot(s)
        assert snap["beacon"] is None
        assert snap["nav"] is True
        assert snap["strobe"] is False
        assert snap["landing"] is None
        assert snap["taxi"] is True

    def test_snapshot_preserves_none_engines(self):
        s = _telemetry(eng1_running=True, eng2_running=False,
                       eng3_running=None, eng4_running=None)
        snap = _config_snapshot(s)
        assert snap["eng1_running"] is True
        assert snap["eng2_running"] is False
        assert snap["eng3_running"] is None
        assert snap["eng4_running"] is None

    def test_dep_config_set_at_out(self):
        """dep_config is populated when _out() fires."""
        rec = _make_rec()
        s_out = _telemetry(t=1100.0, beacon=True, nav_lights=True, taxi_light=True,
                           eng1_running=True, eng2_running=True)
        rec._out(1100.0, s_out)
        assert rec.dep_config["beacon"] is True
        assert rec.dep_config["nav"] is True
        assert rec.dep_config["eng1_running"] is True

    def test_arr_config_set_at_in(self):
        """arr_config is populated when _in() fires."""
        rec = _make_rec()
        s_in = _telemetry(t=5000.0, beacon=False, nav_lights=True,
                          eng1_running=False, eng2_running=False)
        rec._in(5000.0, s_in)
        assert rec.arr_config["beacon"] is False
        assert rec.arr_config["eng1_running"] is False
        assert rec.arr_config["eng2_running"] is False

    def test_dep_arr_config_independent(self):
        """dep_config and arr_config are separate dicts."""
        rec = _make_rec()
        rec._out(1100.0, _telemetry(t=1100.0, taxi_light=True))
        rec._in(5000.0,  _telemetry(t=5000.0, taxi_light=False))
        assert rec.dep_config["taxi"] is True
        assert rec.arr_config["taxi"] is False


# ---------------------------------------------------------------------------
# 2. Engine startup tracking -- twin-engine
# ---------------------------------------------------------------------------

class TestEngineStartTwin:
    def test_no_start_on_first_connect(self):
        """First sample sets baseline; must not record an engine start even if running=True."""
        rec = FlightRecorder(_booking())
        s = _telemetry(t=1000.0, eng1_running=True, eng2_running=False)
        rec.update(s)
        assert rec.eng_starts == []

    def test_twin_start_eng1_then_eng2(self):
        """Twin: eng1 starts then eng2 starts; expect two events in order."""
        rec = FlightRecorder(_booking())
        # baseline (both off)
        rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))

        # eng1 transitions; debounce needs ~2s
        for t in [1001.0, 1002.0, 1003.0]:
            rec.update(_telemetry(t=t, eng1_running=True, eng2_running=False))

        assert len(rec.eng_starts) == 1
        assert rec.eng_starts[0]["n"] == 1
        assert rec.eng_starts[0]["seq"] == 1

        # eng2 transitions
        for t in [1010.0, 1011.0, 1012.0]:
            rec.update(_telemetry(t=t, eng1_running=True, eng2_running=True))

        assert len(rec.eng_starts) == 2
        assert rec.eng_starts[1]["n"] == 2
        assert rec.eng_starts[1]["seq"] == 2

    def test_no_duplicate_eng_start(self):
        """An engine already in eng_starts must not get a second entry."""
        rec = FlightRecorder(_booking())
        rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))
        for t in [1001.0, 1002.0, 1003.0]:
            rec.update(_telemetry(t=t, eng1_running=True, eng2_running=False))
        # keep running -- no second entry
        for t in [1010.0, 1020.0, 1030.0]:
            rec.update(_telemetry(t=t, eng1_running=True, eng2_running=False))
        eng1_entries = [e for e in rec.eng_starts if e["n"] == 1]
        assert len(eng1_entries) == 1

    def test_debounce_rejects_brief_spike(self):
        """A single-sample True spike that disappears must not register as a start."""
        rec = FlightRecorder(_booking())
        rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))
        rec.update(_telemetry(t=1001.0, eng1_running=True,  eng2_running=False))
        rec.update(_telemetry(t=1001.5, eng1_running=False, eng2_running=False))  # drops back
        assert rec.eng_starts == []

    def test_startup_stops_at_takeoff(self):
        """Engine starts detected after TAKEOFF phase must be ignored."""
        rec = _make_rec()
        # Jump to TAKEOFF manually
        rec.phase = "TAKEOFF"
        # Even if eng2 goes True, _config_capture must not add an entry
        rec.update(_telemetry(t=1200.0, eng1_running=True, eng2_running=True))
        rec.update(_telemetry(t=1201.0, eng1_running=True, eng2_running=True))
        rec.update(_telemetry(t=1202.0, eng1_running=True, eng2_running=True))
        assert rec.eng_starts == []

    def test_startup_recorded_during_pushback(self):
        """Engine start during PUSHBACK phase must be recorded (PUSHBACK is in _CONFIG_PHASES)."""
        rec = FlightRecorder(_booking())
        # baseline: both engines off in PUSHBACK
        rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))
        rec.phase = "PUSHBACK"
        # eng1 starts during PUSHBACK
        for t in [1001.0, 1002.0, 1003.0]:
            rec.update(_telemetry(t=t, eng1_running=True, eng2_running=False))
        assert len(rec.eng_starts) == 1
        assert rec.eng_starts[0]["n"] == 1
        assert rec.eng_starts[0]["phase"] == "PUSHBACK"


# ---------------------------------------------------------------------------
# 3. Engine startup tracking -- quad-engine (B747)
# ---------------------------------------------------------------------------

class TestEngineStartQuad:
    def test_quad_all_four_start(self):
        """B747 four-engine: all four engines start in sequence."""
        rec = FlightRecorder(_booking("B744"))
        s0 = _telemetry(t=1000.0, num_engines=4,
                        eng1_running=False, eng2_running=False,
                        eng3_running=False, eng4_running=False)
        rec.update(s0)

        for n, start_t in enumerate([1010.0, 1020.0, 1030.0, 1040.0], 1):
            kw = {f"eng{i}_running": (i <= n) for i in range(1, 5)}
            kw["num_engines"] = 4
            for tt in [start_t, start_t + 1.0, start_t + 2.0]:
                rec.update(_telemetry(t=tt, **kw))

        assert len(rec.eng_starts) == 4
        assert [e["n"] for e in rec.eng_starts] == [1, 2, 3, 4]
        assert [e["seq"] for e in rec.eng_starts] == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# 4. Reconnect / missing data safety
# ---------------------------------------------------------------------------

class TestReconnectSafety:
    def test_none_resets_baseline_no_spurious_start(self):
        """When eng1 goes None (disconnect) then comes back True,
        no start event should fire for the reconnect sample alone."""
        rec = FlightRecorder(_booking())
        rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))
        # disconnect
        rec.update(_telemetry(t=1001.0, eng1_running=None, eng2_running=False))
        # reconnect with engine already running -- this is a new baseline, not a start
        rec.update(_telemetry(t=1002.0, eng1_running=True, eng2_running=False))
        assert rec.eng_starts == []

    def test_none_then_start_detected(self):
        """After a disconnect/reconnect cycle, a fresh False->True transition is still tracked."""
        rec = FlightRecorder(_booking())
        rec.update(_telemetry(t=1000.0, eng1_running=False, eng2_running=False))
        # disconnect & reconnect with engine off
        rec.update(_telemetry(t=1001.0, eng1_running=None, eng2_running=False))
        rec.update(_telemetry(t=1002.0, eng1_running=False, eng2_running=False))  # new baseline
        # now start eng1
        for t in [1003.0, 1004.0, 1005.0]:
            rec.update(_telemetry(t=t, eng1_running=True, eng2_running=False))
        assert len(rec.eng_starts) == 1
        assert rec.eng_starts[0]["n"] == 1


# ---------------------------------------------------------------------------
# 5. Single-engine taxi
# ---------------------------------------------------------------------------

class TestSingleEngTaxi:
    def _rec_in_taxi(self):
        rec = _make_rec()
        rec.phase = "TAXI_OUT"
        return rec

    def test_single_eng_taxi_detected(self):
        """Moving with 1-of-2 engines running during TAXI_OUT sets the flag."""
        rec = self._rec_in_taxi()
        s = _telemetry(t=1200.0, gs=5.0, num_engines=2,
                       eng1_running=True, eng2_running=False)
        rec.update(s)
        assert rec.single_eng_taxi is True


    def test_no_flag_when_engine_status_unknown(self):
        """Unknown engine status must not trigger single-engine taxi."""
        rec = self._rec_in_taxi()
        s = _telemetry(
            t=1200.0,
            gs=5.0,
            num_engines=2,
            eng1_running=True,
            eng2_running=None,
        )
        rec.update(s)
        assert rec.single_eng_taxi is False

    
    def test_no_flag_when_both_running(self):
        """Both engines running: flag stays False."""
        rec = self._rec_in_taxi()
        s = _telemetry(t=1200.0, gs=5.0, num_engines=2,
                       eng1_running=True, eng2_running=True)
        rec.update(s)
        assert rec.single_eng_taxi is False

    def test_no_flag_when_stationary(self):
        """gs <= 2.0 (pushback/tow): flag stays False even with one engine."""
        rec = self._rec_in_taxi()
        s = _telemetry(t=1200.0, gs=1.0, num_engines=2,
                       eng1_running=True, eng2_running=False)
        rec.update(s)
        assert rec.single_eng_taxi is False

    def test_no_flag_outside_taxi_out(self):
        """PREFLIGHT phase: flag stays False even with single engine and movement."""
        rec = _make_rec()
        # stay in PREFLIGHT (default)
        s = _telemetry(t=1200.0, gs=5.0, num_engines=2,
                       eng1_running=True, eng2_running=False)
        rec.update(s)
        assert rec.single_eng_taxi is False

    def test_flag_never_resets(self):
        """Once set True the flag stays True."""
        rec = self._rec_in_taxi()
        rec.update(_telemetry(t=1200.0, gs=5.0, num_engines=2,
                              eng1_running=True, eng2_running=False))
        assert rec.single_eng_taxi is True
        # both running now
        rec.update(_telemetry(t=1300.0, gs=5.0, num_engines=2,
                              eng1_running=True, eng2_running=True))
        assert rec.single_eng_taxi is True

    def test_no_flag_single_engine_aircraft(self):
        """Single-engine aircraft: flag must never be set."""
        rec = _make_rec()
        rec.phase = "TAXI_OUT"
        s = _telemetry(t=1200.0, gs=5.0, num_engines=1,
                       eng1_running=True, eng2_running=None)
        rec.update(s)
        assert rec.single_eng_taxi is False


# ---------------------------------------------------------------------------
# 6. Exception isolation
# ---------------------------------------------------------------------------

class TestExceptionIsolation:
    def test_config_capture_exception_does_not_crash_update(self):
        """A bug in _config_capture must not propagate to update() callers."""
        rec = _make_rec()
        with patch.object(rec, "_config_capture", side_effect=RuntimeError("test error")):
            # update() must not raise
            rec.update(_telemetry(t=1100.0))
        # flight is still tracking
        assert rec.phase is not None

    def test_config_capture_exception_recorded(self):
        """Exception message is appended to coach_error."""
        rec = _make_rec()
        with patch.object(rec, "_config_capture", side_effect=RuntimeError("cfg boom")):
            rec.update(_telemetry(t=1100.0))
        assert "cfg" in (rec.coach_error or "")


# ---------------------------------------------------------------------------
# 7. export() and from_export() round-trip
# ---------------------------------------------------------------------------

class TestExportRoundTrip:
    def test_new_attributes_present_in_export(self):
        """eng_starts, single_eng_taxi, dep_config, arr_config appear in export."""
        rec = _make_rec()
        exp = rec.export()
        assert "eng_starts" in exp
        assert "single_eng_taxi" in exp
        assert "dep_config" in exp
        assert "arr_config" in exp

    def test_eng_prev_excluded_from_export(self):
        """_eng_prev (underscore prefix) must NOT appear in export."""
        rec = _make_rec()
        exp = rec.export()
        assert "_eng_prev" not in exp
        assert "eng_prev" not in exp

    def test_round_trip_new_flight(self):
        """from_export() restores new 1.2 attributes for a flight that has them."""
        rec = _make_rec()
        rec.eng_starts = [{"n": 1, "t": 1050.0, "z": "1030Z", "phase": "PREFLIGHT", "seq": 1}]
        rec.single_eng_taxi = True
        rec.dep_config = {"beacon": True,  "nav": True,  "strobe": None,
                          "landing": False, "taxi": True,
                          "eng1_running": True,  "eng2_running": False,
                          "eng3_running": None,  "eng4_running": None}
        rec.arr_config = {"beacon": False, "nav": True,  "strobe": None,
                          "landing": None,  "taxi": False,
                          "eng1_running": False, "eng2_running": False,
                          "eng3_running": None,  "eng4_running": None}
        exp = rec.export()

        rec2 = FlightRecorder.from_export(_booking(), exp)
        assert rec2.eng_starts == rec.eng_starts
        assert rec2.single_eng_taxi is True
        assert rec2.dep_config == rec.dep_config
        assert rec2.arr_config == rec.arr_config

    def test_round_trip_old_flight_missing_attributes(self):
        """from_export() on a pre-1.2 export (missing new keys) must not raise,
        and must initialize to safe defaults."""
        rec = _make_rec()
        exp = rec.export()
        # Simulate an old PIREP that doesn't have the 1.2 keys
        for key in ("eng_starts", "single_eng_taxi", "dep_config", "arr_config"):
            exp.pop(key, None)

        rec2 = FlightRecorder.from_export(_booking(), exp)
        assert rec2.eng_starts == []
        assert rec2.single_eng_taxi is False
        assert rec2.dep_config == {}
        assert rec2.arr_config == {}


# ---------------------------------------------------------------------------
# 8. Engine-count edge cases
# ---------------------------------------------------------------------------

class TestEngineCountEdgeCases:
    def test_xplane_twin_absent_engines_always_false_no_spurious_start(self):
        """X-Plane twin: eng3_running=False and eng4_running=False throughout.
        These absent engines must never produce a start event because they never
        transition False->True.  (X-Plane uses 0.0 as the default, so absent
        engines read False rather than None.)"""
        rec = FlightRecorder(_booking("B737", engines=2))
        # Baseline: 2 engines off, absent pair always False (X-Plane style)
        rec.update(_telemetry(t=1000.0, num_engines=2,
                              eng1_running=False, eng2_running=False,
                              eng3_running=False, eng4_running=False))
        # Both real engines start
        for t in [1001.0, 1002.0, 1003.0]:
            rec.update(_telemetry(t=t, num_engines=2,
                                  eng1_running=True, eng2_running=True,
                                  eng3_running=False, eng4_running=False))
        # Only 2 starts; eng3/eng4 never went True so no event
        assert len(rec.eng_starts) == 2
        assert {e["n"] for e in rec.eng_starts} == {1, 2}

    def test_three_engine_aircraft(self):
        """Three-engine aircraft (num_engines=3): only engines 1-3 start;
        eng4_running=None (MSFS-style unavailable) must not block anything."""
        rec = FlightRecorder(_booking("B727", engines=3))
        rec.update(_telemetry(t=1000.0, num_engines=3,
                              eng1_running=False, eng2_running=False,
                              eng3_running=False, eng4_running=None))
        for n, start_t in enumerate([1010.0, 1020.0, 1030.0], 1):
            kw = {f"eng{i}_running": (i <= n) for i in range(1, 4)}
            kw["eng4_running"] = None
            kw["num_engines"] = 3
            for t in [start_t, start_t + 1.0, start_t + 2.0]:
                rec.update(_telemetry(t=t, **kw))
        assert len(rec.eng_starts) == 3
        assert {e["n"] for e in rec.eng_starts} == {1, 2, 3}

    def test_num_engines_none_does_not_crash(self):
        """num_engines=None (telemetry unavailable): engine loop still runs on
        range(1,5), no crash, and start events still fire for the engines that
        do report a transition."""
        rec = FlightRecorder(_booking())
        rec.update(_telemetry(t=1000.0, num_engines=None,
                              eng1_running=False, eng2_running=False,
                              eng3_running=None, eng4_running=None))
        for t in [1001.0, 1002.0, 1003.0]:
            rec.update(_telemetry(t=t, num_engines=None,
                                  eng1_running=True, eng2_running=False,
                                  eng3_running=None, eng4_running=None))
        assert len(rec.eng_starts) == 1
        assert rec.eng_starts[0]["n"] == 1
def test_xplane_missing_engine_dataref_preserves_unknown():
    """Missing engine datarefs must remain None, not become False."""
    from sim_sources import XPlaneSource

    source = XPlaneSource()
    source.values = {
        "lat": 51.47,
        "lon": -0.46,
        "eng1": 1.0,
        "eng2": 0.0,
        # eng3 and eng4 intentionally missing
    }
    source.last_rx = 1000.0

    with patch("sim_sources.time.time", return_value=1000.0):
        with patch.object(source, "_pump"):
            telemetry = source.read()

    assert telemetry is not None
    assert telemetry.eng1_running is True
    assert telemetry.eng2_running is False
    assert telemetry.eng3_running is None
    assert telemetry.eng4_running is None