"""PAC flies on VATSIM and IVAO under its own network code (PGI by default: PAC is Polar Air Cargo's ICAO code),
while the website keeps showing PAC flight numbers. Also checks that the Discord invite and website address are read
from the home-page settings, where staff enter them.

Run from the PAC folder:   python tests/test_filing_code.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "booking.json", "bot_secret"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import botlink  # noqa: E402
import va  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Filing-Code-Test-1"})

print("The network code")
check("PGI by default", A.filing_icao() == "PGI")
check("pilots' browsers are told it", c.get("/api/bootstrap").get_json()["settings"].get("filing_icao") == "PGI")
for bad in ("12", "PG", "PGIX", "p-c"):
    check(f"a bad code ({bad!r}) falls back to PGI", A.filing_icao({"filing_icao": bad}) == "PGI")
check("staff can change it", c.post("/api/settings", json={"filing_icao": "PGI"}).status_code == 200)
check("the SimBrief airframe sheets use it", va.simbrief_sheet("B738F")["airline"] == "PGI", va.simbrief_sheet("B738F").get("airline"))

print("Flight numbers on the website stay PAC")
check("a plan filed as PGI shows as PAC", A.site_flight_number({"airline": "PGI", "flight_number": "9613"}, "PAC9613") == "PAC9613")
check("so does a plan with no airline", A.site_flight_number({"airline": "", "flight_number": "9613"}, "PAC9613") == "PAC9613")
check("a partner's plan keeps the partner's code", A.site_flight_number({"airline": "GTI", "flight_number": "5988"}, "GTI5988") == "GTI5988")
check("no plan: the mission's own number", A.site_flight_number(None, "PAC1022") == "PAC1022")

print("Booking with a PGI plan, end to end")
c.post("/api/settings", json={"enforce_pilot_location": False})
r = c.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": "B733F", "airframe": "N010PC",
                                  "ofp": {"airline": "PGI", "flight_number": "1022", "origin": "KCVG", "destination": "KBNA"}})
check("the booking is made", r.status_code == 200, r.get_data(as_text=True)[:300])
b = A.load_booking() or {}
check("and shows as PAC1022", b.get("flight_number") == "PAC1022", b.get("flight_number"))
d = c.get("/api/dispatch").get_json() or {}
check("the dispatch release gives the ATC callsign to file", d.get("paper", {}).get("atc_callsign") == "PGI1022", d.get("paper", {}).get("atc_callsign"))
check("and keeps the radio callsign PAGANI", str(d.get("paper", {}).get("callsign", "")).startswith("PAGANI"), d.get("paper", {}).get("callsign"))
check("a partner flight files under the partner's code",
      A.atc_callsign({"flight_number": "GTI5988", "mission": {"id": "GTI5988", "operator": {"code": "GTI"}}}) == "GTI5988")
c.delete("/api/booking")

print("Home-page settings reach the Fleet page and the bot")
A.save_json(DATA / "site.json", {"discord_invite": "https://discord.gg/pac", "public_url": "https://fly.example.com/"})
check("the Fleet page gets the Discord invite", c.get("/api/fleet").get_json().get("discord_invite") == "https://discord.gg/pac")
check("so does the liveries list", c.get("/api/fleet/liveries").get_json().get("discord_invite") == "https://discord.gg/pac")
cfg = c.get("/api/bot/config", headers={"X-PAC-Bot": botlink.secret()}).get_json()
check("the bot links to the website address staff entered", cfg.get("site") == "https://fly.example.com", cfg.get("site"))
(DATA / "site.json").unlink(missing_ok=True)
check("without one it falls back to pac-va.com",
      c.get("/api/bot/config", headers={"X-PAC-Bot": botlink.secret()}).get_json().get("site") == "https://pac-va.com")

print("\nFILING CODE TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
