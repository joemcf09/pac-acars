# Pagani Air Cargo ACARS

Mission board, SimBrief dispatch, live flight tracking and PIREP logbook for the
Pagani Air Cargo virtual fleet. It runs on the same PC as your simulator and
opens in your browser at http://localhost:5050.

## Install (Windows)

1. Install Python 3.10 or newer from python.org (tick "Add Python to PATH").
2. Double-click `start.bat`. The first run creates a virtual environment and
   installs Flask and the SimConnect library, then opens the app.

Manual start: `pip install -r requirements.txt` then `python app.py`.

## Flying a mission

1. **Settings**: enter your name, pilot ID and SimBrief username (or numeric
   SimBrief pilot ID), and pick your simulator.
2. **Mission board**: choose a mission and one of its approved aircraft.
3. **Open SimBrief with this mission**: origin, destination, aircraft type,
   callsign and cargo weight are prefilled. Generate the OFP in SimBrief.
4. **Fetch latest OFP**: pulls your newest OFP from the SimBrief API and checks
   it against the mission (airports, aircraft, payload limit). You can also paste
   or upload the OFP as JSON or XML.
5. **Request mission**: the mission is held for you and loaded into ACARS.
6. In the sim, load at a stand at the departure airport with the parking brake
   set, then press **Start tracking**. ACARS refuses to start more than 5 nm
   from the departure airport or while airborne.
7. Fly. At the arrival stand set the parking brake and shut down all engines.
   The flight goes on block, the PIREP is scored, and **File PIREP** writes it
   to the logbook.

Choose **Demo** as the simulator to test the whole flow without a sim. It flies
a time-compressed flight along the great circle (compression set in Settings).

## Three ways to fly

* **Missions**: 12 hand-written relief, medical and time-critical flights.
* **Scheduled network**: 664 realistic cargo routes across 327 stations, grouped
  into US domestic, Americas, Transatlantic, Europe, Middle East & Africa,
  Asia-Pacific and Transpacific. PAC's main hub is Cincinnati (KCVG), with
  gateways at Milan Malpensa, Miami, Dubai World Central, Hong Kong and
  Anchorage. Filter by region or simulator (MSFS or X-Plane),
  search by ICAO, city or cargo, or click a station on the network map. Routes
  added in October 2026 recommend two MSFS and two X-Plane types wherever both
  can fly the sector, so pilots on either simulator find work everywhere.
* **Charter**: pick any two of ~6,300 airports worldwide, any fleet aircraft,
  a cargo type, weight and priority. ACARS warns you if the sector is beyond
  the aircraft's typical range or a runway is shorter than it normally needs,
  but lets you fly it anyway. Charters get PAC8xxx flight numbers unless you
  set your own.

All three use the same SimBrief, ACARS, PIREP and logbook flow.

## Running the airline

* **Pilots** (signed-in pilots only): the roster of everyone at PAC with rank, hours, flights, average score, base,
  where they are now and their last flight; search it and sort it by hours, flights, recent activity or newest.
  Click a pilot for their profile: crew card, type ratings, career figures, recent flights, awards and a map of
  everywhere they've flown. Link to a profile directly with `#pilots/PAC0002`. Nothing private is shown (no email,
  Discord, VATSIM or IVAO details, wallet or settings); staff can open any pilot's flights from their profile.
* **Directory badges**: under the stats band on Home, a "Find us on" strip shows PAC's live VA-List ranking badge,
  linked to PAC's listing (va-list.com/pagani-air-cargo-1231). If the directory can't be reached the strip simply
  hides. Add another directory with one line in `DIRECTORY_BADGES` in `static/app.js`.
* **Home**: the public face of PAC. Liveries, the route network, who's in the air,
  recent arrivals, events, the founder's story and the pilot application form.
  Edit the text in Staff › Site and rules.
* **Applications and onboarding**: applications land in Staff › Applications.
  Approving one creates a pilot on the roster with the next PAC ID. New pilots
  fly the **PAC001 line checkride** (KCVG–KBNA on the 737-800BCF); ACARS grades
  it when the PIREP is filed.
* **Ranks**: Cadet → Second Officer (737, 727) → First Officer (A300) → Senior
  First Officer (MD-11) → Captain (777F) → Senior Captain (747-8F), based on
  hours and average score. Staff can credit transfer hours and switch rank
  enforcement on or off.
* **Events, featured routes and tours**: time-limited point multipliers (Relief
  Week and others, editable in Staff › Events), six featured routes a month at
  ×1.25, and four multi-leg tours with completion bonuses.
* **Rotations**: 18 real freighter working patterns (Hong Kong–Anchorage–
  Cincinnati, the Himalayan circuit through Kathmandu and Paro, the Caribbean
  island hopper, Arctic Norway to Svalbard and more), on their own board tab.
  Legs are flown in order and end where they started; every full lap pays the
  rotation bonus, and a rotation can be flown again as often as you like. Leg
  numbers are PAC9001–9099 and PAC9501–9599. Progress is on the Career page.
* **Awards and leaderboards**: 30 badges and monthly leaderboards on the Career
  page.
* **Airframes**: every aircraft is tracked by registration and stays where it
  lands. Book one that's at your departure airport or ferry one in. Hard
  landings ground the aircraft for inspection, and A-checks come due every
  500 hours. Manage the fleet in Staff › Airframes.
