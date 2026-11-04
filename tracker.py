"""Flight phase detection and flight recording for PAC ACARS."""
from __future__ import annotations

import datetime as dt
import threading
import time

from sim_sources import Telemetry, gc_distance_nm, SourceError

PHASES = [
    ("PREFLIGHT", "Preflight"),
    ("PUSHBACK", "Pushback"),
    ("TAXI_OUT", "Taxi out"),
    ("TAKEOFF", "Takeoff roll"),
    ("INITIAL_CLIMB", "Initial climb"),
    ("CLIMB", "Climb"),
    ("CRUISE", "Cruise"),
    ("DESCENT", "Descent"),
    ("APPROACH", "Approach"),
    ("GO_AROUND", "Go-around"),
    ("LANDING", "Landing rollout"),
    ("TAXI_IN", "Taxi in"),
    ("ARRIVED", "On block"),
]
PHASE_LABEL = dict(PHASES)
# approximate pitch at which the tail touches the runway, by fleet type (degrees)
AIRBORNE = {"INITIAL_CLIMB", "CLIMB", "CRUISE", "DESCENT", "APPROACH", "GO_AROUND"}


ENGINES_BY_ICAO = {"B741": 4, "B742": 4, "B743": 4, "B744": 4, "B748": 4, "B74F": 4, "B48F": 4, "MD11": 3, "B721": 3, "B722": 3,
                   "DC10": 3, "L101": 3, "A342": 4, "A343": 4, "A345": 4, "A346": 4, "A388": 4, "IL76": 4, "C17": 4}


def expected_engines(booking):
    """How many engines the booked type has: 2 unless it's a known three- or four-engine type."""
    info = booking.get("aircraft_info") or {}
    code = str(info.get("icao") or booking.get("aircraft") or "").upper()[:4]
    if not code:
        return None
    return ENGINES_BY_ICAO.get(code, 2)


