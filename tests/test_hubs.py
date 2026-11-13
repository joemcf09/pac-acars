"""Opening and closing hubs from the CEO desk: costs, every module's hub list, monthly station costs, founding hubs protected."""
import os, sys, tempfile
os.environ.setdefault("PAC_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
from werkzeug.security import generate_password_hash
import hubs, va, trips, cargo_orders, aog, ceo, warehouses, shipments, company

with A.db() as con:
    if not con.execute("SELECT 1 FROM pilots WHERE id='PAC0001'").fetchone():
        con.execute("INSERT INTO pilots (id, name) VALUES ('PAC0001','J')")
    con.execute("UPDATE pilots SET password_hash=?, staff=1, status='Active' WHERE id='PAC0001'", (generate_password_hash("x"),))
c = A.app.test_client()
with c.session_transaction() as s: s["pid"] = "PAC0001"

assert "hub_network" in c.get("/api/staff/ceo").get_json()
r = c.post("/api/staff/ceo/hub", json={"icao": "EDDP"}); assert r.status_code == 200, r.get_json()
for lst in (va.LIVE_HUBS, trips.HUBS, cargo_orders.HUBS, aog.HUBS, shipments.PAC_HUBS, ceo.HUBS, warehouses.HUBS):
    assert "EDDP" in lst, lst
assert "EDDP" in c.get("/api/bootstrap").get_json()["hubs"]
assert c.post("/api/staff/ceo/hub", json={"icao": "EDDP"}).status_code == 400          # already a hub
assert c.post("/api/staff/ceo/hub", json={"icao": "ZZZZ"}).status_code == 400          # unknown
assert c.post("/api/staff/ceo/hub", json={"action": "close", "icao": "KCVG"}).status_code == 400
with A.db() as con:
    assert con.execute("SELECT amount FROM company_ledger WHERE kind='hub_opening'").fetchone()[0] == -hubs.OPEN_COST
    con.execute("UPDATE hubs_opened SET last_billed='2000-01'")
    hubs.tick(con); hubs.tick(con)
    assert con.execute("SELECT COUNT(*) FROM company_ledger WHERE kind='hub_station'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM news WHERE title LIKE 'PAC opens a new hub%'").fetchone()[0] == 1
assert c.post("/api/staff/ceo/hub", json={"action": "close", "icao": "EDDP"}).status_code == 200
assert "EDDP" not in va.LIVE_HUBS and "KCVG" in va.LIVE_HUBS
print("HUBS TEST PASSED")