* **PIREP review**: clean flights scoring 80+ are accepted automatically;
  flagged flights wait in Staff › PIREP review. Only accepted flights count
  towards hours, rank, points, awards and leaderboards.
* **Handbook**: the pilot rulebook, generated from the live rules.
* **Departures and arrivals board**: a split-flap board on the home page showing
  your current flight, recent arrivals with landing rates, and today's featured
  departures. Refreshes every 30 seconds.
* **Dispatch paperwork**: every booked flight gets a printable dispatch release
  (ACARS › Dispatch release, or from the PIREP in the logbook): the release with
  crew, fuel and weights from your OFP; a cargo manifest with a loading plan,
  ULDs, air waybills and special handling codes; and a NOTOC when dangerous goods
  are on board. The manifest is generated once at booking so it never changes.
  Print it or save it as a PDF from the browser. For simulation use only.
* **Airline economics**: every flight is a contract priced from the cost of the
  most expensive recommended aircraft plus a markup by kind of work, and pays
  for fuel, fees, handling, crew, maintenance, ownership and overhead, plus any
  incident costs. Each flight's detail panel shows an estimate, each PIREP the
  actual figures, and the **Finance** page shows company cash, profit by aircraft
  type, route and kind of flying, cost breakdown and a ledger. Set the fuel
  price and starting capital in Staff › Site and rules.
* **Pilot pay and jumpseating**: every accepted flight pays an hourly rate by
  rank plus 5% of the flight's profit into your wallet. Your location is where
  your last flight ended; to fly from somewhere else, jumpseat there from the
  Missions page (cheap on a PAC freighter, dearer on an airline ticket). Staff
  can adjust wallets and turn the location rule off in Staff › Site and rules.
* **Fleet management (admin)**: Staff › Fleet types adds new aircraft types
  (specs, SimBrief type, simulator, unlocking rank, photo), edits any type, and
  retires or restores types. Retired types can't be booked but stay in the
  logbook. Staff › Airframes adds, moves and removes individual aircraft.
  Admin changes are stored in `data/fleet_custom.json`, so updates never
  overwrite them.
* **Partners**: FedEx Express, UPS Airlines, Qatar Airways Cargo, Emirates
  SkyCargo, Cathay Cargo and Atlas Air hire PAC captains when they're short of
  qualified crew (Missions › Partners, new requests daily). You fly their
  aircraft under their ICAO code and callsign (FDX, UPS, QTR, UAE, CPA, GTI);
  SimBrief opens with their code and a crew-hire remark. Partner jumpseats run
  across each partner's network. The partnerships are simulated; names and
  logos are trademarks of their owners (credits in `static/partners/CREDITS.md`).
* **Messaging dispatch (ACARS)**: during a tracked flight, send delay reports,
  diversions, fuel checks, ETA requests, fault write-ups and free text to PAC
  Operations, who reply in the ACARS log. Reported delays for causes outside
  your control are excused from late-delivery penalties; declared diversions
  count as diversions rather than failed deliveries. Dispatch also uplinks the
  loadsheet at pushback and your stand at top of descent.
* **Maintenance write-ups**: faults filed under ATA chapters, deferred
  (category B 3 days / C 10 days) or grounding. They follow the tail onto the
  next pilot's paperwork and airframe choice, overdue deferrals ground the
  aircraft, and staff clear them in Staff › Maintenance. Hard landings, tail
  strikes and A-checks open write-ups automatically.
* **Skill bonuses**: up to $475 extra per flight for an A grade, a smooth
  landing, fuel on plan, an on-time and stable approach, and a clean flight.
* **Company news and NOTAMs**: staff post in Staff › News. News shows on the
  home page; company NOTAMs also appear as banners and as ACARS messages when a
  pilot starts tracking.
* **Screenshot gallery**: add screenshots to any PIREP (logbook) or on the
  Gallery page; featured ones lead the home-page gallery. Files are stored in
  `data/gallery` (thumbnails are made if Pillow is installed). Back this folder
  up yourself if you want to keep the images; it isn't in the automatic backups
  to keep them small.
* **Urgent requests**: AOG, medical, production and relief jobs appear about
  every 40 minutes (up to three), each using an aircraft already in position.
  Deliver before the deadline for ×1.5 points and full revenue.
* **Takeoff analysis**: rotation and liftoff speeds, pitch against each type's
  tail-strike limit, ground roll, runway remaining and initial climb, with a
  downloadable takeoff card. Tail strikes cost points and ground the aircraft.
* **Flight integrity**: sim-rate acceleration (over 10 s) and long pauses
  (over 10 min in the air) are detected and sent to staff review.
* **Online flying**: add your VATSIM CID or IVAO VID in Settings. ACARS checks the
  public network feed every 5 minutes in the air; flights seen online for at
  least 60% of checks get a 10% bonus.
* **Promotions and awards**: new ranks and badges are revealed with the patch
  or medal when you file the PIREP.
* **Airframe pages**: click any registration on the Fleet page (or in Staff ›
  Airframes) for its route map, hours, cycles, profit and flight history.
