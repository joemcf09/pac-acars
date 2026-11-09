"""PAC ACARS: the flight-tracking app.

Runs next to the simulator. It reads MSFS or X-Plane, runs the flight phases,
dispatch messages, weather and online checks locally, keeps the PAC website
updated with the live flight, and hands the finished flight record to the
website, which scores it and files the PIREP.

Start it with   python acars_client/client.py   (or start_acars.bat).
It opens a compact window (native if pywebview is installed, otherwise in your browser).
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)  # running as the packaged PAC ACARS.exe
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if not FROZEN:
    sys.path.insert(0, str(ROOT))
# bundled read-only files (window, logos, airport data)
RES = Path(getattr(sys, "_MEIPASS", HERE))
AIRPORTS_FILE = RES / "data" / "airports.json" if FROZEN else ROOT / "data" / "airports.json"
# runway data for the in-app landing debrief (1.1): bundled with the app's assets, or the website's copy when run from source
RUNWAYS_DIR = next((d for d in (RES / "assets", RES / "data", ROOT / "data") if (d / "runways.json").exists()), RES / "assets")
# where the app may write: %APPDATA%\\PAC ACARS when installed, the app folder when run from source


class LogFile:
    """The log PAC ACARS writes when it has no console. It starts afresh (keeping one older copy as acars.old.log)
    whenever it passes LOG_MAX, while running as well as at start-up, so it never grows without limit."""
    LOG_MAX = 2_000_000

    def __init__(self, path):
        self.path, self.lock = Path(path), threading.Lock()
        self._roll()
        self.f = open(self.path, "a", encoding="utf-8", buffering=1)

    def _roll(self):
        try:
            if self.path.exists() and self.path.stat().st_size > self.LOG_MAX:
                self.path.replace(self.path.with_name(self.path.stem + ".old" + self.path.suffix))
        except OSError:
            pass

    def write(self, text):
        with self.lock:
            try:
                n = self.f.write(text)
                if self.f.tell() > self.LOG_MAX:
                    self.f.close()
                    self._roll()
                    self.f = open(self.path, "a", encoding="utf-8", buffering=1)
                return n
            except (OSError, ValueError):
                return 0

    def flush(self):
        try:
            self.f.flush()
        except (OSError, ValueError):
            pass

    def isatty(self):
        return False


if FROZEN:
    USER_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "PAC ACARS"
    USER_DIR.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = LogFile(USER_DIR / "acars.log")  # no console window in the exe
else:
    USER_DIR = HERE
    if sys.stdout is None or sys.stderr is None:  # started windowless (pythonw) from a pacacars:// link
        sys.stdout = sys.stderr = LogFile(HERE / "acars.log")

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

import acars_core  # noqa: E402
from sim_sources import DemoSource, MSFSSource, XPlaneSource, gc_distance_nm  # noqa: E402
from tracker import FlightRecorder, TrackerThread  # noqa: E402

VERSION = "1.1.5"   # major.minor.patch, plus a fourth number for hotfixes (shown as "1.1.2 hotfix 1")
PORT = int(os.environ.get("PAC_ACARS_PORT", "5070"))  # not 5060: browsers block that port (SIP)
CONFIG_PATH = USER_DIR / "config.json"
STATE_PATH = USER_DIR / "flight_state.pkl"
# The airline's website. A build made with PAC_SITE set (build_acars.bat reads it, or Staff > Downloads bakes it in)
# points pilots at the real site, so they don't have to type it. Anyone can still change it in Settings.
def _built_site():
    try:
        import site_url                       # written by build_acars.bat when the build is made
        return str(site_url.SITE).strip().rstrip("/")
    except Exception:
        return ""


OFFICIAL_SITE = "https://pac-va.com"
# Pilots' copies (the packaged exe) always know the real website, even if the build forgot to bake it in; run from
# source on the PC that also runs the website, the app talks to that local copy.
SITE = (os.environ.get("PAC_SITE", "").strip().rstrip("/") or _built_site()
        or (OFFICIAL_SITE if FROZEN else "http://127.0.0.1:5050"))
DEFAULTS = {"server": SITE, "source": "MSFS", "xplane_host": "127.0.0.1", "demo_speedup": 60, "always_on_top": True,
            "win_w": 460, "win_h": 640, "chime": True, "chime_volume": 0.5, "close_to_tray": True,
            "sop_coach": True, "discord_status": True, "start_reminder": True}
# Discord Rich Presence: the PAC application's ID from discord.com/developers (public, not a secret).
# The website can also send one (Staff settings: discord_app_id), which wins.
DISCORD_APP_ID = ""
UPLINK_KINDS = ("ul", "wx")  # messages to the flight deck: they chime and light MSG

_ap = json.loads(AIRPORTS_FILE.read_text(encoding="utf-8"))
_rows = _ap[[k for k in _ap if k != "fields"][0]]
_f = _ap["fields"]
AIRPORTS = {r[0]: dict(zip(_f, r)) for r in _rows}


def nearest_airport(lat, lon, within=4.0):
    best = None
    for icao, a in AIRPORTS.items():
        if abs(a["lat"] - lat) > 0.2 or abs(a["lon"] - lon) > 0.3:
            continue
        d = gc_distance_nm(lat, lon, a["lat"], a["lon"])
        if d <= within and (best is None or d < best[1]):
            best = (icao, d)
    return best[0] if best else None


def load_config():
    try:
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_config(cfg):
    cfg = dict(cfg)
    if _norm_site(cfg.get("server")) == _norm_site(DEFAULTS["server"]):
        cfg.pop("server", None)       # only remember the address if the pilot chose a different one
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _norm_site(url):
    url = str(url or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.replace("://localhost", "://127.0.0.1")


def is_local_site(url):
    """An address on this PC or the home network: right for testing, never for a pilot's everyday copy."""
    host = (urllib.parse.urlsplit(_norm_site(url)).hostname or "").lower()
    return (host in ("127.0.0.1", "::1", "localhost", "0.0.0.0") or host.startswith(("192.168.", "10.", "169.254."))
            or any(host.startswith(f"172.{n}.") for n in range(16, 32)))


class ServerError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status
        self.detail = None          # the technical reason, shown small under the message
        self.unreachable = False    # no answer at all (as opposed to an error from the website)


_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never send local traffic through a system proxy


def server_url():
    """The website address. 'localhost' becomes 127.0.0.1: the website listens on IPv4 only, and on Windows
    Python may try IPv6 (::1) for 'localhost' first."""
    return _norm_site(load_config().get("server")) or _norm_site(DEFAULTS["server"])


