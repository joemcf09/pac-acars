# PAC ACARS: how it fits together

A local web app. `python app.py` starts a Flask server on port 5050; the
browser is the interface. Everything the airline knows lives in `data/`.

## Server (Python)

| File | What it does |
|---|---|
| `app.py` | Flask app: loads data files, serves pages and the core API (bookings, ACARS tracking, PIREPs, logbook, weather, finance, dispatch, fleet admin, backups). Builds each PIREP from the flight recorder. |
| `auth.py` | Sign-in: passwords (salted hashes), sessions, one-time links for new pilots and resets, keys for PAC ACARS, and the gatekeeper that sorts every request into public, members and staff. |
| `va.py` | The virtual-airline layer (a Flask blueprint): pilots, ranks, careers, awards, events, tours and rotations, airframes, review queue, staff tools, pay and wallet, jumpseats, urgent requests, the job board and partner crew requests, news and NOTAMs, the gallery, ACARS dispatch messages and maintenance. |
| `tests/flightgen.py`, `tests/test_flights.py` | Scripted realistic flights on real runway geometry, run through the real tracker, scoring, analysis, economics, pay, dispatch messages and maintenance. |
| `tracker.py` | `FlightRecorder` turns a telemetry stream into flight phases, OOOI times, exceedances, touchdowns and bounces, integrity checks (sim rate, pause), and the samples used for analysis. `TrackerThread` polls the simulator. |
| `sim_sources.py` | Telemetry sources: MSFS (SimConnect), X-Plane (UDP datarefs), and the demo aircraft. All produce the same `Telemetry` record. |
| `analysis.py` | Landing analysis (runway match, touchdown point, centreline, float, stability, rollout) and takeoff analysis (rotation, liftoff, tail-strike margin, runway used). |
| `economics.py` | Contract pricing and flight costs. PAC's revenue, costs and profit per flight and estimates. |
| `dispatch.py` | Dispatch release, cargo manifest, loading plan and NOTOC, generated once at booking. |
| `weather.py` | METAR/TAF fetch (aviationweather.gov), cache and decoder; wind components. |
| `online.py` | VATSIM/IVAO presence from the networks' public feeds. |

| `acars_core.py` | ACARS logic shared by the website and the ACARS app: weather uplinks, loadsheet and stand, online checks, dispatch messages and OCC replies. |
| `acars_client/build/` | Windows packaging: PyInstaller recipe, version details, Inno Setup installer script, `build_acars.bat`, `BUILD.md`. Builds land in `static/downloads/` for the website's download card. |
| `liveries.py` | Liveries on the Fleet page: staff add a file or a link per aircraft type with the painter's credit; listed under `/api/fleet/liveries` (public), files download for signed-in pilots only, new ones are announced through the Discord bot. Stored in `data/liveries.json` and `data/liveries/<id>/`. |
| `acars_client/client.py`, `acars_client/ui.html` | The PAC ACARS app, in two processes. The **engine** (the program started normally) runs the local server on port 5070, the tracker, dispatch messages, website updates, saving, the chime and the tray icon (on its main thread). The **window** is, by preference, a Microsoft Edge (or Chrome) **app window** showing `ui.html` from the engine, with its own profile in `%APPDATA%\PAC ACARS\window-profile` and background throttling switched off; the built-in pywebview window (the same program with `--window`) is the fallback. The engine controls the window through the Windows API (`winctl.py`): showing, hiding to the tray, compact resizing, always-on-top. Every second it checks whether Windows reports the window as not responding (8 s) and whether the page still checks in (15 s); either way a frozen window is closed and a fresh one opened, and tracking never stops. The window is followed by its handle and its check-ins, not by the browser process the engine started, because Edge often hands a new app window to a copy of itself that is already running and exits at once (1.0.3 mistook that for the window closing). Before opening a window the engine ends any browser still running on the window profile, and on start-up it adopts a PAC ACARS window left open from before instead of opening a second. The app is: a local window (port 5070) that runs the tracker and simulator connection, talks to the website over HTTP, and hands over the finished flight record. |

`va.init(...)` receives shared objects from `app.py` (database, fleet, missions,
routes, airports, partners, helpers) so the two modules don't import each other.

## Browser

| File | What it does |
|---|---|
| `static/index.html` | Page layout and dialogs. |
| `static/app.js` | All client code: views (home, missions, ACARS, fleet, career, finance, logbook, gallery, handbook, staff, profile), maps, cards and charts. |
| `static/app.css` | Styles. |
| `static/dispatch.html` | The printable dispatch paperwork. |

## Data (`data/`)

| File | Contents |
|---|---|
| `logbook.db` | SQLite: PIREPs, pilots, applications, airframes, wallet, urgent requests, jobs, news, gallery index, maintenance items. |
| `fleet.json`, `missions.json`, `routes.json`, `airports.json`, `runways.json`, `partners.json` | Reference data shipped with the app. |
| `fleet_custom.json` | Admin fleet changes (new, edited, retired types). Never overwritten by updates. |
| `profile.json`, `settings.json`, `site.json` | Your profile, settings and home-page text. |
| `booking.json`, `flight_state.pkl` | The current booking and in-flight state (for resuming after a restart). |
| `gallery/` | Uploaded screenshots. |
| `backups/` | Automatic copies made at every start (last 14). |