* **Live weather**: METARs and TAFs from the Aviation Weather Center
  (aviationweather.gov, free, no account) on every flight's detail panel, in
  the dispatch paperwork, and coloring the network maps by flight category.
  ACARS sends destination and alternate weather at top of descent, has a **WX**
  button for on-demand reports, and records the wind at touchdown so the landing
  analysis shows the crosswind and headwind for the runway you used. Reports are
  cached for 10 minutes. Needs an internet connection.
* **Backups**: every time ACARS starts it copies the logbook, profile, settings,
  fleet edits and photos into `data/backups` (last 14 kept). Staff › Site and
  rules shows them and has a **Back up now** button. To restore, close ACARS
  and copy the files from a backup folder back into `data`.
* **Pilot license**: Profile › Pilot license draws a two-sided ID card with your
  photo, rank insignia and type ratings. Download front and back as PNG.
* **Flight analysis**: every PIREP records a flight profile and a high-rate
  landing window. The logbook shows the runway you landed on, touchdown
  distance past the threshold, centerline offset, float, approach stability and
  rollout, with profile charts and an animated replay. Each flight has a
  downloadable landing card (PNG) for Discord or social media. Runway data comes
  from OurAirports (`data/runways.json`, rebuilt by `tools/build_airports.py`).

The data model is multi-pilot (every PIREP carries a pilot ID), so it can move to
a hosted server later. Today the pilot ID in Settings is the one flying.

## Fleet by simulator

| Simulator | Types |
|---|---|
| MSFS | 737-800BCF/BDSF, 727-200F, A300-600F, MD-11F, 777F, 747-8F |
| X-Plane | 737-200C Advanced (FlyJSim), 737-300SF (IXEG), 757-200F, 767-300F, 747-200F (FELIS) |

Each type's simulator and add-on can be changed on the Fleet page (Edit), for
example when an X-Plane type becomes available for MSFS. ACARS tracks any type
in either simulator; it only reminds you which one PAC normally uses.

## Simulator support

| Simulator | Connection | Notes |
|---|---|---|
| MSFS 2020 / 2024 | SimConnect (Python `SimConnect` package) | Start the sim and get into the cockpit before starting tracking. |
| X-Plane 11 / 12 | Built-in UDP data interface, port 49000 | No plugin needed. Load into the cockpit before starting tracking. In X-Plane 12, Settings › Network must allow incoming connections on UDP port 49000. Set the address in Settings if X-Plane runs on another PC. |
| Demo | Built-in | Flagged as demo in the logbook and excluded from totals. |

## Flight phases

Telemetry is sampled 4 times a second. Each condition must hold for a short
time so gusts and bounces don't cause false phase changes.

| Phase | Entered when |
|---|---|
| Preflight | Tracking starts at the stand |
| Pushback | Moving with the parking brake off before engines are running (logs **OUT**) |
| Taxi out | Engines running and above 5 kt |
| Takeoff roll | On the ground above 50 KIAS for 2 s (back below 30 kt = rejected takeoff) |
| Initial climb | Wheels off the ground (logs **OFF** and takeoff weight) |
| Climb | Above 1,500 ft AGL; also step climbs out of cruise |
| Cruise | Level (within 400 fpm) for 60 s at 90% or more of the OFP cruise altitude |
| Descent | Descending more than 500 fpm for 20 s (logs top of descent) |
| Approach | Below 2,500 ft AGL, or below 4,000 ft within 20 nm of destination or with gear down |
| Go-around | Climbing over 500 fpm below 3,000 ft AGL on approach |
| Landing rollout | Touchdown (logs **ON**, landing rate and G load; bounces counted) |
| Taxi in | Below 35 kt |
| On block | Stopped, parking brake set, engines off for 5 s (logs **IN**) |

Also recorded: position reports every 10 minutes, 250 kt below 10,000 ft
exceedances, taxi speed above 30 kt, and position jumps (slew or teleport).

## Scoring

Every flight starts at 100.

| Item | Effect |
|---|---|
| Landing softer than −250 fpm | 0 |
| −250 to −400 fpm / −400 to −600 / below −600 | −5 / −15 / −35 |
| Below −1,000 fpm | Flight failed |
| Landing load over 1.8 G / 2.5 G | −10 / −20 |
| Trip fuel over plan by more than 15% / 25% (saving fuel never costs points) | −5 / −10 |
| Landed below final reserve | −15 |
| Landed over max landing weight (up to 5% / more than 5% over) | −10 / −20 |
| Overspeed below FL100 / fast taxi / bounce | −5 / −3 / −5 each |
| Position jump | −15 |
| Diverted to the OFP alternate | −20 |
| Parked anywhere else | −40, flight failed |
| Critical or High priority within 10% of planned block | +5 |
| Late (over 25% for urgent, 35% for standard) | −10 / −5 |

Grades: A 90+, B 80+, C 70+, D 60+, F below. Points = mission reward × score.

## Customizing

* `data/missions.json`: add or edit missions. Airport coordinates drive the
  position checks and the map.
* `data/fleet.json`: aircraft, payload limits and the `simbrief_type` sent to
  SimBrief. If SimBrief doesn't recognize a type, replace it with the code or
  airframe ID from your SimBrief aircraft list.