def zulu(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%H%MZ")


class Debounce:
    """True once a condition has held continuously for `hold` sim-seconds."""

    def __init__(self):
        self.since = {}

    def check(self, key, cond, t, hold):
        if not cond:
            self.since.pop(key, None)
            return False
        self.since.setdefault(key, t)
        return t - self.since[key] >= hold


class FlightRecorder:
    def __init__(self, booking: dict):
        self.booking = booking
        ofp = booking.get("ofp") or {}
        m = booking["mission"]
        self.dest = ofp.get("destination") or m["destination"]
        self.origin = ofp.get("origin") or m["origin"]
        self.alternate = ofp.get("alternate")
        self.planned_cruise = ofp.get("cruise_ft") or 0
        self.phase = "PREFLIGHT"
        self.timeline = []  # (phase, t)
        self.events = []  # dicts: t, kind, text
        self.messages = []  # ACARS log lines
        self.track = []
        self.oooi = {"out": None, "off": None, "on": None, "in": None}
        self.fuel = {"start": None, "out": None, "off": None, "on": None, "in": None}
        self.weights = {"takeoff": None, "landing": None}
        self.db = Debounce()
        self.last = None
        self.start_t = None
        self.max_alt = 0.0
        self.max_g = 1.0
        self.min_g = 1.0
        self.landing = None  # dict
        self.bounces = 0
        self.distance_nm = 0.0
        self.recent_vs = []  # (t, vs) while airborne and low
        self.last_pos_report = 0
        self.last_track_t = 0
        self.overspeed_active = False
        self.taxi_speed_active = False
        self.complete = False
        self.profile = []         # [t_rel, lat, lon, alt, agl, ias, gs, vs, hdg] sampled through the flight
        self.last_profile_t = -1e9
        self.approach_buf = []    # high-rate samples in the last ~2 minutes below 2,500 ft AGL
        self.landing_series = None
        self.landing_capture_until = None
        self.position_jumps = 0
        # PAC ACARS 1.1
        self.practice = bool(booking.get("practice"))   # landing practice: graded, never filed
        self.touchdowns = []      # every touchdown this session (touch-and-goes too): t, rate, ias, g, lat, lon
        self.ride = {"max_bank": 0.0, "steep_s": 0.0, "max_g": 1.0, "min_g": 1.0, "rough": 0}
        self.coach = {}           # SOP reminders already given (once each)
        self.callouts = {}        # approach gates already checked
        self.fuel_checks = {}

    # ---------------------------------------------------------------- logging
    def msg(self, t, text, kind="info"):
        self.messages.append({"t": t, "z": zulu(t), "text": text, "kind": kind})

    def event(self, t, kind, text, penalty=0):
        self.events.append({"t": t, "kind": kind, "text": text, "penalty": penalty})
        self.msg(t, text, "warn" if penalty else "info")

    def set_phase(self, p, t, s: Telemetry):
        if p == self.phase:
            return
        if p == "DESCENT" and not getattr(self, "tod_wx_sent", False):
            self.tod_wx_sent = True
            self.wx_jobs = getattr(self, "wx_jobs", []) + ["tod"]
        self.phase = p
        self.timeline.append({"phase": p, "t": t})
        self.msg(t, f"PHASE {PHASE_LABEL[p].upper()}  ALT {s.alt_ft:,.0f}FT  IAS {s.ias:.0f}KT", "phase")
        self._add_track(s, force=True)

    def _add_track(self, s, force=False):
        if force or s.t - self.last_track_t >= 30:
            self.track.append([round(s.lat, 5), round(s.lon, 5), round(s.alt_ft), self.phase])
            self.last_track_t = s.t

    def _stand_note(self, t, s):
        """At logon: confirm the PAC departure stand, or note that it's held. Information only: where you park is never
        scored, flagged or reviewed, and starting from any stand is fine."""
        import math
        dep, arr = self.booking.get("dep_stand") or {}, self.booking.get("arr_stand") or {}
        parts = []
        if dep.get("stand") and dep.get("lat") is not None and dep.get("icao") == self.origin["icao"]:
            r = math.radians
            dlat, dlon = r(s.lat - dep["lat"]), r(s.lon - dep["lon"])
            h = math.sin(dlat / 2) ** 2 + math.cos(r(s.lat)) * math.cos(r(dep["lat"])) * math.sin(dlon / 2) ** 2
            m = 2 * 6371000 * math.asin(math.sqrt(h))
            if m <= 120:
                parts.append(f"DEP STAND {dep['stand']} {dep['icao']} CONFIRMED")
            else:  # parked somewhere else: PAC holds the stand for them, nothing to put right
                parts.append(f"STAND {dep['stand']} {dep['icao']} IS HELD FOR YOU. ANY STAND IS FINE")
        if arr.get("stand") and arr.get("icao") == self.dest["icao"]:
            parts.append(f"EXPECT ARR STAND {arr['stand']} {arr['icao']} IF FREE")
        if parts:
            self.msg(t, "PAC OCC  " + ". ".join(parts) + ".", "ul")

    # ---------------------------------------------------------------- update
    def update(self, s: Telemetry):
        t = s.t
        if self.start_t is None:
            self.start_t = t
            self.fuel["start"] = s.fuel_lbs
            self.timeline.append({"phase": "PREFLIGHT", "t": t})
            fn = self.booking.get("flight_number", "PAC")
            self.msg(t, f"LOGON {fn}  {self.origin['icao']}-{self.dest['icao']}  FOB {s.fuel_lbs:,.0f}LB", "phase")
            self._stand_note(t, s)
            self._add_track(s, force=True)
        prev = self.last
        db = self.db

        # distance and teleport detection. A single bad sample from the sim (for
        # example a failed read that comes back as 0) is dropped. Only a new
        # position that holds for 3 samples counts as a real jump or slew.
        if prev:
            step_dt = max(1e-3, t - prev.t)
            d = gc_distance_nm(prev.lat, prev.lon, s.lat, s.lon)
            if d / (step_dt / 3600) > 1200 and d > 0.3:
                pj = getattr(self, "pending_jump", [])
                if pj and gc_distance_nm(pj[-1].lat, pj[-1].lon, s.lat, s.lon) / (max(1e-3, t - pj[-1].t) / 3600) > 1200:
                    pj = []
                pj.append(s)
                self.pending_jump = pj
                if len(pj) < 3:
                    self.glitches = getattr(self, "glitches", 0) + 1
                    return
                self.pending_jump = []
                if prev.on_ground and s.on_ground:
                    self._ground_reposition(t, s, d)
                else:
                    self.position_jumps += 1
                    self.event(t, "slew", f"POSITION JUMP {d:.1f}NM DETECTED", penalty=15)
            else:
                self.pending_jump = []
                self.distance_nm += d
        self.last = s
        if getattr(s, "slew", False) and not s.on_ground and not getattr(self, "slew_flagged", False) and self.oooi["off"]:
            self.slew_flagged = True
            self.event(t, "slew", "SLEW MODE USED IN FLIGHT", penalty=15)
        self.max_alt = max(self.max_alt, s.alt_ft)
        if self.phase in AIRBORNE or self.phase == "LANDING":
            self.max_g = max(self.max_g, s.g)
            self.min_g = min(self.min_g, s.g)
        if not s.on_ground and s.agl_ft < 300:
            self.recent_vs.append((t, s.vs_fpm))
            self.recent_vs = [x for x in self.recent_vs if t - x[0] <= 3]

        p = self.phase
        moving = s.gs > 1.0
        if p == "PREFLIGHT":
            # Some aircraft (and some pushback tugs) report ground speed late or keep the parking-brake value set while
            # they roll, so the gate departure also counts when the aircraft has clearly left where it logged on.
            home = getattr(self, "logon_pos", None)
            if home is None:
                home = self.logon_pos = (s.lat, s.lon)
            moved_m = gc_distance_nm(home[0], home[1], s.lat, s.lon) * 1852
            self.moved_m = moved_m
            rolling = s.gs > 2.0 or moved_m > 25
            brake_stuck = s.parking_brake and db.check("brake_stuck", s.on_ground and rolling, t, 5)
            if brake_stuck and not getattr(self, "brake_note", False):
                self.brake_note = True
                self.msg(t, "PARKING BRAKE READS SET BUT THE AIRCRAFT IS MOVING. GATE DEPARTURE LOGGED.", "ul")
            if s.on_ground and (moving or moved_m > 25) and (not s.parking_brake or brake_stuck) and db.check("out", True, t, 2):
                self._out(t, s)
                self.set_phase("TAXI_OUT" if s.engines_running and s.gs > 6 else "PUSHBACK", t, s)
            elif not s.on_ground:
                self.event(t, "procedure", "AIRBORNE WITHOUT GATE DEPARTURE", penalty=10)
                self._out(t, s)
                self._off(t, s)
                self.set_phase("INITIAL_CLIMB", t, s)
        elif p == "PUSHBACK":
            if db.check("taxi", s.engines_running and s.gs > 5, t, 3):
                self.set_phase("TAXI_OUT", t, s)
            elif db.check("roll", s.on_ground and s.ias > 50, t, 1):
                self.set_phase("TAKEOFF", t, s)
        elif p == "TAXI_OUT":
            if db.check("roll", s.on_ground and s.ias > 50, t, 2):
                self.set_phase("TAKEOFF", t, s)
                self.msg(t, f"TAKEOFF ROLL  FOB {s.fuel_lbs:,.0f}LB  GW {s.weight_lbs:,.0f}LB")
        elif p == "TAKEOFF":
            if not s.on_ground and s.agl_ft > 3 and s.gs > 60:
                self.first_air_t = getattr(self, "first_air_t", None) or t
            elif s.on_ground and getattr(self, "first_air_t", None) and not getattr(self, "takeoff_touchback", False):
                self.takeoff_touchback = True  # lifted off, then the wheels touched the runway again
                self.event(t, "takeoff", "WHEELS TOUCHED RUNWAY AFTER LIFTOFF")
            if db.check("lift", not s.on_ground and s.agl_ft > 10, t, 2):
                self._off(t, s)
                self.set_phase("INITIAL_CLIMB", t, s)
            elif db.check("rto", s.on_ground and s.ias < 30, t, 3):
                self.event(t, "rto", "REJECTED TAKEOFF")
                self.takeoff_series = None
                self.set_phase("TAXI_OUT", t, s)
        elif p in AIRBORNE:
            self._airborne(t, s, prev)
        elif p == "LANDING":
            if self.landing and self.oooi["on"] and t - self.oooi["on"] <= 3:
                self.landing["g"] = round(max(self.landing["g"], s.g), 2)
            # a skip back into the air shortly after touchdown, then down again, is a bounce
            if self.oooi["on"] and t - self.oooi["on"] < 15:
                if not s.on_ground and s.agl_ft > 2:
                    self.bounce_air = True
                elif s.on_ground and getattr(self, "bounce_air", False):
                    self.bounce_air = False
                    self.bounces += 1
                    self.event(t, "bounce", f"BOUNCED LANDING  #{self.bounces}", penalty=5)
            if db.check("tng", not s.on_ground and s.agl_ft > 50, t, 3):
                self.event(t, "go_around", "TOUCH AND GO / REJECTED LANDING")
                self.oooi["on"] = None
                self.landing = None
                self.set_phase("GO_AROUND", t, s)
            elif db.check("rolled", s.on_ground and s.gs < 35, t, 4):
                self.set_phase("TAXI_IN", t, s)
        elif p == "TAXI_IN":
            stopped = s.on_ground and s.gs < 1 and not s.engines_running
            braked = db.check("in", stopped and s.parking_brake, t, 5)
            chocked = db.check("in_nobrake", stopped, t, 60)   # engines off and stopped a minute: on block even if the brake can't be read
            if braked or chocked:
                if not braked:
                    self.msg(t, "ENGINES OFF 60 S. PARKING BRAKE NOT READ FROM THE AIRCRAFT: ON BLOCK ANYWAY", "info")
                self._in(t, s)
                self.set_phase("ARRIVED", t, s)
                self.complete = True
            elif db.check("roll2", s.on_ground and s.ias > 60, t, 3):
                if getattr(self, "practice", False):
                    self.msg(t, "PRACTICE  TAKEOFF FOR ANOTHER CIRCUIT")
                    self.oooi["off"] = None
                    self.complete = False
                else:
                    self.event(t, "procedure", "SECOND TAKEOFF ROLL DETECTED", penalty=10)
                self.set_phase("TAKEOFF", t, s)

        # exceedances
        overspeed = not s.on_ground and s.alt_ft < 10000 and s.ias > 260
        if db.check("ovs", overspeed, t, 10) and not self.overspeed_active:
            self.overspeed_active = True
            self.event(t, "overspeed", f"250KT BELOW FL100 EXCEEDED  IAS {s.ias:.0f}", penalty=5)
        # re-arm only after a clear return below the limit, so one long exceedance counts once
        if db.check("ovs_clear", s.on_ground or s.alt_ft >= 10000 or s.ias < 250, t, 30):
            self.overspeed_active = False
        fast_taxi = s.on_ground and self.phase in ("TAXI_OUT", "TAXI_IN") and 30 < s.gs < 50
        if db.check("taxispd", fast_taxi, t, 8) and not self.taxi_speed_active:
            self.taxi_speed_active = True
            self.event(t, "taxi_speed", f"TAXI SPEED {s.gs:.0f}KT ABOVE 30KT LIMIT", penalty=3)
        if db.check("taxi_clear", not s.on_ground or s.gs < 25, t, 20):
            self.taxi_speed_active = False

        self._record_profile(s)
        self._record_takeoff(s)
        self._integrity(s, prev)
        try:
            self._coach_1_1(s, prev)
        except Exception as e:   # coaching must never stop a flight from being tracked
            self.coach_error = str(e)[:200]

        # periodic position report
        if self.phase in AIRBORNE and t - self.last_pos_report >= 600:
            self.last_pos_report = t
            rem = gc_distance_nm(s.lat, s.lon, self.dest["lat"], self.dest["lon"])
            self.msg(t, f"POS {s.lat:+.2f}{s.lon:+.2f}  FL{s.alt_ft / 100:03.0f}  GS{s.gs:.0f}  FOB {s.fuel_lbs:,.0f}  DTG {rem:.0f}NM")
        self._add_track(s)

    def _record_profile(self, s):
        t = s.t
        if not hasattr(self, "profile"):
            self.profile, self.last_profile_t, self.approach_buf = [], -1e9, []
            self.landing_series, self.landing_capture_until = None, None
        low = not s.on_ground and s.agl_ft < 3000
        every = 2 if low else (10 if not s.on_ground else 15)
        if t - self.last_profile_t >= every or getattr(self, "_phase_mark", None) != self.phase:
            self._phase_mark = self.phase
            self.last_profile_t = t
            self.profile.append([round(t - (self.start_t or t), 1), round(s.lat, 5), round(s.lon, 5), round(s.alt_ft),
                                 round(s.agl_ft), round(s.ias), round(s.gs), round(s.vs_fpm), round(s.hdg)])
        sample = [round(t, 2), round(s.agl_ft, 1), round(s.vs_fpm), round(s.ias, 1), round(s.g, 3),
                  round(s.lat, 6), round(s.lon, 6), round(s.hdg, 1), 1 if s.on_ground else 0, round(s.gs, 1)]
        if self.landing_capture_until is not None:
            if t <= self.landing_capture_until:
                self.landing_series.append(sample)
            else:
                self.landing_capture_until = None
        elif not s.on_ground and s.agl_ft < 2500 and (self.phase in ("APPROACH", "DESCENT", "GO_AROUND")
                                                       or (getattr(self, "practice", False) and self.phase in AIRBORNE)):
            if not self.approach_buf or t - self.approach_buf[-1][0] >= 0.25 or s.agl_ft < 300:
                self.approach_buf.append(sample)
            self.approach_buf = [x for x in self.approach_buf if t - x[0] <= 150]

    def _integrity(self, s, prev):
        """Time spent paused in flight and at accelerated sim rate."""
        if not prev:
            return
        dt = max(0.0, min(5.0, s.t - prev.t))
        airborne = not s.on_ground
        if getattr(s, "paused", False) and airborne:
            self.paused_air_s = getattr(self, "paused_air_s", 0.0) + dt
            if self.paused_air_s >= 600 and not getattr(self, "pause_flagged", False):
                self.pause_flagged = True
                self.event(s.t, "integrity", "PAUSED MORE THAN 10 MIN IN FLIGHT")
        rate = getattr(s, "sim_rate", None)
        parked = s.on_ground and (getattr(s, "gs", 0) or 0) < 3    # loading or unloading at the stand: sim rate is fine
        if rate and rate > 1.05 and not getattr(s, "paused", False) and not parked:
            self.accel_s = getattr(self, "accel_s", 0.0) + dt
            self.max_rate = max(getattr(self, "max_rate", 1.0), rate)
            if self.accel_s >= 10 and not getattr(self, "accel_flagged", False):
                self.accel_flagged = True
                self.event(s.t, "integrity", f"SIM RATE {rate:g}X DETECTED")

    def _record_takeoff(self, s):
        """High-rate samples from the start of the takeoff roll up to 1,500 ft."""
        t = s.t
        sample = [round(t, 2), round(s.agl_ft, 1), round(s.vs_fpm), round(s.ias, 1), round(s.g, 3), round(s.lat, 6), round(s.lon, 6),
                  round(s.hdg, 1), 1 if s.on_ground else 0, round(s.gs, 1), None if getattr(s, "pitch", None) is None else round(s.pitch, 2)]
        if self.phase in ("TAXI_OUT", "PUSHBACK"):
            buf = getattr(self, "taxi_buf", [])
            buf.append(sample)
            self.taxi_buf = [x for x in buf if t - x[0] <= 120]
        elif self.phase == "TAKEOFF" and getattr(self, "takeoff_series", None) is None:
            pre = getattr(self, "taxi_buf", [])
            start = 0
            for i in range(len(pre) - 1, -1, -1):
                if pre[i][9] < 15:
                    start = i
                    break
            self.takeoff_series = pre[start:] + [sample]
            self.taxi_buf = []
        elif self.phase in ("TAKEOFF", "INITIAL_CLIMB", "CLIMB") and getattr(self, "takeoff_series", None) is not None \
                and not getattr(self, "takeoff_done", False):
            self.takeoff_series.append(sample)
            if s.agl_ft > 1500 or (self.oooi["off"] and t - self.oooi["off"] > 180):
                self.takeoff_done = True
        if self.phase == "TAXI_OUT" and getattr(self, "takeoff_series", None) is not None and not self.oooi["off"]:
            self.takeoff_series = None  # rejected takeoff: start again on the next roll

    def _airborne(self, t, s, prev):
        db, p = self.db, self.phase
        contact = db.check("td", s.on_ground, t, 0.5)
        just_off = p == "INITIAL_CLIMB" and self.oooi["off"] and t - self.oooi["off"] < 30 and s.gs > 60
        # A bounce's first contact can be shorter than the touchdown confirmation. Remember it provisionally:
        # if the aircraft lifts off again and comes back down, it was a bounce and the first contact sets the rate.
        if not just_off and p in ("APPROACH", "DESCENT", "GO_AROUND"):
            pc = getattr(self, "pending_contact", None)
            if s.on_ground and not pc:
                last = self.recent_vs[-1][0] if self.recent_vs else t
                vs_c = [v for tt, v in self.recent_vs if last - tt <= 0.6] or [s.vs_fpm]
                self.pending_contact = {"t": t, "rate": -abs(min(vs_c)), "ias": s.ias, "lat": s.lat, "lon": s.lon, "air_again": False}
            elif pc and not s.on_ground and s.agl_ft > 2:
                if t - pc["t"] < 3:
                    pc["air_again"] = True
                else:
                    self.pending_contact = None
        if contact and just_off and not getattr(self, "takeoff_touchback", False):
            self.takeoff_touchback = True  # wheels back on the runway during rotation: part of the takeoff, not a landing
            self.event(t, "takeoff", "WHEELS TOUCHED RUNWAY AFTER LIFTOFF")
        if contact and not just_off:
            self._touchdown(t, s)
            return
        dist_dest = gc_distance_nm(s.lat, s.lon, self.dest["lat"], self.dest["lon"])
        climbing, descending = s.vs_fpm > 500, s.vs_fpm < -500
        level = abs(s.vs_fpm) < 400
        cruise_floor = self.planned_cruise * 0.9 if self.planned_cruise else 0

        if p == "INITIAL_CLIMB":
            if s.agl_ft > 1500:
                self.set_phase("CLIMB", t, s)
        elif p == "CLIMB":
            near_plan = s.alt_ft >= cruise_floor if cruise_floor else s.alt_ft > 10000
            if db.check("lvl", level and near_plan, t, 60) or db.check("lvl_long", level and s.alt_ft > 10000, t, 180):
                self.msg(t, f"TOP OF CLIMB  FL{s.alt_ft / 100:03.0f}  FOB {s.fuel_lbs:,.0f}LB")
                self.set_phase("CRUISE", t, s)
            elif db.check("desc", descending and s.alt_ft > 3000, t, 45):
                self.set_phase("DESCENT", t, s)
        elif p == "CRUISE":
            if db.check("step", climbing, t, 30):
                self.msg(t, "STEP CLIMB")
                self.set_phase("CLIMB", t, s)
            elif db.check("tod", descending, t, 20):
                self.msg(t, f"TOP OF DESCENT  DTG {dist_dest:.0f}NM  FOB {s.fuel_lbs:,.0f}LB")
                self.set_phase("DESCENT", t, s)
        elif p == "DESCENT":
            if s.agl_ft < 2500 or (s.agl_ft < 4000 and (dist_dest < 20 or s.gear_down)):
                self.set_phase("APPROACH", t, s)
            elif db.check("reclimb", climbing and s.alt_ft > 10000, t, 60):
                self.set_phase("CLIMB", t, s)
        elif p == "APPROACH":
            if db.check("ga", climbing and s.agl_ft < 3000, t, 4):
                self.event(t, "go_around", f"GO-AROUND  {s.agl_ft:.0f}FT AGL")
                self.set_phase("GO_AROUND", t, s)
        elif p == "GO_AROUND":
            if db.check("reapp", s.vs_fpm < -300, t, 20):
                self.set_phase("APPROACH", t, s)
            elif s.agl_ft > 6000:
                self.set_phase("CLIMB", t, s)

    def _ground_reposition(self, t, s, d):
        """GSX or slew move on the ground, e.g. gate to runway or runway to stand."""
        allowed = getattr(self, "allow_reposition", True)
        self.repositions = getattr(self, "repositions", 0) + 1
        if self.phase == "PREFLIGHT":
            self.logon_pos = (s.lat, s.lon)       # moved to a new stand: measure the push from there
        if allowed:
            self.event(t, "reposition", f"GROUND REPOSITION {d:.1f}NM")
        else:
            self.event(t, "reposition", f"GROUND REPOSITION {d:.1f}NM NOT PERMITTED", penalty=15)
        if self.phase in ("PREFLIGHT", "PUSHBACK"):
            if not self.oooi["out"]:
                self._out(t, s)
            self.set_phase("TAXI_OUT", t, s)
        elif self.phase in ("LANDING", "TAXI_IN"):
            self.set_phase("TAXI_IN", t, s)

    # ---------------------------------------------------------------- PAC ACARS 1.1: coaching (messages only, never scored)
    def _once(self, store, key):
        d = getattr(self, store, None)
        if d is None:
            d = {}
            setattr(self, store, d)
        if d.get(key):
            return False
        d[key] = True
        return True

    def _ul(self, t, text):
        self.msg(t, text, "ul")       # an uplink: chimes and lights MSG

    def _coach_1_1(self, s, prev):
        t, p, db = s.t, self.phase, self.db
        dt = max(0.0, min(5.0, t - prev.t)) if prev else 0.0
        airborne = not s.on_ground

        # smooth ride: bank, steep turns and rough handling (for live animals and fragile freight)
        ride = getattr(self, "ride", None)
        if ride is None:
            ride = self.ride = {"max_bank": 0.0, "steep_s": 0.0, "max_g": 1.0, "min_g": 1.0, "rough": 0}
        if airborne and p in AIRBORNE:
            if s.bank is not None:
                ride["max_bank"] = round(max(ride["max_bank"], abs(s.bank)), 1)
                if abs(s.bank) > 30:
                    ride["steep_s"] = round(ride["steep_s"] + dt, 1)
            ride["max_g"] = round(max(ride["max_g"], s.g), 2)
            ride["min_g"] = round(min(ride["min_g"], s.g), 2)
            if (s.g > 1.5 or s.g < 0.5) and db.check("rough", True, t, 0.5) and self._once("callouts", f"rough{int(t // 60)}"):
                ride["rough"] += 1
        else:
            db.check("rough", False, t, 0.5)

        # aircraft check: the loaded aircraft should match the booked type
        if not self.coach.get("ac_checked") and s.num_engines and p == "PREFLIGHT":
            self.coach["ac_checked"] = True
            want = expected_engines(self.booking)
            if want and s.num_engines != want:
                self._ul(t, f"PAC OCC  LOADED AIRCRAFT HAS {s.num_engines} ENGINES. THE {self.booking.get('aircraft', 'BOOKED TYPE')} "
                            f"HAS {want}. CHECK YOU LOADED THE RIGHT AIRCRAFT")
        ac_max = (self.booking.get("aircraft_info") or {}).get("mtow_lbs")
        if ac_max and s.weight_lbs > ac_max * 1.08 and p in ("PREFLIGHT", "PUSHBACK", "TAXI_OUT") and self._once("coach", "mtow"):
            self._ul(t, f"PAC OCC  GROSS WEIGHT {s.weight_lbs:,.0f}LB IS ABOVE THE {ac_max:,.0f}LB MAX TAKEOFF WEIGHT. CHECK FUEL AND PAYLOAD")

        # SOP coach: friendly reminders from PAC's standard procedures (only when the aircraft reports its lights)
        if getattr(self, "sop_coach", True):
            if s.beacon is False:
                if s.engines_running and self._once("coach", "beacon_eng"):
                    self.msg(t, "PAC SOP  BEACON SHOULD BE ON BEFORE ENGINE START", "warn")
                elif p == "PUSHBACK" and self._once("coach", "beacon_push"):
                    self.msg(t, "PAC SOP  BEACON ON BEFORE PUSHBACK", "warn")
            if p == "TAKEOFF" and s.ias > 30:
                if s.landing_lights is False and self._once("coach", "ldg_to"):
                    self.msg(t, "PAC SOP  LANDING LIGHTS ON FOR TAKEOFF", "warn")
                if s.strobe is False and self._once("coach", "strobe_to"):
                    self.msg(t, "PAC SOP  STROBES ON WHEN ENTERING THE RUNWAY", "warn")
            if db.check("ldg_high", airborne and s.landing_lights is True and s.alt_ft > 11000 and p in ("CLIMB", "CRUISE"), t, 120) \
                    and self._once("coach", "ldg_high"):
                self.msg(t, "PAC SOP  LANDING LIGHTS OFF ABOVE 10,000 FT", "info")
            if db.check("ldg_low", airborne and s.landing_lights is False and s.alt_ft < 9500 and p in ("DESCENT", "APPROACH"), t, 60) \
                    and self._once("coach", "ldg_low"):
                self.msg(t, "PAC SOP  LANDING LIGHTS ON BELOW 10,000 FT", "warn")
            if db.check("strobe_taxi", p == "TAXI_IN" and s.strobe is True and s.gs > 3, t, 45) and self._once("coach", "strobe_taxi"):
                self.msg(t, "PAC SOP  STROBES OFF AFTER VACATING THE RUNWAY", "info")

        # stabilized approach gates at 1,000 and 500 ft above the ground
        on_final = p == "APPROACH" or (getattr(self, "practice", False) and p in AIRBORNE and s.gear_down)
        if on_final and airborne and s.vs_fpm < -100:
            buf = [x for x in getattr(self, "approach_buf", []) if t - x[0] <= 12]
            for gate in (1000, 500):
                key = f"gate{gate}_{len(getattr(self, 'touchdowns', []))}"
                if s.agl_ft <= gate and (prev and prev.agl_ft > gate) and self._once("callouts", key):
                    issues = []
                    if not s.gear_down:
                        issues.append("GEAR UP")
                    if gate == 1000 and s.flaps < 0.3:
                        issues.append("FLAPS NOT SET")
                    recent = [x[2] for x in buf if t - x[0] <= 6] or [s.vs_fpm]
                    if max(recent) < -1000:
                        issues.append(f"SINK {abs(max(recent)):,.0f}FPM")
                    spd = [x[3] for x in buf]
                    if len(spd) >= 4 and max(spd) - min(spd) > 15:
                        issues.append(f"SPEED UNSTABLE {min(spd):.0f}-{max(spd):.0f}KT")
                    if issues:
                        self._ul(t, f"UNSTABLE AT {gate}FT  {'  '.join(issues)}  CONSIDER A GO-AROUND")
                    elif gate == 1000:
                        self.msg(t, "STABLE AT 1000FT")

        # fuel checks against the SimBrief plan at top of climb and top of descent
        ofp = self.booking.get("ofp") or {}
        trip, block = ofp.get("trip_fuel_lbs"), ofp.get("block_fuel_lbs")
        route_nm = ofp.get("distance_nm") or 0
        if trip and block and route_nm and airborne:
            for when, ph in (("TOC", "CRUISE"), ("TOD", "DESCENT")):
                if p == ph and self._once("fuel_checks", when):
                    dtg = gc_distance_nm(s.lat, s.lon, self.dest["lat"], self.dest["lon"])
                    est_arrival = s.fuel_lbs - trip * min(1.0, dtg / route_nm)
                    plan_arrival = block - trip - (ofp.get("taxi_fuel_lbs") or 0)
                    diff = est_arrival - plan_arrival
                    line = f"FUEL CHECK {when}  FOB {s.fuel_lbs:,.0f}LB  EST ARRIVAL {est_arrival:,.0f}LB  PLAN {plan_arrival:,.0f}LB"
                    reserve = ofp.get("reserve_fuel_lbs") or 0
                    if reserve and est_arrival < reserve:
                        self._ul(t, "PAC OCC  " + line + "  BELOW RESERVE: CONSIDER A FUEL STOP OR YOUR ALTERNATE")
                    elif abs(diff) >= 1000:
                        self.msg(t, line + f"  ({'+' if diff > 0 else ''}{diff:,.0f}LB VS PLAN)")
                    else:
                        self.msg(t, line + "  ON PLAN")

        # top of descent reminder: about 3 nm per 1,000 ft to lose, plus 10 nm to slow down
        if p == "CRUISE" and airborne:
            dtg = gc_distance_nm(s.lat, s.lon, self.dest["lat"], self.dest["lon"])
            elev = self.dest.get("elevation") or 0
            tod_nm = max(0.0, (s.alt_ft - elev) / 1000 * 3 + 10)
            if dtg <= tod_nm + 20 and self._once("callouts", "tod"):
                self._ul(t, f"PAC OCC  TOP OF DESCENT IN ABOUT {max(0, dtg - tod_nm):.0f}NM. START DOWN AT ~{tod_nm:.0f}NM FROM "
                            f"{self.dest.get('icao', 'DEST')}. CHECK ATIS, BRIEF THE APPROACH, SET VREF AND MINIMUMS")
                self.wx_jobs = getattr(self, "wx_jobs", []) + ["tod"]
                self.tod_wx_sent = True

        # live dispatch: occasional realistic messages from PAC Operations on longer flights
        if p == "CRUISE" and self.oooi.get("off") and not getattr(self, "practice", False):
            self._dispatch_events(t, s)

    def _dispatch_events(self, t, s):
        import random
        sent = getattr(self, "dispatch_sent", [])
        self.dispatch_sent = sent
        flown_min = (t - self.oooi["off"]) / 60
        est = (self.booking.get("ofp") or {}).get("est_enroute_min") or (self.booking.get("mission") or {}).get("target_block_min") or 0
        if est < 75 or len(sent) >= 2 or flown_min < 25 or t - getattr(self, "dispatch_last_t", 0) < 1800:
            return
        if random.Random(f"{self.booking.get('flight_number')}-{int(t // 600)}").random() > 0.35:
            self.dispatch_last_t = t - 1200   # look again in about 10 minutes
            return
        m = self.booking.get("mission") or {}
        dest = self.dest.get("icao", "DEST")
        pool = [
            ("eta", f"PAC OCC  {(m.get('cargo') or 'CARGO').upper()[:40]} CONSIGNEE REQUESTS AN UPDATED ETA FOR {dest}. "
                    f"SEND IT FROM THE ETA TAB WHEN ABLE"),
            ("ramp", f"PAC OCC  {dest} RAMP REPORTS A BUSY CARGO APRON ON ARRIVAL. EXPECT A SHORT WAIT FOR MARSHALLING"),
            ("mx", "PAC MX  PLEASE WRITE UP ANY DEFECTS FROM THIS SECTOR ON THE FAULT TAB SO MAINTENANCE CAN PLAN THE TURN"),
            ("load", f"PAC LOAD CONTROL  FINAL LOAD FIGURES CONFIRMED. NO LAST-MINUTE CHANGES FOR {dest}"),
        ]
        if (m.get("priority") or "").lower() in ("high", "critical") or m.get("urgent"):
            pool.append(("prio", f"PAC OCC  CUSTOMER CONFIRMS PRIORITY HANDLING AT {dest}. A TRUCK WILL MEET THE AIRCRAFT ON STAND"))
        pool = [x for x in pool if x[0] not in sent]
        if not pool:
            return
        kind, text = random.Random(f"{self.booking.get('flight_number')}-{len(sent)}").choice(pool)
        sent.append(kind)
        self.dispatch_last_t = t
        self._ul(t, text)

    # ---------------------------------------------------------------- OOOI
    def _out(self, t, s):
        self.oooi["out"] = t
        self.fuel["out"] = s.fuel_lbs
        self.wx_jobs = getattr(self, "wx_jobs", []) + ["out"]
        self.msg(t, f"OUT {zulu(t)}  FOB {s.fuel_lbs:,.0f}LB", "oooi")

    def _off(self, t, s):
        self.oooi["off"] = t
        self.last_pos_report = t  # first position report 10 min after takeoff
        self.fuel["off"] = s.fuel_lbs
        self.weights["takeoff"] = s.weight_lbs
        self.msg(t, f"OFF {zulu(t)}  TOW {s.weight_lbs:,.0f}LB", "oooi")

    def _touchdown(self, t, s):
        pc = getattr(self, "pending_contact", None)
        self.pending_contact = None
        if pc and pc.get("air_again") and not self.oooi["on"]:
            # bounced: the landing counts from the first contact, then this is bounce #1
            self._touchdown_at(pc["t"], s, forced=pc)
            self.bounces += 1
            self.event(t, "bounce", f"BOUNCED LANDING  #{self.bounces}", penalty=5)
            return
        self._touchdown_at(t, s)

    def _touchdown_at(self, t, s, forced=None):
        # Use the vertical speed in the last ~0.6 s before contact. A longer window reaches back
        # before the flare and reports the approach descent rate (~700 fpm) instead of the touchdown.
        last = self.recent_vs[-1][0] if self.recent_vs else t
        vs_candidates = [v for tt, v in self.recent_vs if last - tt <= 0.6] or [s.vs_fpm]
        vs_rate = min(vs_candidates)
        rate = vs_rate
        # the sim's own touchdown value is best, unless it looks stale
        if s.touchdown_fpm and abs(-abs(s.touchdown_fpm) - vs_rate) < 400:
            rate = s.touchdown_fpm
        rate = -abs(rate)
        lat, lon, ias = s.lat, s.lon, s.ias
        if forced:  # a bounce: the first contact counts
            rate, lat, lon, ias = forced["rate"], forced["lat"], forced["lon"], forced["ias"]
        if self.oooi["on"] and t - self.oooi["on"] < 15:
            self.bounces += 1
            self.event(t, "bounce", f"BOUNCED LANDING  #{self.bounces}", penalty=5)
        else:
            self.oooi["on"] = t
            self.fuel["on"] = s.fuel_lbs
            self.weights["landing"] = s.weight_lbs
            dist_dest = gc_distance_nm(lat, lon, self.dest["lat"], self.dest["lon"])
            self.landing = {"rate_fpm": round(rate), "g": round(s.g, 2),
                            "ias": round(ias), "lat": lat, "lon": lon, "dist_dest_nm": round(dist_dest, 1)}
            if not hasattr(self, "touchdowns"):
                self.touchdowns = []
            self.touchdowns.append({"t": t, "rate_fpm": round(rate), "ias": round(ias), "g": round(s.g, 2), "lat": lat, "lon": lon,
                                    "hdg": round(s.hdg, 1), "n": len(self.touchdowns) + 1})
            self.msg(t, f"ON {zulu(t)}  TOUCHDOWN {rate:.0f}FPM  IAS {ias:.0f}KT  FOB {s.fuel_lbs:,.0f}LB", "oooi")
            buf = [x for x in getattr(self, "approach_buf", []) if x[0] < t]
            self.landing_series = buf + [
                [round(t, 2), 0.0, round(rate), round(ias, 1), round(s.g, 3), round(lat, 6), round(lon, 6), round(s.hdg, 1), 1, round(s.gs, 1)]]
            self.landing_touchdown_t = t
            self.wx_jobs = getattr(self, "wx_jobs", []) + ["landing"]
            self.landing_capture_until = t + 45
            self.approach_buf = []
        self.recent_vs = []
        self.set_phase("LANDING", t, s)

    def _in(self, t, s):
        self.oooi["in"] = t
        self.fuel["in"] = s.fuel_lbs
        self.msg(t, f"IN {zulu(t)}  FOB {s.fuel_lbs:,.0f}LB  FLIGHT COMPLETE", "oooi")

    # ---------------------------------------------------------------- export for the website
    EXPORT_SKIP = {"booking", "db"}

    def export(self):
        """The whole flight record as plain JSON, so the PAC ACARS app can hand it to the website for scoring."""
        out = {}
        for k, v in self.__dict__.items():
            if k in self.EXPORT_SKIP or k.startswith("_"):
                continue
            if isinstance(v, Telemetry):
                v = {"__telemetry__": v.to_dict()}
            elif isinstance(v, (set, tuple)):
                v = list(v)
            out[k] = v
        return out

    @classmethod
    def from_export(cls, booking, data):
        rec = cls(booking)
        fields = set(Telemetry.__dataclass_fields__)
        for k, v in (data or {}).items():
            if k in cls.EXPORT_SKIP:
                continue
            if isinstance(v, dict) and "__telemetry__" in v:
                v = Telemetry(**{kk: vv for kk, vv in v["__telemetry__"].items() if kk in fields})
            elif k == "wx_sent" and isinstance(v, dict):
                v = {kk: tuple(vv) for kk, vv in v.items()}
            setattr(rec, k, v)
        return rec

    # ---------------------------------------------------------------- views
    def waiting_for(self):
        """Before the gate departure: what PAC ACARS is waiting to see, so a pilot can tell why nothing's happening."""
        s = self.last
        if self.phase == "TAXI_IN":
            if s and s.on_ground and s.gs < 1 and not s.engines_running and not s.parking_brake:
                return "Engines off. Set the parking brake, or wait a minute: PAC ACARS then puts you on block by itself."
            return "To finish the flight: stop at the stand, set the parking brake and shut down all engines. Keep PAC ACARS open until it shows On block."
        if self.phase != "PREFLIGHT":
            return None
        if not s:
            return "Waiting for the first data from the simulator."
        if not s.on_ground:
            return None
        if s.parking_brake and s.gs <= 1.0:
            return "Ready. Release the parking brake and push back or taxi: the flight starts when the aircraft moves."
        if s.gs <= 1.0:
            return f"Ready. Parking brake off; waiting for the aircraft to move (ground speed {s.gs:.1f} kt)."
        return "Moving: logging the gate departure…"

    def status(self):
        s = self.last
        live = s.to_dict() if s else None
        dtg = None
        if s:
            dtg = gc_distance_nm(s.lat, s.lon, self.dest["lat"], self.dest["lon"])
        elapsed = (s.t - self.oooi["out"]) if (s and self.oooi["out"]) else 0
        return {
            "phase": self.phase, "phase_label": PHASE_LABEL[self.phase], "waiting_for": self.waiting_for(),
            "timeline": self.timeline, "oooi": self.oooi, "live": live,
            "dtg_nm": dtg, "distance_nm": round(self.distance_nm, 1),
            "block_elapsed_s": elapsed, "messages": self.messages[-120:], "msg_count": len(self.messages),
            "events": self.events, "track": self.track[-2000:],
            "landing": self.landing, "complete": self.complete,
            "fuel_used": (self.fuel["out"] - s.fuel_lbs) if (s and self.fuel["out"] is not None) else 0,
        }


class TrackerThread(threading.Thread):
    def __init__(self, source, recorder: FlightRecorder, interval=0.25, check_origin=True, on_save=None, on_wx=None, on_tick=None):
        super().__init__(daemon=True)
        self.source = source
        self.rec = recorder
        self.interval = interval
        self.check_origin = check_origin
        self.on_save = on_save
        self.on_wx = on_wx
        self.on_tick = on_tick
        self.last_tick = 0.0
        self.stop_flag = threading.Event()
        self.error = None
        self.connected = False
        self.lock = threading.Lock()

    def _origin_ok(self, s):
        o = self.rec.origin
        d = gc_distance_nm(s.lat, s.lon, o["lat"], o["lon"])
        if d > 5:
            self.error = f"You are {d:.0f} nm from {o['icao']}. Load the aircraft at a stand at {o['icao']} and start ACARS again."
            return False
        if not s.on_ground:
            self.error = "Start ACARS on the ground at your stand, before pushback."
            return False
        return True

    def run(self):
        # Keep trying until the simulator answers (X-Plane still loading, a flight not yet started): the pilot never has
        # to press Start again, and the message says what PAC ACARS is waiting for.
        tries = 0
        while not self.stop_flag.is_set():
            try:
                self.source.connect()
                self.connected, self.error = True, None
                break
            except SourceError as e:
                tries += 1
                self.error = f"{e} Still trying (attempt {tries})…"
            except Exception as e:  # never die silently
                tries += 1
                self.error = f"Could not connect to {self.source.name}: {e}. Still trying (attempt {tries})…"
            self.stop_flag.wait(3)
        if self.stop_flag.is_set():
            return
        misses, last_save, last_online = 0, time.time(), 0.0
        while not self.stop_flag.is_set():
            try:
                s = self.source.read()
                if s is None or (abs(s.lat) < 1e-6 and abs(s.lon) < 1e-6):
                    raise ValueError("incomplete sample")
                if self.check_origin:
                    if not self._origin_ok(s):
                        break
                    self.check_origin = False
                with self.lock:
                    try:
                        self.rec.update(s)
                    except Exception as e:     # a fault in PAC ACARS itself, not the sim: say so at once
                        import traceback
                        if not getattr(self, "update_fault_logged", False):
                            self.update_fault_logged = True
                            traceback.print_exc()
                        self.error = f"PAC ACARS couldn't process the simulator data ({e.__class__.__name__}: {e}). Please report this."
                        raise
                    jobs = getattr(self.rec, "wx_jobs", None)
                    if jobs:
                        self.rec.wx_jobs = []
                    if time.time() - last_online > 180 and self.rec.oooi.get("out") and not self.rec.complete:
                        last_online = time.time()
                        jobs = (jobs or []) + ["online"]
                if jobs and self.on_wx:
                    threading.Thread(target=self.on_wx, args=(self.rec, list(jobs), self.lock), daemon=True).start()
                if self.on_tick and self.rec.phase in AIRBORNE and time.time() - self.last_tick > 300:
                    self.last_tick = time.time()
                    threading.Thread(target=self.on_tick, args=(self.rec, self.lock), daemon=True).start()
                misses = 0
                self.connected = True
                self.error = None
                self.last_sample = time.time()
            except Exception as e:  # keep the flight alive through sim hiccups
                misses += 1
                if misses > 40:
                    self.connected = False
                    self.error = f"Lost connection to {self.source.name}: {e}. Tracking resumes when data returns."
            if self.on_save and (time.time() - last_save > 10 or self.rec.complete):
                last_save = time.time()
                with self.lock:
                    self.on_save(self.rec)
            if self.rec.complete:
                break
            low = self.rec.last and not self.rec.last.on_ground and self.rec.last.agl_ft < 300
            time.sleep(0.1 if low else self.interval)
        if self.on_save and self.rec.start_t:
            with self.lock:
                self.on_save(self.rec)
        self.source.close()

    def stop(self):
        self.stop_flag.set()