def server(method, path, body=None, timeout=10):
    """Calls the PAC website."""
    base = server_url()
    url = base + path
    local = is_local_site(base)
    headers = {"Content-Type": "application/json", "User-Agent": f"PAC-ACARS/{VERSION}"}
    token = load_config().get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"  # signed in: the key the website gave this app
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with (_DIRECT.open(req, timeout=timeout) if local else urllib.request.urlopen(req, timeout=timeout)) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except Exception:
            msg = None
        if e.code == 401:
            state["auth_needed"] = True
        raise ServerError(msg or f"The PAC website answered with HTTP {e.code}.", e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        why = getattr(e, "reason", None) or e
        err = ServerError(f"Can't reach the PAC website at {base}." +
                          (" Nothing is running at that address on this PC." if is_local_site(base) else
                           " Check your internet connection, then try again."))
        err.detail, err.unreachable = str(why), True
        raise err


OPEN_PREFIX = "pacacars:"

state = {"thread": None, "rec": None, "booking": None, "source": None, "hello": None, "server_ok": False,
         "server_error": None, "handed_over": False, "draft": None, "result": None, "last_push": 0, "acked": 0,
         "window": None, "tray": None, "compact": False, "server_detail": None, "site_notice": None}
lock_fallback = threading.Lock()


def lock():
    th = state.get("thread")
    return th.lock if th else lock_fallback


class Busy(Exception):
    """The tracker held the flight record for too long: answer without it rather than wait."""


class TimedLock:
    """The tracker's lock, but giving up after a couple of seconds. Everything the window asks for uses this,
    so a slow moment in the tracker can never freeze the app."""
    def __init__(self, timeout=2.0):
        self.lk, self.timeout = lock(), timeout

    def __enter__(self):
        if not self.lk.acquire(timeout=self.timeout):
            raise Busy()
        return self

    def __exit__(self, *exc):
        self.lk.release()
        return False


def snapshot(rec):
    """A consistent copy of the flight record, taken under the lock (so it can't change while it's being sent)."""
    with lock():
        return json.loads(json.dumps(rec.export()))


def save_state(rec):
    try:
        tmp = STATE_PATH.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump({"recorder": rec, "source": state.get("source")}, fh)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        print("Could not save flight state:", e)


def saved_flight():
    try:
        with open(STATE_PATH, "rb") as fh:
            return pickle.load(fh)
    except Exception:
        return None


def clear_state():
    STATE_PATH.unlink(missing_ok=True)


def saved_candidates(booking):
    """Flights in progress that can be resumed for this booking: this copy's file and the website's copy. Newest first."""
    out = []
    if not booking:
        return out
    saved = saved_flight()
    if saved and saved["recorder"].booking.get("requested_at") == booking.get("requested_at") and not saved["recorder"].complete:
        try:
            at = STATE_PATH.stat().st_mtime
        except OSError:
            at = 0
        out.append({"where": "this PC", "phase": saved["recorder"].phase, "at": at, "source": saved.get("source")})
    cp = (state.get("hello") or {}).get("checkpoint")
    if cp and cp.get("phase") not in (None, "PREFLIGHT"):
        out.append({"where": "PAC website", "phase": cp["phase"], "at": cp.get("saved_at") or 0, "source": cp.get("source")})
    return sorted(out, key=lambda x: -x["at"])


SIM_PROCESSES = {"x-plane.exe": "X-Plane", "flightsimulator.exe": "MSFS", "flightsimulator2024.exe": "MSFS"}


def detect_sims():
    """Which simulators are running right now (Windows): X-Plane, MSFS 2020 or MSFS 2024."""
    if sys.platform != "win32":
        return []
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=8,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.lower()
        return sorted({sim for exe, sim in SIM_PROCESSES.items() if f'"{exe}"' in out})
    except Exception:
        return []


def sim_watch():
    while True:
        state["detected_sims"] = detect_sims()
        time.sleep(10)


def suggested_source(booking=None):
    """The simulator to preselect: the one running; else what this aircraft type was last flown in; else the website's hint."""
    running = state.get("detected_sims") or []
    if len(running) == 1:
        return running[0], "detected"
    cfg = load_config()
    ac = (booking or {}).get("aircraft")
    if ac and (cfg.get("sim_by_type") or {}).get(ac):
        return cfg["sim_by_type"][ac], "last used"
    if state.get("link_sim"):
        return state["link_sim"], "from the website"
    return cfg.get("source") or "MSFS", "default"


def use_site(url, notice=None, chosen=False):
    """Point PAC ACARS at another website. The sign-in key belongs to the old one, so the pilot signs in again.
    chosen: the pilot typed this address in Settings, so it's never switched away from automatically."""
    cfg = load_config()
    if _norm_site(url) != _norm_site(cfg.get("server")):
        cfg.pop("token", None)
        cfg.pop("pilot", None)
    cfg["server"] = _norm_site(url)
    cfg.pop("server_chosen", None)
    if chosen and _norm_site(url) != _norm_site(DEFAULTS["server"]):
        cfg["server_chosen"] = True
    save_config(cfg)
    state["site_notice"] = notice


def fall_back_to_official():
    """A copy left pointing at a test website on this PC (127.0.0.1:5050 and the like) that isn't running: if the
    real PAC website answers, switch to it rather than leave the pilot stuck. Never during a tracked flight."""
    here, home = server_url(), _norm_site(DEFAULTS["server"])
    if load_config().get("server_chosen") or not is_local_site(here) or is_local_site(home) or here == home:
        return False
    if state.get("thread") and state["thread"].is_alive():
        return False
    try:   # only switch to a site that really is PAC (not a captive portal or a proxy's error page)
        with urllib.request.urlopen(urllib.request.Request(home + "/api/acars/app/download",
                                                           headers={"User-Agent": f"PAC-ACARS/{VERSION}"}), timeout=8) as r:
            if "version" not in json.loads(r.read() or b"{}"):
                return False
    except Exception:
        return False
    print(f"Website {here} isn't running; switching to {home}")
    use_site(home, f"PAC ACARS was set to {here}, which isn't running, so it now uses {home}. "
                   "Sign in with your PAC pilot ID and password.")
    return True


def refresh_hello(_retry=True):
    try:
        state["hello"] = server("GET", "/api/acars/app/hello")
        state.update(server_ok=True, server_error=None, server_detail=None, auth_needed=False)
    except ServerError as e:
        if e.status == 401:  # the website is there, but PAC ACARS needs to sign in
            state.update(server_ok=True, server_error=None, server_detail=None, auth_needed=True, hello=None)
        elif e.unreachable and _retry and fall_back_to_official():
            return refresh_hello(_retry=False)
        else:
            state.update(server_ok=False, server_error=str(e), server_detail=e.detail)
    return state["hello"]


def stop_thread():
    th = state.get("thread")
    if th and th.is_alive():
        th.stop()
        th.join(timeout=3)
    state["thread"] = None


def send_finished(rec):
    """Offline queue: a finished flight is kept on this PC (it survives closing PAC ACARS or restarting Windows) and
    sent the moment the website can be reached again. Tries every 3 seconds, quietly."""
    if not state.get("finished_saved"):
        save_state(rec)
        state["finished_saved"] = True
    try:
        hand_over()
        state.update(server_ok=True, server_error=None, pending_send=None)
        print("Finished flight sent to the website.")
    except ServerError as e:
        state.update(server_ok=False, server_error=str(e), pending_send={"flight": rec.booking.get("flight_number"), "since": state.get("pending_send", {}) and state["pending_send"].get("since") or time.time()})
    except Exception as e:
        print("Send finished flight:", e)


def restore_finished():
    """At start-up: a flight that finished but never reached the website goes back in the queue."""
    saved = saved_flight()
    if not saved or getattr(saved["recorder"], "practice", False) or not saved["recorder"].complete:
        return
    rec = saved["recorder"]
    bk = (state.get("hello") or {}).get("booking")
    if bk and bk.get("requested_at") != rec.booking.get("requested_at"):
        return                           # the website moved on (a new booking): this one was already filed or cancelled
    state.update(rec=rec, booking=rec.booking, source=saved.get("source"), handed_over=False, finished_saved=True)
    print("Restored a finished flight that hadn't reached the website:", rec.booking.get("flight_number"))


def hand_over(force=False):
    """Sends the finished flight record to the website, which scores it."""
    rec, booking = state["rec"], state["booking"]
    record = snapshot(rec)
    r = server("POST", "/api/acars/app/complete", {"record": record, "requested_at": booking.get("requested_at"),
                                                  "source": state.get("source"), "force": force}, timeout=30)
    state.update(handed_over=True, draft=r.get("draft"))
    return r


def si_flight_json():
    """SayIntentions.AI writes the pilot's API key and current flight to %LOCALAPPDATA%\\SayIntentionsAI\\flight.json.
    Returns (api_key, modified time) or (None, None)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    path = Path(os.environ.get("PAC_SI_FLIGHT_JSON") or os.path.join(base, "SayIntentionsAI", "flight.json"))
    try:
        mtime = path.stat().st_mtime
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None, None
    key = ((data.get("flight_details") or {}).get("api_key") or data.get("api_key") or "").strip()
    return (key or None), mtime


def si_sync():
    """Tell PAC the pilot's SayIntentions key, and when SayIntentions starts a new flight, so PAC can brief the
    pilot's AI dispatcher, crew and co-pilot. Quiet if SayIntentions isn't installed."""
    if time.time() - state.get("si_checked", 0) < 20 or not state.get("server_ok") or state.get("auth_needed"):
        return
    state["si_checked"] = time.time()
    key, mtime = si_flight_json()
    if not key or (key == state.get("si_key") and mtime == state.get("si_mtime")):
        return
    try:
        server("POST", "/api/acars/app/sayintentions", {"api_key": key, "new_flight": mtime != state.get("si_mtime")})
        if key != state.get("si_key"):
            print("SayIntentions.AI found: PAC will brief your AI crew about your flights.")
        state.update(si_key=key, si_mtime=mtime)
    except Exception as e:
        print(f"Couldn't pass SayIntentions details to PAC: {e}")


def pusher():
    """Keeps the website's live view up to date, and hands over the flight when it's on block."""
    while True:
        time.sleep(3)
        si_sync()
        rec, th = state.get("rec"), state.get("thread")
        if not rec and time.time() - state.get("last_hello", 0) > 30:  # idle: pick up a plan attached on the website
            state["last_hello"] = time.time()
            refresh_hello()
        if rec:
            debrief_tick(rec)
        if rec and getattr(rec, "practice", False):
            continue                     # landing practice stays on this PC: nothing is sent to the website
        if rec and rec.complete and not state.get("handed_over") and not (th and th.is_alive()):
            send_finished(rec)           # a finished flight still waiting to reach the website (offline at block-in)
            continue
        if not rec or not th or state.get("handed_over"):
            continue
        try:
            with lock():
                st = json.loads(json.dumps(rec.status()))
            st.update(connected=bool(th.connected), error=th.error)
            server("POST", "/api/acars/app/live", {"status": st}, timeout=6)
            state.update(server_ok=True, server_error=None)
            if rec.start_t and not rec.complete and (time.time() - state.get("last_checkpoint", 0) > 60 or rec.phase != state.get("checkpoint_phase")):
                record = snapshot(rec)
                server("POST", "/api/acars/app/checkpoint", {"record": record, "requested_at": (state.get("booking") or {}).get("requested_at"),
                                                            "source": state.get("source")}, timeout=20)
                state.update(last_checkpoint=time.time(), checkpoint_phase=rec.phase)
            if rec.complete:
                stop_thread()
                hand_over()
        except ServerError as e:
            state.update(server_ok=False, server_error=str(e))
        except Exception as e:
            print("Live update failed:", e)


# ---------------------------------------------------------------- the app's local interface
ui = Flask(__name__, static_folder=None)


@ui.get("/")
def index():
    return send_from_directory(RES, "ui.html")


@ui.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(RES / "assets", name)


@ui.get("/api/state")
def api_state():
    if not request.headers.get("X-PAC-Probe"):
        state["ui_seen"] = time.time()
    rec, th = state.get("rec"), state.get("thread")
    status = None
    if rec:
        try:
            with TimedLock(1.0):
                status = json.loads(json.dumps(rec.status()))
            state["last_status"] = status
        except Busy:
            status = dict(state.get("last_status") or {})  # the tracker is busy: show the last picture for a moment
        status.update(connected=bool(th and th.connected), error=th.error if th else None, tracking=bool(th and th.is_alive()))
        last = getattr(th, "last_sample", None) if th else None
        status["data_age"] = round(time.time() - last, 1) if last else None      # seconds since the sim last sent data
        status["debriefs"] = state.get("debriefs") or []
        status["practice"] = bool(getattr(rec, "practice", False))
        if status["practice"]:
            status["practice_airport"] = rec.origin.get("icao") if rec.origin.get("icao") != "----" else None
        status.pop("track", None)  # the window doesn't draw the flown track (the website's map does), so don't send it every second
    hello = state.get("hello") or {}
    bk = hello.get("booking")
    # Resume is possible when nothing is being tracked and the current recorder (if any) never got going
    idle = not (th and th.is_alive()) and (not rec or not rec.oooi.get("out"))
    cands = saved_candidates(bk) if idle else []
    resumable = bool(cands)
    saved_info = cands[0] if cands else None
    sug, why = suggested_source(bk)
    return jsonify({"version": VERSION, "config": {**load_config(), "server": server_url()}, "server_ok": state["server_ok"],
                    "server_error": state["server_error"], "server_detail": state.get("server_detail"),
                    "default_server": _norm_site(DEFAULTS["server"]), "site_notice": state.get("site_notice"),
                    "hello": hello, "status": status, "source": state.get("source"), "handed_over": state["handed_over"],
                    "draft": state.get("draft"), "result": state.get("result"), "resumable": resumable, "saved": saved_info,
                    "suggested_source": sug, "suggested_why": why, "detected_sims": state.get("detected_sims") or [],
                    "auth_needed": bool(state.get("auth_needed")), "signed_in_as": load_config().get("pilot"),
                    "unread": unread(), "compact": state.get("compact"), "native": bool(state.get("native")), "tray": bool(state.get("tray")),
                    "win_cmd": state.get("win_cmd"), "window_restarts": state.get("window_restarts", 0),
                    "practice": bool(state.get("practice")), "debriefs": state.get("debriefs") or [],
                    "update": update_info(), "whats_new": whats_new(), "start_reminder": state.get("start_reminder"), "pending_send": state.get("pending_send")})


@ui.get("/api/track")
def api_track():
    """The flown track for the moving map: [lat, lon, altitude, phase] every 30 s (the state poll leaves it out)."""
    rec = state.get("rec")
    if not rec:
        return jsonify({"track": []})
    try:
        with TimedLock(1.0):
            track = list(rec.track[-2000:])
    except Busy:
        track = []
    return jsonify({"track": track})


# ---------------------------------------------------------------- 1.1: landing debrief, landing practice
def debrief_tick(rec):
    """Turns each touchdown into a coaching card about 40 seconds after it happens (once the rollout or the climb-out
    is recorded). Works the same for a normal flight and for landing practice."""
    try:
        if getattr(rec, "practice", False) and rec.last and rec.origin.get("icao") == "----":
            icao = nearest_airport(rec.last.lat, rec.last.lon, within=6.0)
            if icao:
                a = AIRPORTS[icao]
                apt = {"icao": icao, "lat": a["lat"], "lon": a["lon"], "name": a.get("name", "")}
                with lock():
                    rec.origin, rec.dest = dict(apt), dict(apt)
                    rec.booking["mission"]["origin"] = rec.booking["mission"]["destination"] = dict(apt)
                    rec.msg(time.time(), f"PRACTICE AT {icao}  EVERY LANDING IS GRADED. NOTHING IS FILED", "phase")
        done = {d["t"] for d in state.get("debriefs") or []}
        now_sim = rec.last.t if rec.last else 0
        for td in list(getattr(rec, "touchdowns", []) or []):
            if td["t"] in done or not (now_sim - td["t"] >= 40 or rec.complete):
                continue
            with lock():
                card = acars_core.landing_debrief(rec, td, RUNWAYS_DIR, nearest_airport)
            state.setdefault("debriefs", []).append(card)
            state["debriefs"] = state["debriefs"][-20:]
            print(f"Landing {card['n']}: {card['rate_fpm']} fpm, {card.get('verdict')}")
    except Exception as e:
        print("Debrief:", e)


@ui.post("/api/practice/start")
def api_practice_start():
    """Landing practice: circuits and touch-and-goes at any airport. Every landing gets a debrief; nothing is filed,
    nothing is sent to the website and no booking is needed."""
    if state.get("thread") and state["thread"].is_alive():
        return jsonify({"error": "A flight is being tracked. Finish or abort it first."}), 409
    b = request.json or {}
    cfg = load_config()
    name = b.get("source") or cfg["source"]
    if name == "MSFS":
        src = MSFSSource()
    elif name == "X-Plane":
        src = XPlaneSource(host=cfg.get("xplane_host") or "127.0.0.1")
    else:
        return jsonify({"error": "Choose MSFS or X-Plane for landing practice."}), 400
    here = {"icao": "----", "lat": 0.0, "lon": 0.0}
    booking = {"practice": True, "flight_number": "PRACTICE", "aircraft": "", "requested_at": time.time(),
               "mission": {"title": "Landing practice", "origin": dict(here), "destination": dict(here), "payload_lbs": 0, "cargo": ""}}
    rec = FlightRecorder(booking)
    rec.sop_coach = bool(cfg.get("sop_coach", True))
    rec.msg(time.time(), "LANDING PRACTICE  FLY CIRCUITS OR TOUCH-AND-GOES. EACH LANDING GETS A DEBRIEF", "phase")
    th = TrackerThread(src, rec, check_origin=False)
    state.update(thread=th, rec=rec, booking=None, source=name, handed_over=False, draft=None, result=None, practice=True, debriefs=[])
    th.start()
    return jsonify({"ok": True})


@ui.post("/api/practice/stop")
def api_practice_stop():
    if not state.get("practice"):
        return jsonify({"error": "Landing practice isn't running."}), 400
    rec = state.get("rec")
    if rec:
        debrief_tick(rec)
        rec.complete = True
        debrief_tick(rec)          # the last landing gets its card even if it was less than 40 s ago
    stop_thread()
    state.update(rec=None, practice=False)
    return jsonify({"ok": True, "debriefs": state.get("debriefs") or []})


# ---------------------------------------------------------------- 1.1: built-in update
UPDATE = {"state": "idle", "progress": 0, "error": None, "file": None, "version": None, "dismissed": False,
          "mb_got": 0, "mb_total": 0, "eta_s": None}


def _vt(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def installed_copy():
    """True for the installed program (it can update itself); a portable copy or the source code can't."""
    return FROZEN and any((Path(sys.executable).parent / n).exists() for n in ("unins000.exe", "unins001.exe"))


def changelog_since(prev):
    """The changelog entries newer than `prev`, up to this version: [{version, date, text}]."""
    try:
        text = (RES / "CHANGELOG.txt").read_text(encoding="utf-8")
    except OSError:
        try:
            text = (HERE / "CHANGELOG.txt").read_text(encoding="utf-8")
        except OSError:
            return []
    out, cur = [], None
    for line in text.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^(\d+\.\d+\.\d+)(?: hotfix (\d+))? \((.+)\)\s*$", line)
        if m:
            cur = {"version": m.group(1) + (f".{m.group(2)}" if m.group(2) else ""), "date": m.group(3), "lines": []}
            out.append(cur)
        elif cur is not None and not re.match(r"^-{3,}\s*$", line):
            cur["lines"].append(line)
    keep = [e for e in out if _vt(e["version"]) <= _vt(VERSION) and (prev is None or _vt(e["version"]) > _vt(prev))]
    return [{"version": e["version"], "date": e["date"], "text": "\n".join(e["lines"]).strip()} for e in keep[:4]]


def whats_new():
    """After an update, the first start shows what changed (once). A brand-new install just remembers the version."""
    cfg = load_config()
    seen = cfg.get("seen_version")
    if seen == VERSION:
        return None
    if seen is None and not cfg.get("token"):
        cfg["seen_version"] = VERSION      # first ever start: nothing to compare with
        save_config(cfg)
        return None
    entries = changelog_since(seen if seen and _vt(seen) < _vt(VERSION) else None)
    if seen is None:
        entries = entries[:1]              # updated from a version without this feature: this version's notes
    return {"version": VERSION, "from": seen, "entries": entries} if entries else None


@ui.post("/api/whatsnew/seen")
def api_whatsnew_seen():
    cfg = load_config()
    cfg["seen_version"] = VERSION
    save_config(cfg)
    return jsonify({"ok": True})


def update_info():
    h = state.get("hello") or {}
    latest = h.get("latest_app")
    inst = h.get("latest_installer") or {}
    newer = bool(latest) and _vt(latest) > _vt(VERSION)
    return {"current": VERSION, "latest": latest, "available": newer, "can_install": newer and installed_copy() and bool(inst.get("url")),
            "size_mb": inst.get("size_mb"), "state": UPDATE["state"], "progress": UPDATE["progress"], "error": UPDATE["error"],
            "dismissed": UPDATE["dismissed"], "page": server_url() + "/#downloads",
            "mb_got": UPDATE.get("mb_got"), "mb_total": UPDATE.get("mb_total"), "eta_s": UPDATE.get("eta_s")}


def _download_update(inst):
    try:
        UPDATE.update(state="downloading", progress=0, error=None, mb_got=0, mb_total=0, eta_s=None)
        folder = USER_DIR / "updates"
        folder.mkdir(exist_ok=True)
        for old in folder.glob("PAC-ACARS-Setup-*.exe"):
            try:
                old.unlink()
            except OSError:
                pass
        target = folder / Path(inst["file"]).name
        url = inst["url"] if inst["url"].startswith("http") else server_url() + inst["url"]
        headers = {"User-Agent": f"PAC-ACARS/{VERSION}"}
        token = load_config().get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        opener = _DIRECT.open if is_local_site(url) else urllib.request.urlopen
        with opener(req, timeout=30) as r, open(target, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0) or int((inst.get("size_mb") or 0) * 1_048_576)
            got, t0 = 0, time.time()
            UPDATE["mb_total"] = round(total / 1_048_576, 1) if total else 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                UPDATE["mb_got"] = round(got / 1_048_576, 1)
                if total:
                    UPDATE["progress"] = min(99, int(got * 100 / total))
                    took = time.time() - t0
                    if took > 1 and got:          # time left, from the speed so far
                        UPDATE["eta_s"] = max(0, int((total - got) / (got / took)))
        with open(target, "rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("The download isn't a Windows installer. Try again, or download it from the website.")
        if got < 1_000_000:
            raise ValueError("The download was incomplete. Try again.")
        UPDATE.update(state="ready", progress=100, file=str(target), version=inst.get("version"))
    except Exception as e:
        UPDATE.update(state="error", error=str(e) if isinstance(e, ValueError) else f"Download failed: {e}")


@ui.post("/api/update/download")
def api_update_download():
    info = update_info()
    if not info["available"]:
        return jsonify({"error": "You already have the latest PAC ACARS."}), 400
    if not info["can_install"]:
        return jsonify({"error": "This copy of PAC ACARS can't update itself. Download the new version from the PAC website.",
                        "page": info["page"]}), 400
    if UPDATE["state"] == "downloading":
        return jsonify({"ok": True})
    threading.Thread(target=_download_update, args=((state.get("hello") or {}).get("latest_installer"),), daemon=True).start()
    return jsonify({"ok": True})


@ui.post("/api/update/install")
def api_update_install():
    """Runs the downloaded installer (Windows asks for permission), then starts the new PAC ACARS. A flight that's
    being tracked must be finished or saved first; a saved flight can be resumed in the new version."""
    if state.get("thread") and state["thread"].is_alive():
        return jsonify({"error": "A flight is being tracked. Update after it's filed, or close PAC ACARS to save it first."}), 409
    if UPDATE["state"] != "ready" or not UPDATE["file"] or not Path(UPDATE["file"]).exists():
        return jsonify({"error": "The update isn't downloaded yet."}), 400
    UPDATE["state"] = "installing"
    threading.Timer(0.8, quit_for_update, args=(UPDATE["file"],)).start()
    return jsonify({"ok": True})


def quit_for_update(installer=None):
    """Closes this window first (so no stale window is left showing an error), then starts the installer and exits
    at once. The installer closes anything left, installs, and starts the new version itself (silent installs)."""
    try:
        stop_thread()
        end_window(state.get("win_proc"))
        if state.get("win_detached"):
            import winctl
            winctl.close(state.get("win_hwnd"))
    except Exception as e:
        print("Closing for the update:", e)
    if installer:
        import subprocess
        log = USER_DIR / "updates" / "install.log"
        flags = 0x00000008 | 0x00000200   # detached, new process group
        subprocess.Popen([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", f"/LOG={log}"],
                         creationflags=flags, close_fds=True, cwd=str(USER_DIR / "updates"))
    PID_FILE.unlink(missing_ok=True)
    os._exit(0)


@ui.post("/api/update/later")
def api_update_later():
    UPDATE["dismissed"] = True
    return jsonify({"ok": True})


# ---------------------------------------------------------------- 1.1: Discord status ("Flying PAC1234 KCVG → KMIA")
class DiscordIPC:
    """Talks to the Discord desktop app over its local pipe (no extra packages). Quietly does nothing when Discord isn't running."""

    def __init__(self, app_id):
        self.app_id, self.f = app_id, None

    def _send(self, op, payload):
        import struct
        data = json.dumps(payload).encode()
        self.f.write(struct.pack("<II", op, len(data)) + data)
        head = self.f.read(8)
        if len(head) < 8:
            raise OSError("Discord closed the connection")
        _, n = struct.unpack("<II", head)
        return json.loads(self.f.read(n) or b"{}")

    def connect(self):
        for i in range(10):
            try:
                self.f = open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
                break
            except OSError:
                self.f = None
        if not self.f:
            return False
        r = self._send(0, {"v": 1, "client_id": self.app_id})
        if r.get("evt") != "READY":
            self.close()
            return False
        return True

    def set(self, activity):
        import uuid
        return self._send(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": activity}, "nonce": str(uuid.uuid4())})

    def close(self):
        try:
            if self.f:
                self.f.close()
        except OSError:
            pass
        self.f = None


def discord_activity():
    rec, h = state.get("rec"), state.get("hello") or {}
    base = {"assets": {"large_image": "pac", "large_text": "Pagani Air Cargo · pac-va.com"},
            "buttons": [{"label": "Fly with Pagani Air Cargo", "url": OFFICIAL_SITE}]}
    PH = {"PREFLIGHT": "Preparing", "PUSHBACK": "Pushback", "TAXI_OUT": "Taxiing", "TAKEOFF": "Taking off", "INITIAL_CLIMB": "Climbing",
          "CLIMB": "Climbing", "CRUISE": "Cruising", "DESCENT": "Descending", "APPROACH": "On approach", "GO_AROUND": "Going around",
          "LANDING": "Landing", "TAXI_IN": "Taxiing in", "ARRIVED": "On block"}
    if rec and getattr(rec, "practice", False):
        apt = rec.origin.get("icao")
        n = len(getattr(rec, "touchdowns", []) or [])
        return {**base, "details": f"Landing practice{' at ' + apt if apt and apt != '----' else ''}",
                "state": f"{n} landing{'s' if n != 1 else ''} so far"}
    if rec and rec.start_t:
        bk = rec.booking or {}
        ac = (bk.get("aircraft_info") or {}).get("name") or bk.get("aircraft") or ""
        l = rec.last
        alt = ""
        if l and not l.on_ground:
            alt = f" · FL{round(l.alt_ft / 100):03d}" if l.alt_ft >= 18000 else f" · {round(l.alt_ft, -2):,.0f} ft"
        act = {**base, "details": f"{bk.get('flight_number', 'PAC')} · {rec.origin.get('icao')} → {rec.dest.get('icao')}",
               "state": f"{PH.get(rec.phase, rec.phase)}{alt}{' · ' + ac if ac else ''}"[:128]}
        start = rec.oooi.get("out") or rec.start_t
        if start:
            act["timestamps"] = {"start": int(start)}
        return act
    bk = h.get("booking")
    if bk:
        return {**base, "details": f"Planning {bk.get('flight_number', '')}", "state": f"{bk['mission']['origin']['icao']} → {bk['mission']['destination']['icao']}"}
    return None


def discord_presence():
    if sys.platform != "win32":
        return
    ipc, last = None, None
    while True:
        time.sleep(15)
        try:
            app_id = (state.get("hello") or {}).get("discord_app_id") or DISCORD_APP_ID
            if not app_id or not load_config().get("discord_status", True):
                if ipc:
                    ipc.close()
                    ipc, last = None, None
                continue
            act = discord_activity()
            key = json.dumps(act, sort_keys=True, default=str)
            if key == last:
                continue
            if not ipc:
                ipc = DiscordIPC(app_id)
                if not ipc.connect():
                    ipc = None
                    continue
            ipc.set(act)
            last = key
        except Exception:
            if ipc:
                ipc.close()
            ipc, last = None, None


@ui.get("/api/ping")
def api_ping():
    """Lets the PAC website see that PAC ACARS is running (read-only, no flight data)."""
    resp = jsonify({"app": "PAC ACARS", "version": VERSION, "tracking": bool(state.get("thread") and state["thread"].is_alive()),
                    "window": state.get("win_mode"), "window_open": window_open(), "window_detached": bool(state.get("win_detached")),
                    "window_pid": state["win_proc"].pid if state.get("win_proc") else state.get("win_pid"),
                    "ui_age_s": round(time.time() - state["ui_seen"], 1) if state.get("ui_seen") else None,
                    "window_restarts": state.get("window_restarts", 0)})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def apply_open_url(url):
    """pacacars://open?flight=PAC1022&sim=MSFS : load the booked flight and pick the simulator."""
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) if url else {}
    sim = (q.get("sim") or [""])[0]
    if sim in ("MSFS", "X-Plane"):
        state["link_sim"] = sim  # only a hint: a running simulator, or what you last flew the type in, comes first
    refresh_hello()
    state["opened_for"] = (q.get("flight") or [None])[0]


@ui.post("/api/open")
def api_open():
    """A second launch (from a pacacars:// link) hands its link to this running copy."""
    apply_open_url((request.json or {}).get("url"))
    bring_to_front()
    return jsonify({"ok": True})


def uplinks():
    rec = state.get("rec")
    if not rec:
        return 0
    try:
        with TimedLock(1.0):
            n = sum(1 for m in rec.messages if m.get("kind") in UPLINK_KINDS)
        state["last_uplinks"] = n
        return n
    except Busy:
        return state.get("last_uplinks", 0)


def unread():
    return max(0, uplinks() - state.get("acked", 0))


@ui.post("/api/login")
def api_login():
    """Signs PAC ACARS in to the PAC website once; the key it receives is kept in this app's settings."""
    b = request.json or {}
    import socket
    try:
        cfg = load_config()
        cfg.pop("token", None)
        save_config(cfg)
        r = server("POST", "/api/auth/token", {"pilot_id": b.get("pilot_id"), "password": b.get("password"),
                                               "label": f"PAC ACARS on {socket.gethostname()}"[:60]}, timeout=15)
    except ServerError as e:
        return jsonify({"error": str(e)}), 400
    cfg = load_config()
    cfg.update(token=r["token"], pilot={"id": r["pilot"]["id"], "name": r["pilot"]["name"]})
    save_config(cfg)
    state["auth_needed"] = False
    refresh_hello()
    return jsonify({"ok": True, "pilot": cfg["pilot"]})


@ui.post("/api/logout")
def api_logout():
    if state.get("thread") and state["thread"].is_alive():
        return jsonify({"error": "A flight is being tracked. Finish or abort it before signing out."}), 409
    try:
        server("POST", "/api/auth/token/revoke", {})
    except ServerError:
        pass
    cfg = load_config()
    cfg.pop("token", None)
    cfg.pop("pilot", None)
    save_config(cfg)
    state.update(auth_needed=True, hello=None)
    return jsonify({"ok": True})


@ui.post("/api/ack")
def api_ack():
    """The pilot has seen the messages: MSG light off."""
    state["acked"] = uplinks()
    return jsonify({"ok": True})


@ui.post("/api/ofp")
def api_ofp():
    """Fetch the latest SimBrief OFP for the booked flight through the PAC website."""
    if state.get("thread") and state["thread"].is_alive():
        st = state["rec"].phase if state.get("rec") else None
        if st and st != "PREFLIGHT":
            return jsonify({"error": "The flight is under way. Import the OFP before pushback."}), 409
    try:
        r = server("POST", "/api/acars/app/ofp", {"raw": (request.json or {}).get("raw")} if (request.json or {}).get("raw") else {}, timeout=30)
    except ServerError as e:
        return jsonify({"error": str(e)}), 400
    refresh_hello()
    if state.get("rec") and state.get("hello", {}).get("booking"):
        with lock():  # the flight in progress uses the new plan (fuel checks, loadsheet)
            state["rec"].booking = state["hello"]["booking"]
            state["booking"] = state["hello"]["booking"]
    return jsonify({"ok": True, "warnings": r.get("warnings", [])})


@ui.post("/api/compact")
def api_compact():
    """The window switched compact mode itself: just remember it (for the tray menu)."""
    state["compact"] = bool((request.json or {}).get("on"))
    threading.Thread(target=apply_compact, args=(state["compact"],), daemon=True).start()
    return jsonify({"ok": True, "compact": state["compact"]})


@ui.post("/api/site/default")
def api_site_default():
    """The 'Use pac-va.com' button: back to the airline's own website."""
    if state.get("thread") and state["thread"].is_alive():
        return jsonify({"error": "A flight is being tracked. Change the website address after it's filed."}), 409
    use_site(DEFAULTS["server"])
    refresh_hello()
    return api_state()


@ui.post("/api/notice/dismiss")
def api_notice_dismiss():
    state["site_notice"] = None
    return jsonify({"ok": True})


@ui.post("/api/refresh")
def api_refresh():
    refresh_hello()
    return api_state()


@ui.post("/api/config")
def api_config():
    cfg = load_config()
    b = request.json or {}
    if "server" in b:
        new = _norm_site(b["server"]) or _norm_site(DEFAULTS["server"])
        if new != server_url():
            if state.get("thread") and state["thread"].is_alive():
                return jsonify({"error": "A flight is being tracked. Change the website address after it's filed."}), 409
            use_site(new, chosen=True)
            cfg = load_config()
        b = {k: v for k, v in b.items() if k != "server"}
    for k in ("source", "xplane_host", "demo_speedup", "always_on_top", "chime", "chime_volume", "close_to_tray", "window_mode", "design",
              "sop_coach", "discord_status", "start_reminder"):
        if k in b:
            cfg[k] = b[k]
    save_config(cfg)
    refresh_hello()
    return jsonify({"ok": True, "config": {**load_config(), "server": server_url()}})


@ui.post("/api/start")
def api_start():
    reminder_release()
    state["finished_saved"] = False
    if state.get("thread") and state["thread"].is_alive():
        return jsonify({"error": "Already tracking."}), 409
    hello = refresh_hello()
    if not hello:
        return jsonify({"error": state["server_error"]}), 503
    booking = hello.get("booking")
    if not booking:
        return jsonify({"error": "No flight is booked. Book one on the PAC website, then press Refresh."}), 400
    b = request.json or {}
    cfg = load_config()
    name = b.get("source") or cfg["source"]
    cfg["source"] = name
    save_config(cfg)
    ofp, m = booking.get("ofp") or {}, booking["mission"]
    cands = saved_candidates(booking)
    if cands and not b.get("resume") and not b.get("discard_saved"):
        c = cands[0]
        return jsonify({"error": f"This flight is already under way: it was saved in {c['phase'].replace('_', ' ').lower()} at "
                                 f"{time.strftime('%H:%M', time.localtime(c['at']))}. Press Resume flight to carry on, or Abort to discard it.",
                        "saved": c}), 409
    resume_rec = None
    if b.get("resume") and cands:
        if name == "Demo":
            return jsonify({"error": "Demo flights can't be resumed. Choose MSFS or X-Plane."}), 400
        if cands[0]["where"] == "PAC website":
            try:
                cp = server("GET", "/api/acars/app/checkpoint", timeout=20)
                resume_rec = FlightRecorder.from_export(booking, cp["record"])
            except (ServerError, KeyError, TypeError) as e:
                print("Could not load the website's copy:", e)
        if resume_rec is None:
            saved = saved_flight()
            if saved and saved["recorder"].booking.get("requested_at") == booking.get("requested_at"):
                resume_rec = saved["recorder"]
        if resume_rec is None:
            return jsonify({"error": "The saved flight couldn't be loaded. Abort it and start again from the stand."}), 400
    resuming = resume_rec is not None
    if name in ("MSFS", "X-Plane"):  # remember what this aircraft type is flown in
        cfg = load_config()
        cfg.setdefault("sim_by_type", {})[booking["aircraft"]] = name
        save_config(cfg)
    if name == "MSFS":
        src = MSFSSource()
    elif name == "X-Plane":
        src = XPlaneSource(host=cfg.get("xplane_host") or "127.0.0.1")
    else:
        name = "Demo"
        src = DemoSource(ofp.get("origin") or m["origin"], ofp.get("destination") or m["destination"], cruise_ft=ofp.get("cruise_ft") or 35000,
                         block_fuel_lbs=ofp.get("block_fuel_lbs") or 45000, zfw_lbs=ofp.get("zfw_lbs") or 150000,
                         speedup=int(cfg.get("demo_speedup") or 60))
    try:
        r = server("POST", "/api/acars/app/start", {"source": name, "requested_at": booking.get("requested_at")})
    except ServerError as e:
        return jsonify({"error": str(e)}), 409
    if resuming:
        rec = resume_rec
        rec.booking = booking
        rec.msg(time.time(), f"ACARS RESUMED  SOURCE {name.upper()}", "phase")
    else:
        rec = FlightRecorder(booking)
        for title in hello.get("notams") or []:
            rec.msg(time.time(), f"CO NOTAM  {title.upper()}", "wx")
    s = hello.get("settings") or {}
    rec.allow_reposition = bool(s.get("allow_ground_reposition", True))
    rec.booking["aircraft_info"] = hello.get("aircraft") or {}
    rec.sop_coach = bool(load_config().get("sop_coach", True))
    th = TrackerThread(src, rec, check_origin=not resuming, on_save=save_state,
                       on_wx=lambda r_, j, l: acars_core.weather_job(r_, j, l, nearest_airport),
                       on_tick=lambda r_, l: acars_core.online_job(r_, l, s))
    state.update(thread=th, rec=rec, booking=booking, source=name, handed_over=False, draft=None, result=None, practice=False,
                 debriefs=list(state.get("debriefs") or []) if resuming else [],
                 acked=sum(1 for m in rec.messages if m.get("kind") in UPLINK_KINDS) if resuming else 0)
    th.start()
    return jsonify({"ok": True, "warning": r.get("warning"), "resumed": resuming})


@ui.post("/api/stop")
def api_stop():
    if state.get("practice"):
        return api_practice_stop()
    stop_thread()
    try:
        server("POST", "/api/acars/app/abort", {})
    except ServerError:
        pass
    clear_state()
    state.update(rec=None, booking=None, handed_over=False, draft=None)
    refresh_hello()
    return jsonify({"ok": True})


@ui.post("/api/message")
def api_message():
    rec = state.get("rec")
    if not rec or not rec.start_t:
        return jsonify({"error": "Start tracking first."}), 400
    try:
        err = acars_core.handle_message(rec, TimedLock(2.0), request.json or {}, AIRPORTS)
    except Busy:
        return jsonify({"error": "PAC ACARS is busy for a moment. Send it again."}), 503
    return (jsonify({"error": err}), 400) if err else jsonify({"ok": True})


@ui.post("/api/wx")
def api_wx():
    booking = state.get("booking") or (state.get("hello") or {}).get("booking")
    if not booking:
        return jsonify({"error": "No flight is loaded."}), 400
    m, ofp = booking["mission"], booking.get("ofp") or {}
    ids = [m["destination"]["icao"]] + ([ofp["alternate"]["icao"]] if ofp.get("alternate") else []) + [m["origin"]["icao"]]
    rec = state.get("rec")

    def fetch():  # the weather service can take several seconds: never make the window wait for it
        try:
            got = acars_core.request_weather(rec, lock(), ids)
            if rec and not any(i in got for i in ids[:2]):
                with lock():
                    rec.msg(time.time(), f"WX NOT AVAILABLE FOR {' '.join(ids[:2])}", "warn")
        except Exception as e:
            print("WX request failed:", e)
            if rec:
                with lock():
                    rec.msg(time.time(), "WX REQUEST FAILED. THE WEATHER SERVICE DIDN'T ANSWER. TRY AGAIN IN A MINUTE.", "warn")
    threading.Thread(target=fetch, daemon=True).start()
    return jsonify({"ok": True, "pending": True, "stations": ids[:2]})


@ui.post("/api/file")
def api_file():
    rec = state.get("rec")
    if not rec:
        return jsonify({"error": "No flight to file."}), 400
    b = request.json or {}
    try:
        if not state["handed_over"] or b.get("force"):
            stop_thread()
            hand_over(force=bool(b.get("force")))
        r = server("POST", "/api/pirep", {"remarks": b.get("remarks", ""), "force": bool(b.get("force"))}, timeout=30)
    except ServerError as e:
        return jsonify({"error": str(e)}), 400
    clear_state()
    state.update(rec=None, booking=None, result=r, handed_over=False, draft=None)
    refresh_hello()
    return jsonify({"ok": True, "result": r})


@ui.post("/api/done")
def api_done():
    state["result"] = None
    return jsonify({"ok": True})


# ---------------------------------------------------------------- the ACARS chime
def chime_wav(volume):
    """A soft two-tone 'ding-dong' as a WAV file, at the chosen volume."""
    import math
    import struct
    import wave
    rate, out = 22050, bytearray()
    vol = max(0.02, min(1.0, float(volume))) * 0.45
    n = int(rate * 1.2)
    for i in range(n):
        t = i / rate
        v = 0.0
        for freq, start in ((1175, 0.0), (880, 0.22)):
            if t >= start:
                tt = t - start
                env = min(1.0, tt / 0.02) * math.exp(-tt * 4.5)
                v += math.sin(2 * math.pi * freq * tt) * env
        out += struct.pack("<h", int(max(-1.0, min(1.0, v * vol)) * 32767))
    path = USER_DIR / "chime.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(out))
    return path


def play_chime(force=False):
    """Plays the chime through Windows, asynchronously: sound can never block the app or its window."""
    cfg = load_config()
    if not force and cfg.get("chime") is False:
        return
    if sys.platform != "win32":
        return
    try:
        import winsound
        vol = float(cfg.get("chime_volume") or 0.5)
        if state.get("chime_vol") != vol or not (USER_DIR / "chime.wav").exists():
            chime_wav(vol)
            state["chime_vol"] = vol
        winsound.PlaySound(str(USER_DIR / "chime.wav"), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception as e:
        print("Chime:", e)


def chime_watch():
    """New messages to the flight deck (PAC Operations, weather) chime once each batch."""
    last = None
    while True:
        time.sleep(1)
        try:
            n = uplinks() if state.get("rec") else None
            if n is not None and last is not None and n > last and state.get("native"):
                play_chime()
            last = n
        except Exception as e:
            print("Chime watch:", e)


@ui.post("/api/chime")
def api_chime():
    threading.Thread(target=play_chime, args=(True,), daemon=True).start()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- 1.1.4: "Start the flight tracker" alarm
ALARM_SRC = RES / "assets" / "start_acars.wav"


def alarm_wav():
    """Windows plays the alarm from the user's PAC ACARS folder, like the chime (the bundled copy sits in a
    temporary unpack folder that Windows sound can refuse)."""
    dst = USER_DIR / "start_acars.wav"
    try:
        if not dst.exists() or dst.stat().st_size != ALARM_SRC.stat().st_size:
            dst.write_bytes(ALARM_SRC.read_bytes())
        return str(dst)
    except Exception as e:
        print("Alarm file:", e)
        return str(ALARM_SRC)
_remind = {"src": None, "lock": threading.Lock(), "playing": False}


def alarm(on):
    """Loops the recorded call-out through Windows until tracking starts. Windows keeps looping it by itself,
    so it can never block the app; PlaySound(None) silences it."""
    if on == _remind["playing"]:
        return
    _remind["playing"] = on
    if sys.platform != "win32":
        print("Alarm", "on" if on else "off")
        return
    try:
        import winsound
        if on:
            path = alarm_wav()
            print("Alarm: playing", path)
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
        else:
            winsound.PlaySound(None, 0)
    except Exception as e:
        print("Alarm:", e)


@ui.post("/api/alarm/test")
def api_alarm_test():
    """Settings › Test alarm: plays the call-out once (not looped), unless the real alarm is sounding."""
    if sys.platform == "win32" and not _remind["playing"]:
        try:
            import winsound
            winsound.PlaySound(alarm_wav(), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            print("Alarm test:", e)
    return jsonify({"ok": True})


def reminder_release():
    """Silences the alarm and lets go of the sim before real tracking starts, so the watcher and the tracker never
    share a connection."""
    alarm(False)
    state["start_reminder"] = None
    with _remind["lock"]:
        src, _remind["src"] = _remind["src"], None
    if src:
        try:
            src.close()
        except Exception:
            pass


def reminder_should_watch():
    """A flight is booked, a simulator is running, and PAC ACARS is not recording it."""
    if load_config().get("start_reminder") is False or state.get("practice") or state.get("handed_over"):
        return None
    th = state.get("thread")
    if th and th.is_alive():
        return None
    if not (state.get("hello") or {}).get("booking"):
        return None
    sims = [x for x in state.get("detected_sims") or [] if x in ("MSFS", "X-Plane")]
    return sims[0] if len(sims) == 1 else None


def reminder_moving(t):
    """Pushback, taxi or airborne: engines running and rolling, brake released, or off the ground."""
    if not t.on_ground:
        return (t.agl_ft or 0) > 50
    return bool(t.engines_running) and ((t.gs or 0) > 3 or t.parking_brake is False)


def start_reminder_watch():
    """Once the aircraft moves without tracking, the alarm loops until the pilot starts tracking (or the flight is
    cancelled, the sim is closed, or the reminder is switched off in Settings). Stopping to taxi doesn't silence it."""
    while True:
        time.sleep(3)
        try:
            sim = reminder_should_watch()
            if not sim:
                if _remind["playing"] or _remind["src"]:
                    reminder_release()
                continue
            if _remind["playing"]:
                continue                     # already sounding: nothing to read, it only stops when tracking starts
            with _remind["lock"]:
                if _remind["src"] is None:
                    src = MSFSSource() if sim == "MSFS" else XPlaneSource(host=load_config().get("xplane_host") or "127.0.0.1", freq=1)
                    try:
                        src.connect()
                    except Exception as e:
                        print("Start reminder: can't read", sim, "yet:", e)
                        time.sleep(25)       # the sim is still loading: try again later
                        continue
                    _remind["src"] = src
                    print("Start reminder: watching", sim, "for", ((state.get("hello") or {}).get("booking") or {}).get("flight_number"))
                t = _remind["src"].read()
            if t and time.time() - _remind.get("logged", 0) > 60:
                _remind["logged"] = time.time()
                print(f"Start reminder: engines {'on' if t.engines_running else 'off'}, brake {'set' if t.parking_brake else 'off'}, "
                      f"{t.gs or 0:.0f} kt, {'on ground' if t.on_ground else 'airborne'}")
            if t and reminder_moving(t):
                bk = (state.get("hello") or {}).get("booking") or {}
                print("Start reminder: aircraft is moving and not tracked. Alarm on.")
                state["start_reminder"] = {"since": time.time(), "flight": bk.get("flight_number")}
                alarm(True)
                try:
                    show_window()
                except Exception:
                    pass
        except Exception as e:
            print("Start reminder:", e)
            with _remind["lock"]:
                src, _remind["src"] = _remind["src"], None
            try:
                src and src.close()
            except Exception:
                pass
            time.sleep(20)


# ---------------------------------------------------------------- window, compact mode and tray icon
COMPACT_SIZE = (400, 170)  # the strip plus the window title bar


def window_cmd(cmd, **kw):
    """Asks the window to do something (show itself, go compact). The window picks it up on its next update, and acts
    on it in its own process: the engine never touches the window directly, so nothing here can freeze it."""
    n = (state.get("win_cmd") or {}).get("id", 0) + 1
    state["win_cmd"] = {"id": n, "cmd": cmd, **kw}


def apply_compact(on):
    """Compact strip on or off. An app window is resized by the engine through Windows; the built-in window resizes itself."""
    import winctl
    h = state.get("win_hwnd")
    if state.get("win_mode") == "app" and h:
        cfg = load_config()
        if on:
            if not state.get("compact_applied"):
                state["full_size"] = winctl.size_of(h) or (int(cfg.get("win_w") or 460), int(cfg.get("win_h") or 640))
            winctl.resize(h, *COMPACT_SIZE)
            winctl.set_topmost(h, True)
        else:
            fw, fh = state.get("full_size") or (int(cfg.get("win_w") or 460), int(cfg.get("win_h") or 640))
            winctl.resize(h, fw, fh)
            winctl.set_topmost(h, bool(cfg.get("always_on_top")))
        state["compact_applied"] = on


def set_compact(on):
    """From the tray menu: switch compact mode and tell the window."""
    state["compact"] = bool(on)
    apply_compact(bool(on))
    window_cmd("compact", on=bool(on))


def show_window():
    """Brings the window forward, or opens a new one if it was closed."""
    import winctl
    if state.get("native") and not window_open():
        launch_window()
        return
    h = state.get("win_hwnd")
    if h and winctl.exists(h):
        winctl.show(h, keep_top=bool(load_config().get("always_on_top")) or bool(state.get("compact")))
    else:
        window_cmd("show")


def bring_to_front():
    show_window()


def tray_status():
    """(dot color, tooltip) for the tray icon."""
    rec, th = state.get("rec"), state.get("thread")
    bk = state.get("booking") or (state.get("hello") or {}).get("booking")
    flight = bk["flight_number"] if bk else "no flight"
    if state.get("result"):
        return None, f"PAC ACARS · {state['result'].get('flight_number', '')} filed"
    if not rec:
        return None, f"PAC ACARS · {flight}"
    if th and th.error:
        return (230, 60, 60), f"PAC ACARS · {flight} · {th.error[:60]}"
    if unread():
        return (255, 200, 69), f"PAC ACARS · {flight} · new message"
    if rec.complete or state.get("handed_over"):
        return (80, 160, 255), f"PAC ACARS · {flight} · on block"
    if th and th.is_alive():
        return (75, 208, 127), f"PAC ACARS · {flight} · {rec.phase.replace('_', ' ').title()}"
    return None, f"PAC ACARS · {flight}"


def shutdown():
    """Ends PAC ACARS: the flight is saved first (it can be resumed)."""
    stop_thread()
    end_window(state.get("win_proc"))
    if state.get("win_detached"):
        import winctl
        winctl.close(state.get("win_hwnd"))  # the window lives in another Edge process: close it too, leave nothing behind
    tray = state.get("tray")
    if tray:
        try:
            tray.stop()
        except Exception:
            pass
    PID_FILE.unlink(missing_ok=True)
    os._exit(0)


def run_tray():
    """The PAC icon in the notification area, run on the engine's main thread (how pystray expects to run).
    Returns False if no tray is available, so the caller keeps the engine alive another way."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception as e:
        print("Tray icon unavailable:", e)
        return False
    base = Image.open(RES / "assets" / "pac-acars.png").convert("RGBA").resize((64, 64))

    def image(dot):
        im = base.copy()
        if dot:
            d = ImageDraw.Draw(im)
            d.ellipse([38, 38, 63, 63], fill=dot + (255,), outline=(255, 255, 255, 255), width=3)
        return im

    def quit_app(icon, _item=None):
        th = state.get("thread")
        if th and th.is_alive() and not state.get("practice") and \
                not ask("A flight is being tracked. Quit PAC ACARS anyway?\n\nThe flight is saved and can be resumed."):
            return
        shutdown()

    menu = pystray.Menu(
        pystray.MenuItem("Show PAC ACARS", lambda i, it: show_window(), default=True),
        pystray.MenuItem("Compact mode", lambda i, it: (show_window(), set_compact(not state.get("compact"))),
                         checked=lambda it: bool(state.get("compact"))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit PAC ACARS", quit_app))
    icon = pystray.Icon("PAC ACARS", image(None), "PAC ACARS", menu)
    state["tray"] = icon

    def refresh(ic):
        ic.visible = True
        last = None
        while True:
            try:
                dot, tip = tray_status()
                if (dot, tip) != last:
                    ic.icon, ic.title, last = image(dot), tip, (dot, tip)
            except Exception as e:
                print("Tray update:", e)
            time.sleep(2)
    try:
        icon.run(setup=refresh)  # blocks until Quit
    except Exception as e:
        print("Tray icon failed:", e)
        state["tray"] = None
        return False
    return True


PID_FILE = USER_DIR / "pac-acars.pid"


def ask(text):
    """Yes/No question on Windows; elsewhere, assume yes."""
    print(text)
    if sys.platform == "win32":
        try:
            import ctypes
            return ctypes.windll.user32.MessageBoxW(0, text, "PAC ACARS", 0x4 | 0x20) == 6  # MB_YESNO | MB_ICONQUESTION
        except Exception:
            return False
    return True


def end_stuck_copy():
    """Ends a PAC ACARS that holds our port but no longer answers. Returns True if the port is free afterwards."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        pid = None
    if not pid or pid == os.getpid():
        return False
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
        else:
            import signal
            os.kill(pid, signal.SIGKILL)  # like taskkill /F: a frozen process may ignore a polite request
    except Exception as e:
        print("Could not end the stuck PAC ACARS:", e)
    for _ in range(20):
        if port_free():
            return True
        time.sleep(0.25)
    return False


def forward_to_running(url=None):
    """Hands a link (or just 'show yourself') to the PAC ACARS that's already open."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/open", method="POST",
                                     data=json.dumps({"url": url}).encode(), headers={"Content-Type": "application/json"})
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5).read()
        return True
    except Exception as e:
        print("Could not reach the running PAC ACARS:", e)
        return False


WINDOW_FROZEN_S = float(os.environ.get("PAC_ACARS_FROZEN_S", "15"))  # no check-in from the page for this long: frozen
WINDOW_HUNG_S = 8  # Windows reports the window as not responding for this long: frozen

# Chromium slows timers in minimized and hidden windows; these keep the window checking in, so it's never mistaken for frozen
APP_FLAGS = ["--no-first-run", "--no-default-browser-check", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
             "--disable-backgrounding-occluded-windows", "--disable-background-mode",
             "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling,Translate,msEdgeSidebarV2,msHubApps"]


def choose_window_mode():
    """The sturdiest window available: an Edge (or Chrome) app window, else the built-in window, else the browser."""
    import importlib.util
    import winctl
    if os.environ.get("PAC_ACARS_WINDOW_CMD"):
        return "test"
    want = load_config().get("window_mode", "auto")
    if want in ("auto", "app") and winctl.find_browser():
        return "app"
    if want in ("auto", "app", "webview") and importlib.util.find_spec("webview"):
        return "webview"
    return "browser"


def window_command():
    """How to open the window."""
    import importlib.util
    import winctl
    url = f"http://127.0.0.1:{PORT}/"
    mode = state.get("win_mode")
    if mode == "test":
        return os.environ["PAC_ACARS_WINDOW_CMD"].split("|") + [url]
    if mode == "app":
        profile = USER_DIR / "window-profile"  # its own profile: a separate, sturdy window that remembers its size and place
        first = not profile.exists()
        cfg = load_config()
        cmd = [winctl.find_browser(), f"--app={url}", f"--user-data-dir={profile}"] + APP_FLAGS
        if first:
            cmd.append(f"--window-size={int(cfg.get('win_w') or 460)},{int(cfg.get('win_h') or 640)}")
        cmd += [a for a in os.environ.get("PAC_ACARS_BROWSER_ARGS", "").split() if a]
        return cmd
    tray = ["--tray"] if importlib.util.find_spec("pystray") and "--no-tray" not in sys.argv else []
    if FROZEN:
        return [sys.executable, "--window", url] + tray
    return [sys.executable, str(Path(__file__).resolve()), "--window", url] + tray


WINDOW_CLOSED_S = float(os.environ.get("PAC_ACARS_CLOSED_S", "6"))  # a followed window that stops checking in this long: closed
HANDOFF_S = 10  # the program started for the window exits this soon: it passed the window on rather than closing it


def end_window(p):
    import winctl
    if p and p.poll() is None:
        winctl.kill_tree(p.pid)
        try:
            p.kill()
            p.wait(timeout=5)  # make sure the frozen window is really gone
        except Exception:
            pass


def end_detached_window():
    """Ends a window that lives in another process (Edge took it over): by its window on Windows, by its process otherwise."""
    import winctl
    h, pid = state.get("win_hwnd"), state.get("win_pid")
    if h and winctl.exists(h):
        pid = winctl.pid_of(h) or pid
    if pid:
        winctl.kill_tree(pid)
    state.update(win_detached=False, win_hwnd=None, win_pid=None)


def window_open():
    """There's a window: the one PAC ACARS started, or one it is following in another process."""
    p = state.get("win_proc")
    return bool((p and p.poll() is None) or state.get("win_detached"))


def window_connected():
    """The page in the current window has checked in at least once since it was opened."""
    return state.get("ui_seen", 0) > state.get("win_started", 0)


def page_gap():
    """Seconds since the current window last checked in (or since it was opened, if it hasn't yet)."""
    return time.time() - max(state.get("ui_seen", 0), state.get("win_started", 0))


def launch_window():
    import subprocess
    end_window(state.get("win_proc"))
    if state.get("win_detached"):
        end_detached_window()
    if state.get("win_mode") == "app":
        clear_window_profile()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" and state.get("win_mode") != "app" else 0
    extra = {} if sys.platform == "win32" else {"start_new_session": True}  # its own process group, so it can be ended as a whole
    state["win_proc"] = subprocess.Popen(window_command(), creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
    state.update(win_started=time.time(), win_cmd=None, win_hwnd=None, win_pid=None, win_detached=False, hung_since=None,
                 compact_applied=False, top_applied=None)
    print(f"{time.strftime('%H:%M:%S')} Window opened ({state['win_mode']}, process {state['win_proc'].pid}).")


def clear_window_profile():
    """Ends any Edge/Chrome still running on PAC ACARS's own window profile (a window left over from before, or Edge
    lingering in the background with it). Otherwise Edge hands the new window to that copy, which may be hidden or stuck."""
    import winctl
    profile = str(USER_DIR / "window-profile")
    browser = winctl.find_browser()
    pids = winctl.pids_with_arg(f"--user-data-dir={profile}", os.path.basename(browser) if browser else None)
    for pid in pids:
        winctl.kill_tree(pid)
    if pids:
        print(f"{time.strftime('%H:%M:%S')} Closed {len(pids)} leftover Edge/Chrome process(es) on PAC ACARS's window profile.")
        time.sleep(1)  # let the profile be released


def adopt_window(why):
    """Follow a window that lives in a process PAC ACARS didn't start, by its check-ins (and on Windows, by the window itself)."""
    state.update(win_proc=None, win_detached=True, win_hwnd=None)
    print(f"{time.strftime('%H:%M:%S')} {why} PAC ACARS follows it by its check-ins.")


def window_closed(where, tracking):
    state.update(win_proc=None, win_hwnd=None, win_pid=None, win_detached=False)
    if tracking:
        print(f"{time.strftime('%H:%M:%S')} Window closed mid-flight ({where}).")
        if not ask("PAC ACARS is tracking your flight.\n\nKeep tracking in the background?\n\n"
                   "Yes: keep tracking. PAC ACARS stays in the system tray, next to the clock.\n"
                   "No: save the flight and quit. You can resume it later."):
            print("Pilot chose to quit. The flight is saved.")
            shutdown()
            return
        tray = state.get("tray")
        if tray:
            try:
                tray.notify("PAC ACARS keeps tracking your flight. Click the tray icon to bring it back.", "PAC ACARS")
            except Exception:
                pass
    else:
        print(f"{time.strftime('%H:%M:%S')} Window closed. PAC ACARS stops.")
        shutdown()


def fall_back_to_browser(where):
    """The window couldn't be opened twice running: show PAC ACARS in the browser rather than leave the pilot without it."""
    print(f"{time.strftime('%H:%M:%S')} The window didn't connect after {state.get('silent_restarts', 0)} tries ({where}). "
          "Opening PAC ACARS in your browser instead; tracking is unaffected.")
    end_window(state.get("win_proc"))
    if state.get("win_detached"):
        end_detached_window()
    state.update(win_proc=None, native=False, win_mode="browser", silent_restarts=0)
    if os.environ.get("PAC_ACARS_WINDOW_CMD"):
        return  # tests: no real browser
    webbrowser.open(f"http://127.0.0.1:{PORT}/")


def window_supervisor():
    """Keeps the window healthy, every second.

    The window is judged by the window itself and by its page checking in, not by the program PAC ACARS started for it:
    Edge often hands a new app window to a copy of Edge that's already running and exits at once. (Before 1.0.4 that
    looked like 'window closed', so PAC ACARS shut down while the window stayed on screen: "Failed to fetch".)
    - Frozen (Windows says not responding for 8 s, or no check-in for 15 s while visible): close it, open a fresh one.
    - Closed by the pilot: keep tracking in the tray mid-flight, otherwise stop PAC ACARS.
    - Minimized with a tray icon: tuck it away there."""
    import winctl
    while True:
        time.sleep(1)
        p = state.get("win_proc")
        if not p and not state.get("win_detached"):
            continue
        try:
            rec, th = state.get("rec"), state.get("thread")
            tracking = bool(th and th.is_alive())
            where = f"phase {rec.phase}, tracking {'on' if tracking else 'off'}" if rec else "no flight loaded"
            mode = state.get("win_mode")
            if window_connected():
                state["silent_restarts"] = 0

            # the program started for the window has ended
            if p and p.poll() is not None:
                if mode == "app" or time.time() - state.get("win_started", 0) < HANDOFF_S:
                    adopt_window(f"The window was handed to another {'Edge/Chrome' if mode == 'app' else 'window'} process "
                                 f"(process {p.pid} ended after {time.time() - state.get('win_started', 0):.0f} s).")
                    p = None
                else:
                    window_closed(where, tracking)
                    continue

            # find the window on screen
            h = state.get("win_hwnd")
            if winctl.WIN and mode in ("app", "webview"):
                if h and not winctl.exists(h):
                    if p:
                        end_window(p)  # the window was closed but the browser stayed in the background
                    window_closed(where, tracking)
                    continue
                if not h:
                    if p:
                        h = winctl.find_window(winctl.child_pids(p.pid))
                    elif mode == "app":
                        h = winctl.find_app_window(winctl.find_browser())
                    state["win_hwnd"] = h
                    if h and not p:
                        state["win_pid"] = winctl.pid_of(h)

            # a followed window we can't see on screen: it's gone when its page stops checking in
            if state.get("win_detached") and not h and window_connected() and page_gap() > WINDOW_CLOSED_S:
                window_closed(where, tracking)
                continue

            if h:
                cfg = load_config()
                top = bool(cfg.get("always_on_top")) or bool(state.get("compact"))
                if mode == "app" and state.get("top_applied") != top:
                    winctl.set_topmost(h, top)
                    state["top_applied"] = top
                if state.get("compact") and not state.get("compact_applied"):
                    apply_compact(True)
                if winctl.is_minimized(h) and state.get("tray") and cfg.get("close_to_tray", True):
                    winctl.hide(h)  # minimized with a tray icon: tucked away there
                if winctl.is_hung(h):
                    state["hung_since"] = state.get("hung_since") or time.time()
                else:
                    state["hung_since"] = None
            reason = None
            if state.get("hung_since") and time.time() - state["hung_since"] > WINDOW_HUNG_S:
                reason = f"Windows reports it not responding for {time.time() - state['hung_since']:.0f} s"
            else:
                gap = page_gap()
                visible = not h or (winctl.is_visible(h) and not winctl.is_minimized(h))
                if gap > WINDOW_FROZEN_S and time.time() - state.get("win_started", 0) > WINDOW_FROZEN_S + 10 and visible:
                    reason = f"no update from the page for {gap:.0f} s" if window_connected() else \
                        f"the page never connected in {gap:.0f} s"
            if reason:
                if not window_connected():
                    state["silent_restarts"] = state.get("silent_restarts", 0) + 1
                    if state["silent_restarts"] >= 3:
                        fall_back_to_browser(where)
                        continue
                print(f"{time.strftime('%H:%M:%S')} WINDOW NOT RESPONDING: {reason} ({where}). Opening a fresh window; tracking carried on.")
                state["window_restarts"] = state.get("window_restarts", 0) + 1
                launch_window()
        except Exception as e:
            print("Window supervisor:", e)


def wait_for_window(secs):
    """True if a window that was already open checks in within this time (it reconnects to us by itself)."""
    t = time.time()
    while time.time() - t < secs:
        if state.get("ui_seen", 0) > t - 1.5:
            return True
        time.sleep(0.2)
    return False


def quiet_request_log():
    """The window checks in every second; logging each of those filled acars.log with a line a second. Keep the rest."""
    import logging

    def keep(record):
        msg = record.getMessage()
        if '" 200 ' in msg or '" 304 ' in msg:
            return not any(f"GET {path}" in msg for path in ("/api/state", "/api/ping", "/static/"))
        return True
    logging.getLogger("werkzeug").addFilter(keep)


def already_running():
    """True if another PAC ACARS already answers on our port."""
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(urllib.request.Request(
                f"http://127.0.0.1:{PORT}/api/state", headers={"X-PAC-Probe": "1"}), timeout=2) as r:
            return "version" in json.loads(r.read() or b"{}")
    except Exception:
        return False


def port_free():
    """Nothing is listening on our port. (Asking whether we could claim it gives false alarms for a short while after
    PAC ACARS closes, while the system winds down old connections; so check whether anything answers instead.)"""
    import socket
    with socket.socket() as sk:
        sk.settimeout(1.0)
        return sk.connect_ex(("127.0.0.1", PORT)) != 0

def alert(text):
    """A small message box on Windows; the console elsewhere."""
    print(text)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, "PAC ACARS", 0x40)
        except Exception:
            pass


def register_link_type():
    """Registers pacacars:// for this user, so the PAC website can open PAC ACARS with the flight loaded.
    Done on every start, so links always open the copy you started last: installed, portable or from source."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        if FROZEN:
            exe = sys.executable
            command, icon = f'"{exe}" "%1"', f'"{exe}",0'
        else:
            # from source: the windowless Python of PAC's environment, so no console window pops up
            py = Path(sys.executable)
            pyw = py.with_name("pythonw.exe")
            runner = pyw if pyw.exists() else py
            command = f'"{runner}" "{Path(__file__).resolve()}" "%1"'
            icon = f'"{HERE / "assets" / "pac-acars.ico"}",0'
        base = r"Software\Classes\pacacars"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:PAC ACARS")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\DefaultIcon") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, icon)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
        print("pacacars:// links open:", command)
    except Exception as e:
        print("Could not register pacacars:// links:", e)


def run_window():
    """The window process: only the window. Everything else (tracking, messages, the tray) runs in the engine,
    so if this process ever freezes, the engine notices, closes it and opens a fresh one."""
    url = sys.argv[sys.argv.index("--window") + 1] if len(sys.argv) > sys.argv.index("--window") + 1 else f"http://127.0.0.1:{PORT}/"
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PaganiAirCargo.PACACARS")
        except Exception:
            pass
    import webview
    cfg = load_config()
    w, h = int(cfg.get("win_w") or 460), int(cfg.get("win_h") or 640)
    x, y = cfg.get("win_x"), cfg.get("win_y")
    place = {"x": x, "y": y} if isinstance(x, int) and isinstance(y, int) and -200 < x < 8000 and -200 < y < 5000 else {}
    box = {}

    class Api:  # the window's JavaScript calls these; they act on this window, in this process
        def compact(self, on):
            win = box["w"]
            if on:
                box.setdefault("full", (int(win.width), int(win.height)))
                win.resize(*COMPACT_SIZE)
                win.on_top = True
            else:
                fw, fh = box.pop("full", None) or (int(load_config().get("win_w") or 460), int(load_config().get("win_h") or 640))
                win.resize(fw, fh)
                win.on_top = bool(load_config().get("always_on_top"))
            return True

        def show(self):
            win = box["w"]
            win.show()
            win.restore()
            win.on_top = True  # a brief on-top pulse brings it in front of the simulator and browser
            time.sleep(0.6)
            win.on_top = bool(load_config().get("always_on_top")) or "full" in box
            return True

    window = webview.create_window("PAC ACARS", url, width=max(380, w), height=max(420, h), min_size=(300, 200),
                                   on_top=bool(cfg.get("always_on_top")), js_api=Api(), **place)
    box["w"] = window

    def remember_size():
        try:
            c = load_config()
            fw, fh = box.get("full") or (int(window.width), int(window.height))
            c.update(win_w=fw, win_h=fh, win_x=int(window.x), win_y=int(window.y))
            save_config(c)
        except Exception:
            pass

    def on_minimized():  # with a tray icon, minimizing tucks the window away there
        if "--tray" in sys.argv and load_config().get("close_to_tray", True):
            window.hide()
    try:
        window.events.closing += remember_size
        window.events.minimized += on_minimized
    except AttributeError:
        pass
    webview.start()
    os._exit(0)


def main():
    if "--window" in sys.argv:
        return run_window()
    open_url = next((a for a in sys.argv[1:] if a.lower().startswith(OPEN_PREFIX)), None)
    if already_running():
        # the copy that's already open shows its window (from the tray, or behind other windows) and takes the link
        if not forward_to_running(open_url):
            alert("PAC ACARS is already running. Look for its window or its icon in the taskbar or tray.")
        return
    register_link_type()
    if not port_free():
        # something holds our port but doesn't answer: most likely a PAC ACARS that froze
        if ask("PAC ACARS isn't responding. It may have frozen.\n\nEnd it and start again? Your flight is saved and can be resumed."):
            if not end_stuck_copy():
                alert("PAC ACARS couldn't end the old copy. Open Task Manager, end PAC ACARS (or Python), then start PAC ACARS again.")
                return
        else:
            return
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass
    if sys.platform == "win32":
        try:  # our own taskbar identity, so the PAC icon shows instead of Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PaganiAirCargo.PACACARS")
        except Exception:
            pass
    if open_url:
        apply_open_url(open_url)
    else:
        refresh_hello()
    quiet_request_log()
    try:
        restore_finished()
    except Exception as e:
        print("Restore finished flight:", e)
    for job in (pusher, sim_watch, chime_watch, window_supervisor, discord_presence, start_reminder_watch):
        threading.Thread(target=job, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}/"
    threading.Thread(target=lambda: ui.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False), daemon=True).start()
    time.sleep(0.8)
    print(f"PAC ACARS {VERSION} · {url} · website {load_config()['server']}")

    # the window: its own process when the native window component is available, otherwise the browser
    mode = "browser" if ("--browser" in sys.argv or "--no-browser" in sys.argv) else choose_window_mode()
    native = mode in ("app", "webview", "test")
    why = None if native else "neither Microsoft Edge nor the window component is available"
    state.update(native=native, win_mode=mode)
    print("Window:", {"app": "Edge/Chrome app window", "webview": "built-in window", "test": "test window", "browser": "browser tab"}[mode])
    if native:
        if mode in ("app", "test") and wait_for_window(2.5):
            state["win_started"] = state["ui_seen"] - 0.01
            adopt_window("Found the PAC ACARS window still open from before and using it.")
            threading.Timer(0.3, show_window).start()
        else:
            launch_window()
    else:
        if why and "--no-browser" not in sys.argv and "--browser" not in sys.argv:
            alert("PAC ACARS is opening in your browser because its window component isn't available "
                  f"({why}).\n\nUse the installed PAC ACARS program, or run start_acars.bat, which installs it.")
        if "--no-browser" not in sys.argv:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    # the engine's main thread: the tray icon when there is one, otherwise just stay alive
    if native and "--no-tray" not in sys.argv and run_tray():
        shutdown()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