* **Fleet page**: descriptions, roles, registrations, engines, crew, main deck
  and photos are editable from the Fleet tab (Edit on each aircraft). Your
  edits are stored in `data/fleet_custom.json` and uploaded photos in
  `data/fleet_photos/`, so updating the app never overwrites them. Weights,
  range and runway figures live in `data/fleet.json`.
* `data/routes.json`: the scheduled network. Edit the lanes in
  `tools/build_routes.py` and run `python tools/build_routes.py` to rebuild it
  (distances, recommended aircraft, loads, block times and rewards are
  calculated for you).
* `data/airports.json`: airport database built from OurAirports open data
  (large and medium airports, plus smaller ones with a paved runway of 5,000 ft
  or more). Rebuild with `tools/build_airports.py` if you want fresher data.
* `data/logbook.db`: your PIREPs (SQLite). Back it up to keep your history.
* Port: set the `PAC_PORT` environment variable to run on something other than 5050.

## Joining and letters

Approving an application assigns the next pilot ID, creates the record and opens the **welcome letter**
(`letters.py`: plain text and HTML, with the pilot ID, a one-time sign-in link, first steps and the Discord invite).
Declining opens a decline letter; Staff › Roster › Letter sends a fresh sign-in link.
**PAC can send the letters itself** (`mailer.py`): give it the airline's mailbox under Staff › Site and rules › Email
(app password for Gmail/Outlook; server settings filled in for common providers) and approving sends the welcome
letter straight away. Sending never blocks approval: if mail fails, the pilot is created and the letter opens to copy.
The password is kept in settings.json and never sent to the browser. Set the public address,
Discord invite and signature under Staff › Site and rules › Letters and links. Edit the wording in `letters.py`.

## Who sees what

**Visitors** see Home, Fleet, Gallery and the Handbook, can apply to fly and sign in. Every other page and API asks
them to sign in first. The founder's profile is the airline's public face on Home; other pilots' photos are for
members only.