## The website and the ACARS app

All tracking happens in the PAC ACARS app. The website's ACARS page follows the flight
live and opens the app with `pacacars://open?flight=PAC1022&sim=MSFS`. That link type is
registered for the current Windows user by the installer and by the app itself at every
start, so it works for installed and portable copies. A second launch hands its link to
the running copy (`POST /api/open` on port 5070), which reloads the flight and comes to
the front. The website checks whether the app is running with `GET /api/ping` on port 5070.


The ACARS app talks to the website through `/api/acars/app/*`:

| Call | Purpose |
|---|---|
| `GET hello` | The booked flight, a few settings, company NOTAMs. |
| `POST start` | Registers the app's flight; the website stops offering built-in tracking. |
| `POST live` | A status snapshot every 3 s, so the website's ACARS page follows the flight. |
| `POST complete` | The whole flight record (`FlightRecorder.export()`), rebuilt on the website with `from_export()` and scored by `build_pirep`. Scoring always happens on the website. |
| `POST abort` | Cancels the app's flight. |

After `complete`, filing goes through the normal `POST /api/pirep`.

## A flight, end to end

1. **Book** (`POST /api/booking`): checks rank, location, aircraft and airframe; reserves the airframe; generates dispatch paperwork.
2. **Track** in the PAC ACARS app: its `TrackerThread` feeds telemetry to `FlightRecorder`; dispatch messages, weather uplinks and online checks run alongside (`acars_core.py`). The app sends live status to the website and hands over the finished record.
3. **Talk to dispatch** (the app's Dispatch panel, `acars_core.handle_message`): delays, diversions, fuel checks, ETA, fault write-ups and free text; OCC replies are queued a few seconds later. Reported delays and declared diversions feed into scoring; write-ups are opened on the tail at filing.
4. **File** (`POST /api/pirep`): `build_pirep` scores the flight, runs landing and takeoff analysis, economics and pay; `va.after_file` moves the airframe and pilot, opens maintenance items, pays the wallet and awards badges.

## Data, backups and updates

User data lives in `data/` (`logbook.db`, `settings.json`, `profile.json`, `site.json`, `fleet_custom.json`,
`booking.json`, `secret_key`, `pilot_photo.*`, `fleet_photos/`, `gallery/`, `backups/`). Packages never contain
these. `tools/update.py` (via `update.bat`) backs up, then copies program files only, skipping a protected list.
`/api/staff/backup/download` and `/restore` move everything as one zip (restore validates the logbook and takes a
safety backup first). The database is prepared (`va.migrate`, `auth.migrate`) the first time each file is opened.

## Checks

Run these before shipping a change:

```
python tests/test_flights.py      # scripted flights through the real tracker, scoring, analysis, economics and pay
python tools/check_frontend.py    # JavaScript syntax check (needs Node.js)
python tests/test_acars_window.py # the ACARS app's window supervision: frozen window replaced, closing mid-flight keeps tracking
python tests/test_liveries.py      # liveries: file and link, painter credit, sign-in for files, editing, Discord announcement
python tests/test_airframe_rename.py # renaming an airframe carries its hours, history, write-ups and job references
python tests/test_acars_handoff.py # the window handed to another Edge process, a window left from before, Edge lingering on the profile
python tests/test_acars_app.py    # the ACARS app: every button during a live flight with a slow weather service; every action must answer within 1.5 s
python app.py  &  python tools/smoke_test.py   # every API endpoint through a running server
```

## Network growth and rotations (October 2026)

* `tools/build_routes.py` keeps the original lanes in `LANES` and appends the new ones from `MORE` (one lane per
  line). New lanes go at the end of their region so every existing PAC number stays the same. New lanes use
  `balanced_types()`: up to two MSFS and two X-Plane types by sector length; the original routes keep their aircraft.
* `missiongen.py` scenarios can set `ferry`, `types`, `challenge` and `handling`; `va._scenario_mission()` turns them
  into `ferry_bonus`, `types_only`, `challenge` and `handling` on the mission. `va._recommend()` puts the chosen type
  first and adds one from the other simulator when one fits.
* `va.ROTATIONS` and `build_rotation_legs()` add rotation legs to `TOUR_LEGS`, so every lookup that knows tour legs
  knows rotation legs. `rotation_progress()` walks the pilot's accepted PIREPs in order, so laps repeat.
  `check_booking()` enforces the order and the types; `enrich_pirep()` pays the bonus on the last leg of a lap.
* Live missions are numbered PAC6000–8999 and skip scheduled route numbers. When an old live mission shares a number
  with a newer route, history lookups use the live mission's own record first.

## Group hub (`group.py`)

A blueprint for the Pagani Aviation Group hub: the key-protected roster/handoff feed and METAR relay (CORS-enabled,
off by default, key in `group_feed_key`, kept out of the browser), the `pilots.pra` column, and `add_onward()`, which
dispatch.py calls to add PRA village freight to flights into PANC.
