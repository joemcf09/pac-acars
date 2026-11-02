"""Telemetry sources for the PAC ACARS tracker.

Every source returns a Telemetry snapshot from read(). Units are fixed:
feet, knots, feet per minute, pounds, degrees. `t` is simulation-clock
epoch seconds so a time-compressed demo flight still produces correct
durations.
"""
from __future__ import annotations

import math
import socket
import struct
import time
from dataclasses import dataclass, asdict

KG_TO_LB = 2.20462
M_TO_FT = 3.28084


def altimeter_alt(indicated, true_ft):
    """The altitude the pilot sees: the altimeter reading (on STD that is the flight level, so FL360 reads
    36,000 even on a warm day when the aircraft is really higher). Falls back to the true altitude if the
    aircraft doesn't drive the simulator's own altimeter."""
    if indicated is None or abs(indicated - true_ft) > 5000:
        return true_ft
    return indicated


@dataclass
class Telemetry:
    t: float
    lat: float
    lon: float
    alt_ft: float
    agl_ft: float
    ias: float
    gs: float
    vs_fpm: float
    hdg: float
    on_ground: bool
    engines_running: bool
    parking_brake: bool
    fuel_lbs: float
    weight_lbs: float
    gear_down: bool
    flaps: float
    g: float
    touchdown_fpm: float | None = None
    slew: bool = False
    pitch: float | None = None      # degrees, positive nose up
    sim_rate: float | None = None   # 1.0 = real time
    paused: bool = False
    true_alt_ft: float | None = None  # height above sea level; alt_ft is the altimeter reading

    def to_dict(self):
        return asdict(self)