**Pilots** get every page except Staff (which isn't in their menu, and sends them to Home if they type the address).
They change only their own things: their profile (photo, biography and secondary base; name, pilot ID, rank,
title, callsign, home base, join date, type ratings and credentials come from their record, ratings and staff), their SimBrief, VATSIM and IVAO details and map style, their bookings and their own screenshots. Their logbook shows only their own flights (staff can open anyone's).

**Staff only:** the Staff area, airline rules and economics, editing fleet types, deleting PIREPs, featuring
screenshots on Home, and anything under `/api/staff/`. The server enforces all of this, not just the menu.
`python tests/test_permissions.py` tries every route as a visitor and as a pilot.

## Discord bot

**PAC Operations** (`discord_bot.py`) is PAC's Discord bot, running on the server as the `pac-discord` service
(set-up: deploy/DEPLOY.md, section 10). Commands: `/flights` (latest flights), `/live` (who's flying, with the live
map link), `/pilot` (a pilot's card), `/link CODE` and `/unlink`. Pilots get a link code in **Settings**; once
linked they get the **PAC Pilot** role, a role named after their PAC rank (updated on promotion) and **PAC Staff**
if they're staff. It posts accepted PIREPs in the flights channel, promotions, new pilots, shop purchases and new
liveries in the news channel, and welcomes people who join.

**The dispatch channel** (#dispatch by default): every minute the bot asks PAC for new work and posts it as a card:
new missions, partner crew requests (with the partner's callsign and shortage bonus) and urgent requests (with a
deliver-by time, shown in each reader's own time zone). Each card links to the mission board. Asking also keeps the
boards moving, so new work keeps appearing even when nobody has signed in. Urgent requests go first, then crew
requests, then missions, up to the hourly limit (4 by default); anything over the limit is skipped rather than
queued. Choose the channel, the kinds of work and the limit under **Discord bot › Dispatch channel**; leave the
channel empty to switch it off. When the bot starts it doesn't repost what's already on the board. Everything is set in **Staff › Site and rules › Discord bot**. The bot
talks to PAC over a private API (`botlink.py`) protected by `data/bot_secret`, which never leaves the server.

## Flying online: PGC

PAC is Polar Air Cargo's ICAO code, so on VATSIM and IVAO PAC flights are filed under PAC's own network code, **PGC**
by default (Staff › Site and rules › Flying online). The SimBrief link fills in PGC and the flight number, with
`CALLSIGN PAGANI` in the remarks so controllers say "Pagani 9613"; the mission page and the dispatch release
(**ATC FPL** line) tell pilots what to connect as. Everything on the website, in PAC ACARS and on Discord keeps the
PAC number (PAC9613): a plan filed as PGC9613 is booked as PAC9613. Partner crew requests are filed under the
partner's own code, as before.

After importing a valid SimBrief plan, the planning screen and **My bids** can prepare the VATSIM filing details,
including PAC's network callsign and remarks, for copying into the pilot's VATSIM client. PAC does not submit plans
directly to VATSIM.

**VATSIM logo.** Once VATSIM accepts PAC as a Virtual Airline Associate or Partner, its policy asks for the VATSIM logo
on the home page or in a clearly marked Partners section, linked to www.vatsim.net. PAC includes the official no-tagline
logo from VATSIM's public logo pack (`static/partners/vatsim-logo.svg`, unaltered; see `static/partners/CREDITS.md`),
ready to show in a **Network partners** section on a white tile with the clear space VATSIM's brand guide asks for. It
is **off by default**: switch it on under Staff › Site and rules › Flying online only once VATSIM has accepted PAC,
since showing it earlier suggests a partnership PAC doesn't have. If VATSIM updates its logo, upload the
new file from vats.im/logo under Staff › Site and rules › Flying online; removing the upload goes back to the
built-in one.

## Liveries

Each aircraft on the **Fleet** page has a **Liveries** section that credits the painter. Staff press **Add livery**
on the aircraft and either upload the file (.zip, .7z or .rar, up to 600 MB; signed-in pilots download it) or link to
where the painter hosts it (flightsim.to, X-Plane.org and the like; open to everyone). Add the painter's name and,
if they like, a link to their page, the simulator and add-on aircraft, a version, a registration, a preview picture
and install notes. The top of the Fleet page thanks every painter by name, downloads are counted, and the Discord
bot announces each new livery in the news channel. Types without a livery invite painters to get in touch (through
the Discord invite in Site and rules, when it's set). Liveries are kept in `data/liveries.json` and
`data/liveries/`, and are part of the full backup. For files over 600 MB, link to them instead or raise
`PAC_LIVERY_MAX_MB` (Caddy allows uploads up to 2 GB).

## Live map

**Live map** shows everyone flying for PAC right now: a plane for each flight, pointing the way it's heading, with
its track so far. Click one for the pilot, route, aircraft, cargo, altitude, speed and distance to go, and a line to
the destination. Positions come from PAC ACARS and refresh every 10 seconds; a flight leaves the map when it's handed
over on block, or after two minutes without a report. Members always see it. Staff can switch on **Live map on the
public site** in Site and rules, and visitors then see flight numbers, aircraft, routes and positions, never pilots'
names, registrations or cargo.

## The PAC shop

Pilots spend their wallet earnings (flight pay, profit share and bonuses) in **Shop**, sorted into tabs:
**Passes**: jumpseat passes (a free trip from the Jumpseat window, hold five), the **hard landing pass** (turns one of
your own PIREPs from the last 14 days that was held or rejected only for its landing into an accepted, paid flight)
and **fleet passes** (7 or 30 days flying any type regardless of rank or ratings, after the line checkride).
**Pilot gear**: logbook, flight bag, EFB, headset, chronograph, motorbike and the hypercar, each adding 1–5% to the pay
of every flight for 90–365 days (all gear together tops out at +10%; buying again extends it). **Patches** and **crew
badge frames** for the profile and crew badge (hover a patch to see what it is). **Aircraft**: repositions ($500 plus
$0.25 per nm, also in the airframe picker) and **naming rights** ($40,000). **My purchases** lists what each pilot owns
and when it runs out. Prices live in `shop.py`. Staff can close the shop in Site and rules and remove an unsuitable
airframe name from the Airframes tab.

Pilots see a short **Finance** summary: company cash, profit, what's been shared with pilots and their own share.
Staff keep the full books.

## SayIntentions.AI

PAC is in the SayIntentions.AI Virtual Airline Alliance. In **Staff › Site and rules › SayIntentions.AI**, paste
PAC's VA-Link key from the VA Manager page, the members' coupon code and the dispatcher frequency, add any airline
notes for the AI, and switch it on. From then on, whenever a pilot books, changes, cancels or finishes a flight, PAC
sends their AI dispatcher, cabin crew, co-pilot and SkyOps a briefing: the flight number and PAGANI callsign, route,
cargo, priority, deadline, aircraft and registration, PAC stands, open maintenance items, the SimBrief plan if
imported, PAC's fuel price and procedures. Pilots link their SayIntentions account by flying with PAC ACARS 1.0.2 or
newer (it reads `%LOCALAPPDATA%\SayIntentionsAI\flight.json`) or by pasting their SayIntentions API key on the
Downloads page, which also shows the coupon code to members. PAC's VA key never leaves the server.

## Giving pilots the ACARS app

Build on Windows with `acars_client\build\build_acars.bat` (it writes `acars_client/site_url.py` from `PAC_SITE`,
so the build points at your website), then upload the installer or portable zip in **Downloads** as staff. Builds
live in `data/acars-builds/`, so server updates never remove them, and they're served to signed-in pilots only.

Pilots' copies always use `https://pac-va.com` unless the pilot types another address in Settings. A copy left
pointing at a test website on the same PC (such as `http://127.0.0.1:5050`) that isn't running switches to
pac-va.com by itself, says so, and asks the pilot to sign in; an address typed in Settings is never changed
automatically, but the window offers a **Use pac-va.com** button whenever the website can't be reached. Run from
source (`start_acars.bat`), the app still talks to the website on your own PC. Test:
`python tests/test_acars_site.py`.

## Putting PAC online

`deploy/DEPLOY.md` is a step-by-step guide (server, DNS, HTTPS, service, backups). With `PAC_PUBLIC=1`, PAC runs on
waitress instead of Flask's development server, marks cookies secure, trusts the proxy's forwarded address (so
sign-in rate limiting sees real visitors), sets security headers and caps uploads (`PAC_MAX_UPLOAD_MB`).
`deploy/` also holds a Caddyfile (automatic HTTPS), a systemd service, a nightly backup script and a server
updater that backs up, replaces program files only and restarts.

## Several pilots at once

PAC is no longer single-pilot. Bookings live in the `bookings` table (one row per pilot), each pilot has their own
flight session (`SESSIONS` in app.py; `state` points at the current request's), in-progress flights are saved per
pilot in `data/flights/<pilot>.pkl`, the SimBrief watcher runs for every waiting pilot, and each pilot keeps their
own SimBrief username (`pilots.simbrief`). An older single-pilot `data/booking.json` is moved to its owner on first
start. Test: `python tests/test_multipilot.py`.

## Removing a pilot

Staff › Roster › **Remove**: shows the pilot's footprint, asks for the pilot ID as confirmation, then deletes the
account, password, invites, API keys, ratings, goals and wallet, and releases bookings. Flights are either kept in
airline history under `EX-<id>` or deleted outright. Staff can't remove themselves or the last staff account, and
pilot IDs are never reused (`next_pilot_id` reads every ID ever issued). The **Reuse pilot IDs** switch
(Staff › Site and rules) is a testing aid: while it's on, the lowest free ID is handed out so the same test
application can be approved repeatedly. Turn it off before going live.

Staff › Applications can be tidied: **Delete** removes one application, and **Clear old applications** removes
every reviewed one from people who aren't on the roster (declined applicants, and pilots since removed, such as test
pilots). A current pilot's application is their joining record and is always kept, as are applications still
waiting for review. Removing a pilot already detaches their application, so clearing never lets a pilot ID be reused.

## Crew badge

The profile page shows a virtual airport ID badge on a PAC lanyard: photo, name, rank, pilot ID, base, issue and
expiry dates, access areas, type ratings and a badge number. Click to turn it over; "Download badge" saves a PNG.

## Station guides and downloads

* **Stations**: a guide for every PAC airport (satellite map with runways, live weather, runways and which PAC
  aircraft fit, your record, chart links). **KCVG** has a full, sourced guide: cargo operation, runways, frequencies,
  procedures, winter operations and PAC's (fictional) stands P1 to P8 on the south cargo complex, which ACARS assigns.
  The other hubs have PAC stands too (Hong Kong on real published cargo stands X12 to X17; Miami, Malpensa, Dubai World
  Central and Anchorage on their cargo areas, for staff to fine-tune).
  Guides live in `stations.py`; add one for any airport the same way.
* **Downloads**: PAC ACARS, a staff-managed library (checklists, documents, scenery; files in
  `data/downloads/`, kept through updates and in full backups), SimBrief airframe sheets for every type, and the
  handbook and station guide to print. Liveries have their own home on the Fleet page, with the painter's credit
  (see Liveries).

## Stands

PAC suggests a departure stand when you book from a hub with PAC stands (never enforced: where you park isn't
scored, flagged or reviewed) (by aircraft size), shown on the flight page,
My bids, the dispatch release and the ACARS page; PAC ACARS confirms it at logon and sends the arrival stand at top
of descent. Each airframe remembers the stand it parked on (`airframes.stand`), so it departs from there next time,
and PAC picks a free stand big enough when another aircraft is on it.

## A living mission board

* **Missions** come from `missiongen.py`: about 30 kinds of real air-cargo work, many seasonal (Valentine's roses
  from Bogotá, cherries before Chinese New Year, hurricane and monsoon relief, Beaujolais Nouveau, the Antarctic
  season), plus year-round work (vaccines, AOG engines and parts, satellites, racehorses, mail, pharma). About 14 are
  open at a time, each for 1.5 to 6 days; some always leave from where you are; a route doesn't repeat within ten
  days; the hand-written missions in `data/missions.json` return from time to time.
* **Challenging airports**: high and hot (La Paz, Cusco, Leh, Lhasa), terrain and valley approaches (Kathmandu, Paro,
  Innsbruck, Sion, Aspen, Juneau), short runways (Gibraltar, St Maarten, Jackson Hole), the Arctic (Svalbard, Resolute
  Bay's gravel strip, Utqiagvik, Nuuk) and remote islands with no alternate (Easter Island, the Galápagos). Each
  mission says what makes the airport hard, in the briefing and in a note in the dossier, and pays 20% more.
* **Special cargo**: lithium batteries and other dangerous goods, livestock and zoo animals, gold and banknotes,
  outsize loads and touring stage rigs. Each comes with handling notes for the pilot.
* **Ferry and positioning**: heavy-maintenance ferries, fresh-paint ferries, factory deliveries from Everett and
  Boeing Field (777F, 747-8F and 767 only), seasonal desert storage and empty legs for charters. No cargo; they pay
  your hourly rate plus the ferry bonus.
* **Partner crew requests** arrive through the day (4 to 8 open, a new one every 45 to 120 minutes), each open for
  8 to 30 hours, with cargo that fits the partner.
* Add your own kinds of work by adding a scenario to `missiongen.py`. Optional fields: `ferry` (no cargo),
  `types` (only these aircraft), `challenge` (uses the airport notes in `CHALLENGES`) and `handling`.

## Pagani Aviation Group hub and PRA

* **Group feed** (`/api/group/v1/summary`) and **METARs** (`/api/group/v1/metar`) for the group hub and PRA's
  go/no-go. Both are off until staff switch on *Share PAC with the group hub* in Staff › Site and rules ›
  Pagani Aviation Group, and both answer only requests carrying the group key (`X-Group-Key`). The feed shares
  names, ranks, hours and recent flights, never emails, Discord, network IDs or wallets. **New key** stops the old
  one at once.
* **PRA tick box** in Staff › Roster for pilots cleared to fly the Kodiak.
* **Village freight:** PAC flights into Anchorage carry a few pieces for PRA strips, printed on the cargo manifest
  under "Onward to Pagani Remote Aviation".

## Updating

`deploy/update.sh` replaces the program files and leaves everything you've made alone (logbook, settings, pilots,
uploads, backups). It also copies PAC's reference data from the zip (`routes.json`, `airports.json`,
`runways.json`, `fleet.json`, `missions.json`, `partners.json`), so new routes and missions arrive with the
update. Always install the newest zip: an update makes the program match the zip exactly.

## The line checkride

* PAC001 passes with a score of 80 or more, a landing softer than 400 fpm and under 1.5 G, no bounce, and no
  overspeed (250 kt below FL100) or slew. Any one of those fails it, whatever the score.
* The result is recorded when the PIREP is filed. Accepting the PIREP pays it but doesn't change the result.
  Staff see "Line checkride not passed" and the reasons on the PIREP in review, and the pilot sees them on Career.
* If a failing penalty was ACARS misreading something, waive it in review: the checkride is checked again and,
  if it now passes, the pilot is promoted at once. Staff can also set the checkride to Passed or Waived in the roster.

## News and NOTAMs on Discord

* Posts from Staff › News go to Discord through the PAC bot when **Post it to Discord too** is ticked (it is for new
  posts). Company NOTAMs go to the NOTAM channel (`notams` by default, set in Staff › Discord bot) numbered for the
  year, like `NOTAM 004/26`; news goes to the announcements channel. Edits are only reposted when you tick the box.
* The bot needs View Channel, Send Messages and Embed Links in both channels.
* Keep NOTAMs short. Long ones are cut short in the home-page banner; use News for announcements.

## Dispatch paperwork, goals and Discord

* **Dispatch release**: printed like real operational paperwork (Courier, fixed columns): release, navigation log,
  weather and NOTAMs, loadsheet, cargo manifest and NOTOC, each with form number, barcode and page count.
  "Classic layout" on its toolbar shows the previous design.
* **Goals** (My stats): targets for hours, flights, distance, cargo, new airports or countries, A grades or soft
  landings, per month, per year, by a date or in total.
* **Discord** (Staff › Site and rules): a channel webhook posts departures and arrivals; landing cards and recaps can
  be posted with one click. The webhook address stays on the server.

## Approach profile, live traffic and weather radar

* **Approach profile** (logbook › any flight): the final approach against the ideal 3° glidepath by distance,
  a one-dot band, speed and sink rate, and how you crossed the 1,000, 500 and 200 ft gates. Works for past
  flights too (it uses the flight profile every PIREP already keeps).
* **Live traffic and radar** (ACARS map): VATSIM or IVAO traffic around you and RainViewer precipitation radar.
* **PAC ACARS** follows the Load Sheet design too (its Settings › Design switches back to Classic).

## Type ratings and the planning helper

* **Type ratings**: each aircraft family (737, 727, A300, MD-11, 757/767, 777, 747 classic, 747-8) needs a
  rating before regular flying. Earn one with a short checkride from where you are (Career › Type ratings ›
  Book checkride): score 85+, softer than 400 fpm, no bounce, stable approach. Types you've already flown
  count; the 737 family comes with the line checkride. Staff can grant or remove ratings (Roster › Ratings)
  or switch the requirement off (Site and rules).
* **Planning helper** (every flight page): suggested cruise level (odd/even for your direction), fuel
  estimate, the runways most likely in use from the current wind, and an alternate. It can pre-fill the
  cruise level and alternate in SimBrief.

## My stats, recap, collection, automatic OFP and dark mode

* **My stats** (More › My stats, or from Career): totals, a map of every route and airport you've flown,
  hours by aircraft, flights per month, records (click one to open that flight) and streaks.
* **Monthly recap**: your month in review on the My stats page, downloadable as an image.
* **Airport collection**: milestones for 10/25/50/100 airports, 5/10/25 countries and six continents,
  shown on Career and earned as awards.
* **Automatic OFP**: after "Open SimBrief with this mission", your new plan is imported by itself. Booked
  without a plan? PAC watches SimBrief for up to 90 minutes and attaches it (dispatch paperwork included).
* **Dark mode**: Settings › Appearance (automatic, light or dark), per computer.

## Signing in

Pilots sign in with their PAC pilot ID and a password. The first time you open the site after this
update, it asks you to choose a password for your existing pilot record (PAC0001): your logbook,
career and settings stay exactly as they are. Visitors see the home page, fleet, gallery and handbook,
and can apply; everything else needs signing in, and Staff needs a staff account.

* New pilots: approve their application, then send them the **welcome link** it shows.
* Forgotten password: Staff › Roster › **Sign-in link** for that pilot.
* Change your own password in Settings.
* PAC ACARS signs in once and stays signed in (sign out in its Settings).

## Your data, backups and updates

Everything that's yours lives in `data/` (logbook, settings, profile and photo, home-page text,
fleet edits and photos, gallery, backups, sign-in key) and in `%APPDATA%\PAC ACARS` (the app).
Updates never replace these.

* **Update safely:** drag the new `pac-acars.zip` onto **update.bat** (close the website first). It
  backs up your data, updates only the program files, and installs any new Python packages.
* **Full backup:** Staff › Site and rules › **Download a full backup** gives one zip with everything;
  **Restore from a backup** puts it back (your current data is backed up first). Use it to keep a copy
  somewhere safe or to move PAC to another computer or a server.
* Automatic backups of the logbook and settings are made every time the website starts (last 14 kept).

## The PAC ACARS app

Flights can be tracked by a separate app that runs next to your simulator:

```
start_acars.bat            (Windows)   or   python acars_client/client.py
```

Keep the PAC website running (`start.bat` / `python app.py`) and book a flight there.
On the website's ACARS page, **Open in PAC ACARS** launches the app (or brings it to
the front) with the flight loaded and the right simulator selected, using a
`pacacars://` link that the app and its installer register with Windows. Then press
**Start tracking** in the app. All tracking happens in the app; the website follows
the flight live and scores it. The app reads MSFS or X-Plane, handles
dispatch messages, weather and online checks, keeps the website's ACARS page
updated live, and on block hands the flight record to the website, which scores
it. File from the app or from the website. If the app or your PC restarts
mid-flight, reopen it and press **Resume flight**.

**As a Windows program:** double-click `acars_client\build\build_acars.bat` to build
`PAC ACARS.exe`, a portable zip and an installer; the website then offers them on its
ACARS page. See `acars_client/build/BUILD.md`.

PAC ACARS shows itself in a Microsoft Edge app window (Chrome if Edge is missing), which it controls and
watches: if the window ever freezes, it's replaced within seconds and tracking carries on. The app's
Settings › Window can switch to the built-in window instead.

It judges the window by the window itself and by the page checking in every second, not by the
`msedge.exe` it started: Edge often hands a new app window to a copy of Edge that's already running
and exits straight away. Before opening its window, PAC ACARS closes any Edge still running on its own
private window profile (never your normal browsing), and if a PAC ACARS window from before is still
open it simply uses that one. Its log, `%APPDATA%\PAC ACARS\acars.log`, keeps one older copy
(`acars.old.log`) and starts afresh at 2 MB, and leaves out the once-a-second check-ins.

**1.0.5:** sim rate is ignored while you're parked at the stand (on the ground and slower than 3 kt), so you
can speed up loading and unloading a heavy. Taxiing or flying above 1× for more than 10 seconds still goes to
staff review.

**1.0.4:** fixes "Failed to fetch" on **Start tracking**. In 1.0.3, Edge handing the window on looked
like the window closing, so the app's engine stopped about five seconds after opening while the window
stayed on screen; the window it left behind caused the same on every later start.

From source, the built-in window is used if `pywebview` is installed (`pip install pywebview`),
otherwise in your browser at http://127.0.0.1:5070. Its settings (website address,
X-Plane address) are in the Settings panel and saved to `acars_client/config.json`.

## Checks

See `ARCHITECTURE.md` for how the code fits together. Before shipping changes:

```
python tests/test_flights.py      # scripted flights through the real tracker and scoring
python tools/check_frontend.py    # JavaScript syntax (needs Node.js)
python tests/test_acars_window.py # PAC ACARS window supervision (frozen window replaced; tracking never stops)
python tests/test_acars_handoff.py # Edge handing the window on, a window left from before, Edge lingering on the window profile
python tests/test_acars_build_upload.py # uploading a PAC ACARS build on the Downloads page
python tests/test_acars_site.py         # PAC ACARS never stuck on a website address that isn't running
python tests/test_permissions.py        # what visitors, pilots and staff can see and do
python tests/test_mail_ports.py         # email when the server's host blocks ports 465 and 587
python tests/test_shop.py               # the PAC shop and the pilots' Finance summary
python tests/test_liveries.py           # liveries on the Fleet page: files, links, painter credit, downloads
python tests/test_applications.py       # deleting and clearing old applications; pilots' records and IDs are safe
python tests/test_dispatch_channel.py   # the Discord dispatch channel: new work, card wording, hourly limit
python tests/test_filing_code.py        # PGC on the networks, PAC on the website; Discord invite and site address
python tests/test_network_logo.py       # the VATSIM logo on the home page: upload, safe serving, removal
python tests/test_flight_cards.py       # landing and takeoff cards credit the pilot who flew, in their simulator
python tests/test_pilots_page.py        # the Pilots roster and profiles: members only, nothing private
python tests/test_sayintentions.py      # SayIntentions.AI VA-Link briefings (against a stand-in server)
python tests/test_live_map.py           # who appears on the live map, and what visitors may see
python tests/test_discord_bot.py        # the Discord bot: linking, roles, announcements and its private API
python tests/test_navigraph.py          # the Navigraph Charts button gets the SimBrief plan
python tests/test_gate_departure.py     # the flight starts when the aircraft leaves the gate (brakes, tugs, sim loading)
python tests/test_acars_app.py    # PAC ACARS app: every button during a live flight, slow weather service (needs Playwright)
python app.py  &  python tools/smoke_test.py   # every API endpoint
```