def gc_distance_nm(lat1, lon1, lat2, lon2):
    r = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def gc_interpolate(lat1, lon1, lat2, lon2, f):
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
    if d == 0:
        return lat1, lon1
    a = math.sin((1 - f) * d) / math.sin(d)
    b = math.sin(f * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


class SourceError(Exception):
    pass


# --------------------------------------------------------------------------
# Microsoft Flight Simulator 2020 / 2024 (and P3D via SimConnect)
# --------------------------------------------------------------------------
class MSFSSource:
    """Reads MSFS through SimConnect. Every variable is requested with an explicit
    unit so the values never depend on the Python library's defaults."""
    name = "MSFS"
    VARS = {
        "lat": ("PLANE LATITUDE", "degrees"),
        "lon": ("PLANE LONGITUDE", "degrees"),
        "alt": ("PLANE ALTITUDE", "feet"),
        "ind_alt": ("INDICATED ALTITUDE", "feet"),
        "agl": ("PLANE ALT ABOVE GROUND", "feet"),
        "ias": ("AIRSPEED INDICATED", "knots"),
        "gs": ("GROUND VELOCITY", "knots"),
        "vs": ("VERTICAL SPEED", "feet per minute"),
        "hdg": ("PLANE HEADING DEGREES TRUE", "degrees"),
        "on_ground": ("SIM ON GROUND", "bool"),
        "eng1": ("GENERAL ENG COMBUSTION:1", "bool"),
        "eng2": ("GENERAL ENG COMBUSTION:2", "bool"),
        "eng3": ("GENERAL ENG COMBUSTION:3", "bool"),
        "eng4": ("GENERAL ENG COMBUSTION:4", "bool"),
        "pbrake": ("BRAKE PARKING POSITION", "bool"),
        "fuel": ("FUEL TOTAL QUANTITY WEIGHT", "pounds"),
        "weight": ("TOTAL WEIGHT", "pounds"),
        "gear": ("GEAR HANDLE POSITION", "bool"),
        "flaps": ("FLAPS HANDLE PERCENT", "percent over 100"),
        "g": ("G FORCE", "gforce"),
        "td": ("PLANE TOUCHDOWN NORMAL VELOCITY", "feet per minute"),
        "slew": ("IS SLEW ACTIVE", "bool"),
        "pitch": ("PLANE PITCH DEGREES", "degrees"),
        "rate": ("SIMULATION RATE", "number"),
        "abstime": ("ABSOLUTE TIME", "seconds"),
    }
    CORE = ("lat", "lon", "alt", "ias", "gs", "vs", "on_ground")

    def __init__(self):
        self.sm = None
        self.req = {}
        self.cache = {}
        self._clock = None  # (wall, sim absolute time) to detect pause

    def connect(self):
        try:
            from SimConnect import SimConnect  # pip install SimConnect
            try:
                from SimConnect import Request
            except ImportError:
                from SimConnect.RequestList import Request
        except ImportError as e:
            raise SourceError("The SimConnect Python package is not installed. Run: pip install SimConnect") from e
        try:
            self.sm = SimConnect()
        except Exception as e:  # sim not running
            raise SourceError("Could not reach Microsoft Flight Simulator. Start the sim and load into the cockpit first.") from e
        self.req = {k: Request((n.encode(), u.encode()), self.sm, _time=150) for k, (n, u) in self.VARS.items()}

    def _v(self, k):
        """Latest value, or the last good one if this read failed (up to 2 s old)."""
        try:
            val = self.req[k].value
        except Exception:
            val = None
        now = time.time()
        if val is not None:
            self.cache[k] = (val, now)
            return val
        old = self.cache.get(k)
        return old[0] if old and now - old[1] < 2.0 else None

    def read(self):
        v = {k: self._v(k) for k in self.VARS}
        if any(v[k] is None for k in self.CORE):
            return None  # no fresh data for a core value; the tracker skips it
        num = lambda k, d=0.0: d if v[k] is None else float(v[k])
        td = v["td"]
        # pause: the simulator clock stops while the wall clock keeps going
        now = time.time()
        paused = False
        if v["abstime"] is not None:
            last = getattr(self, "_abs", None)
            if last and now - last[1] >= 1.5:
                paused = abs(float(v["abstime"]) - last[0]) < 0.2
            if not last or now - last[1] >= 1.5:
                self._abs = (float(v["abstime"]), now)
                self._paused = paused
            paused = getattr(self, "_paused", False)
        return Telemetry(
            t=time.time(),
            lat=num("lat"), lon=num("lon"), agl_ft=num("agl", num("alt")),
            alt_ft=altimeter_alt(None if v["ind_alt"] is None else float(v["ind_alt"]), num("alt")), true_alt_ft=num("alt"),
            ias=max(0.0, num("ias")), gs=max(0.0, num("gs")), vs_fpm=num("vs"), hdg=num("hdg") % 360,
            on_ground=bool(v["on_ground"]),
            engines_running=any(bool(v[f"eng{i}"]) for i in range(1, 5)),
            parking_brake=bool(v["pbrake"]), fuel_lbs=num("fuel"), weight_lbs=num("weight"),
            gear_down=bool(v["gear"]) if v["gear"] is not None else True,
            flaps=num("flaps"), g=num("g", 1.0),
            touchdown_fpm=-abs(float(td)) if td else None,
            slew=bool(v["slew"]),
            pitch=-num("pitch") if v["pitch"] is not None else None,
            sim_rate=num("rate", 1.0) or 1.0, paused=paused,
        )

    def close(self):
        try:
            if self.sm:
                self.sm.exit()
        except Exception:
            pass


# --------------------------------------------------------------------------
# X-Plane 11 / 12 over the built-in UDP interface (no plugin required)
# --------------------------------------------------------------------------
class XPlaneSource:
    name = "X-Plane"
    DATAREFS = [
        ("lat", "sim/flightmodel/position/latitude"),
        ("lon", "sim/flightmodel/position/longitude"),
        ("elev_m", "sim/flightmodel/position/elevation"),
        ("agl_m", "sim/flightmodel/position/y_agl"),
        ("ias", "sim/flightmodel/position/indicated_airspeed"),
        ("gs_ms", "sim/flightmodel/position/groundspeed"),
        ("vs_fpm", "sim/flightmodel/position/vh_ind_fpm"),
        ("hdg", "sim/flightmodel/position/psi"),
        ("on_ground", "sim/flightmodel/failures/onground_any"),
        ("eng1", "sim/flightmodel/engine/ENGN_running[0]"),
        ("eng2", "sim/flightmodel/engine/ENGN_running[1]"),
        ("eng3", "sim/flightmodel/engine/ENGN_running[2]"),
        ("eng4", "sim/flightmodel/engine/ENGN_running[3]"),
        ("pbrake", "sim/cockpit2/controls/parking_brake_ratio"),
        ("pbrake2", "sim/flightmodel/controls/parkbrake"),     # some add-on aircraft only drive this one
        ("fuel_kg", "sim/flightmodel/weight/m_fuel_total"),
        ("weight_kg", "sim/flightmodel/weight/m_total"),
        ("gear", "sim/cockpit2/controls/gear_handle_down"),
        ("flaps", "sim/cockpit2/controls/flap_ratio"),
        ("g", "sim/flightmodel/forces/g_nrml"),
        ("pitch", "sim/flightmodel/position/theta"),
        ("simspeed", "sim/time/sim_speed"),
        ("timeaccel", "sim/time/ground_speed"),   # X-Plane's time acceleration (1x, 2x, 4x...)
        ("paused", "sim/time/paused"),
        ("ind_alt_ft", "sim/cockpit2/gauges/indicators/altitude_ft_pilot"),   # keep last: indexes are fixed
    ]

    def __init__(self, host="127.0.0.1", port=49000, freq=20):
        self.addr = (host, port)
        self.freq = freq
        self.sock = None
        self.values = {}
        self.last_rx = 0.0
        self.last_sub = 0.0

    def _subscribe(self, freq):
        self.last_sub = time.time()
        for idx, (_, ref) in enumerate(self.DATAREFS):
            msg = b"RREF\x00" + struct.pack("<ii400s", freq, idx, ref.encode().ljust(400, b"\x00"))
            try:
                self.sock.sendto(msg, self.addr)
            except OSError:
                pass

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        for attempt in range(3):
            self._subscribe(self.freq)
            if self._pump(wait=3.0):
                return
        self.close()
        raise SourceError(f"No data from X-Plane at {self.addr[0]}:{self.addr[1]}. Load a flight in X-Plane first. "
                          "In X-Plane 12, check Settings › Network and make sure incoming connections are allowed "
                          "and the UDP port is 49000.")

    def _pump(self, wait=0.0):
        """Drains every waiting packet without blocking. Waits up to `wait` seconds for the first one.
        Returns True if any data arrived."""
        deadline = time.time() + wait
        got = False
        for _ in range(500):  # hard cap so a flood of packets can never stall the tracker
            try:
                self.sock.settimeout(0.0 if got else max(0.0, deadline - time.time()))
                data, _ = self.sock.recvfrom(8192)
            except (socket.timeout, BlockingIOError):
                break
            except OSError:
                # Windows reports "connection reset" when nothing is listening on the port yet
                if not got and time.time() < deadline:
                    time.sleep(0.1)
                    continue
                break
            if data[:4] != b"RREF":
                continue
            got = True
            self.last_rx = time.time()
            for off in range(5, len(data) - 7, 8):
                idx, val = struct.unpack("<if", data[off:off + 8])
                if 0 <= idx < len(self.DATAREFS):
                    self.values[self.DATAREFS[idx][0]] = val
        return got

    def read(self):
        self._pump()
        now = time.time()
        if now - self.last_rx > 3 and now - self.last_sub > 5:
            self._subscribe(self.freq)  # X-Plane restarted or the flight was reloaded
        if now - self.last_rx > 5 or "lat" not in self.values:
            return None  # stale: the tracker skips this sample and reports a lost connection if it lasts
        v = self.values.get
        return Telemetry(
            t=time.time(),
            lat=v("lat", 0.0), lon=v("lon", 0.0),
            alt_ft=altimeter_alt(v("ind_alt_ft", None), v("elev_m", 0.0) * M_TO_FT), agl_ft=v("agl_m", 0.0) * M_TO_FT,
            true_alt_ft=v("elev_m", 0.0) * M_TO_FT,
            ias=max(0.0, v("ias", 0.0)), gs=max(0.0, v("gs_ms", 0.0) * 1.94384), vs_fpm=v("vs_fpm", 0.0),
            hdg=v("hdg", 0.0) % 360, on_ground=v("on_ground", 1.0) > 0.5,
            engines_running=any(v(f"eng{i}", 0.0) > 0.5 for i in range(1, 5)),
            # set only if both brake values say so: an aircraft with its own brake system can leave one stuck
            parking_brake=min(v("pbrake", 0.0), v("pbrake2", v("pbrake", 0.0))) > 0.5,
            fuel_lbs=v("fuel_kg", 0.0) * KG_TO_LB, weight_lbs=v("weight_kg", 0.0) * KG_TO_LB,
            gear_down=v("gear", 1.0) > 0.5, flaps=v("flaps", 0.0), g=v("g", 1.0),
            pitch=v("pitch", None), sim_rate=max(v("simspeed", 1.0) or 1.0, v("timeaccel", 1.0) or 1.0), paused=v("paused", 0.0) > 0.5,
        )

    def close(self):
        if self.sock:
            try:
                self._subscribe(0)  # unsubscribe
                self.sock.close()
            except Exception:
                pass


# --------------------------------------------------------------------------
# Demo flight: a time-compressed synthetic flight for testing the pipeline
# --------------------------------------------------------------------------
class DemoSource:
    name = "Demo"

    def __init__(self, origin, destination, cruise_ft=35000, block_fuel_lbs=40000, zfw_lbs=120000, speedup=60):
        self.o, self.d = origin, destination
        self.cruise = max(12000, cruise_ft or 35000)
        self.fuel = float(block_fuel_lbs or 40000)
        self.zfw = float(zfw_lbs or 120000)
        self.speedup = speedup
        self.total_nm = gc_distance_nm(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
        self.state = "parked"
        self.state_t = 0.0
        self.sim_t = time.time()
        self.last_wall = None
        self.flown = 0.0
        self.alt = 0.0
        self.ias = 0.0
        self.vs = 0.0
        self.engines = False
        self.brake = True
        self.on_ground = True
        self.touchdown = None
        self.burn_pph = 7000 + self.zfw / 40

    def connect(self):
        pass

    def close(self):
        pass

    def read(self) -> Telemetry:
        now = time.time()
        wall_dt = 0.0 if self.last_wall is None else now - self.last_wall
        self.last_wall = now
        dt = wall_dt * self.speedup
        # keep ground phases near real time so they remain watchable
        if self.on_ground:
            dt = wall_dt * min(self.speedup, 8)
        self.sim_t += dt
        self.state_t += dt
        s, st = self.state, self.state_t
        gs = 0.0
        remaining = self.total_nm - self.flown

        if s == "parked" and st > 40:
            self._go("push")
        elif s == "push":
            gs = 3.0
            if st > 60:
                self.engines = True
                self._go("taxi")
            self.brake = False
        elif s == "taxi":
            gs = 14.0
            if st > 150:
                self._go("roll")
        elif s == "roll":
            self.ias = min(165.0, self.ias + 4.0 * dt)
            gs = self.ias
            if self.ias >= 160:
                self.on_ground = False
                self._go("climb")
        elif s == "climb":
            self.vs = 2400.0 if self.alt < 10000 else 1800.0
            self.ias = 240.0 if self.alt < 10000 else 290.0
            gs = self.ias * (1 + self.alt / 60000)
            self.alt = min(self.cruise, self.alt + self.vs * dt / 60)
            if self.alt >= self.cruise:
                self.vs = 0
                self._go("cruise")
        elif s == "cruise":
            self.vs = 0
            self.ias = 280.0
            gs = 480.0
            if remaining < self.alt / 1000 * 3.2 + 12:
                self._go("descent")
        elif s == "descent":
            self.vs = -2200.0 if self.alt > 11000 else -1400.0
            self.ias = 280.0 if self.alt > 10000 else 230.0
            gs = self.ias * (1 + self.alt / 60000)
            self.alt = max(2500.0, self.alt + self.vs * dt / 60)
            if self.alt <= 2500:
                self.vs = 0.0  # level at 2,500 ft until the glidepath
            if remaining * 318 <= self.alt + 50 or remaining < 8:
                self._go("approach")
        elif s == "approach":
            # a 3-degree glidepath (about 318 ft per nm) down to the runway, never descending faster than 1,500 fpm
            self.ias = 145.0
            gs = 140.0
            before = self.alt
            path = max(0.0, (remaining - 0.25) * 318)
            self.alt = max(path, self.alt - 1500 * dt / 60) if self.alt > path else path
            self.vs = (self.alt - before) / dt * 60 if dt > 0 else -750.0
            if self.alt < 60:
                self.vs = -165.0
            if remaining < 0.3:
                self.alt = 0.0
                self.on_ground = True
                self.touchdown = -165.0
                self._go("rollout")
        elif s == "rollout":
            self.vs = 0
            self.ias = max(0.0, 140 - 5.0 * st)
            gs = max(14.0, self.ias)
            if self.ias < 20:
                self._go("taxi_in")
        elif s == "taxi_in":
            self.ias = 0
            gs = 12.0
            if st > 120:
                self._go("park")
        elif s == "park":
            gs = 0.0
            self.brake = True
            if st > 10:
                self.engines = False

        if self.engines:
            self.fuel = max(0.0, self.fuel - self.burn_pph * (0.3 if self.on_ground else 1.0) * dt / 3600)
        self.flown = min(self.total_nm, self.flown + gs * dt / 3600)
        f = self.flown / self.total_nm if self.total_nm else 1
        lat, lon = gc_interpolate(self.o["lat"], self.o["lon"], self.d["lat"], self.d["lon"], f)
        hdg = bearing(lat, lon, self.d["lat"], self.d["lon"])
        return Telemetry(
            t=self.sim_t, lat=lat, lon=lon, alt_ft=self.alt, agl_ft=self.alt,
            ias=self.ias if not (s in ("push", "taxi", "taxi_in")) else gs, gs=gs, vs_fpm=self.vs, hdg=hdg,
            on_ground=self.on_ground, engines_running=self.engines, parking_brake=self.brake,
            fuel_lbs=self.fuel, weight_lbs=self.zfw + self.fuel, gear_down=self.alt < 2500,
            flaps=0.3 if self.alt < 3000 else 0.0, g=1.25 if s == "rollout" and st < 2 else 1.0,
            touchdown_fpm=self.touchdown,
            pitch=(min(8.5, max(0.0, (self.ias - 150) * 0.9)) if s == "roll" else 9.0 if s == "climb" and self.alt < 1500 else
                   5.0 if s == "climb" else 2.5 if s == "cruise" else 4.0 if s == "approach" else 1.0 if not self.on_ground else 0.0),
        )

    def _go(self, s):
        self.state = s
        self.state_t = 0.0
