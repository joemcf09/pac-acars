"""End-to-end exception decisions in an isolated PAC data directory."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-ops-exceptions-") as temp:
        data = Path(temp) / "data"
        data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        env = dict(os.environ, PAC_DATA_DIR=str(data))
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=env).returncode)

sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import aog  # noqa: E402
import auth  # noqa: E402

founder = A.app.test_client()
assert founder.post('/api/auth/setup', json={'password': 'Exceptions-Test-123'}).status_code == 200
now = time.time()
with A.db() as con:
    for pid in ('PAC0014', 'PAC0015'):
        con.execute("""INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location)
            VALUES (?,?,?,?,?,'Active','Passed',0,'KCVG')""",
            (pid, f'Test {pid}', f'{pid}@example.com', 'KCVG', now))
auth._set_password('PAC0014', 'Pilot-Test-123')
pilot = A.app.test_client()
assert pilot.post('/api/auth/login', json={'pilot_id': 'PAC0014', 'password': 'Pilot-Test-123'}).status_code == 200
assert pilot.get('/api/staff/ops-exceptions').status_code == 403

sid = 'a' * 32
with A.db() as con:
    con.execute("""INSERT INTO cargo_shipments (id,awb,booking_key,source_awb,origin,destination,
        current_station,status,shipper,consignee,commodity,pieces,gross_weight_lbs,priority,handling,
        data,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, '901-10000123', 'old-booking', '901-10000123', 'KORD', 'KMIA', 'KCVG',
         'HELD_AT_STATION', 'Shipper', 'Consignee', 'Medical kits', 10, 1200, 'Priority', '[]',
         json.dumps({'deadline': now + 3600}), now - 1000, now))
    con.execute("""INSERT INTO cargo_movements (shipment_id,event_key,event_type,event_time,
        from_station,to_station,pilot_id,flight_number,pirep_id,status,details)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, 'test-divert', 'FLIGHT_ARRIVAL', now - 60, 'KORD', 'KCVG',
         'PAC0014', 'PAC9635', 999, 'HELD_AT_STATION', '{}'))
    aog.init(con)
    con.execute("""INSERT INTO aog_cases (reg,type,station,kind,title,kit,item_ids,cause_flight,
        opened,status,mission_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        ('N123PC', 'B744F', 'KCVG', 'hard_landing', 'Hard landing inspection', '{}', '[]',
         'PAC9635', now, 'awaiting_parts', 'PAC8801'))

desk = founder.get('/api/staff/ops-exceptions').get_json()
diversion = next(c for c in desk['cases'] if c['kind'] == 'diversion')
aog_case = next(c for c in desk['cases'] if c['kind'] == 'aog')
assert diversion['shipments'][0]['awb'] == '901-10000123'
assert aog_case['mission_id'] == 'PAC8801'
url = f"/api/staff/ops-exceptions/{diversion['key']}/decision"
hold = {'choice': 'hold', 'note': 'Keep medical freight chilled at Cincinnati.'}
assert pilot.post(url, json=hold).status_code == 403
assert founder.post(url, json={**hold, 'note': 'short'}).status_code == 400
first = founder.post(url, json=hold)
assert first.status_code == 200 and first.get_json()['sent'] == 1
assert founder.post(url, json=hold).get_json()['duplicate']
with A.db() as con:
    assert con.execute("SELECT status,current_station FROM cargo_shipments WHERE id=?", (sid,)).fetchone()[:] == ('HELD_AT_STATION', 'KCVG')
    assert con.execute("SELECT COUNT(*) FROM messages WHERE recipient='PAC0014'").fetchone()[0] == 1

A.save_booking({'mission': {'origin': {'icao': 'KCVG'}, 'destination': {'icao': 'KMIA'}},
                'flight_number': 'PAC4321', 'aircraft': 'B744F', 'requested_at': now},
               'PAC0015', notify=False)
onward = {'choice': 'onward', 'target_pilot': 'PAC0015', 'target_flight': 'PAC4321',
          'note': 'Collect the held medical kits before departing Cincinnati.'}
assert founder.post(url, json={**onward, 'target_flight': 'PAC0000'}).status_code == 409
assert founder.post(url, json=onward).status_code == 200
with A.db() as con:
    assert con.execute("SELECT status,reserved_booking_key FROM cargo_shipments WHERE id=?", (sid,)).fetchone()[:] == ('HELD_AT_STATION', None)
    assert 'PAC4321' in con.execute("SELECT body FROM messages WHERE recipient='PAC0015'").fetchone()[0]

recovery = founder.post(f"/api/staff/ops-exceptions/{aog_case['key']}/decision", json={
    'choice': 'recovery', 'target_pilot': 'PAC0015',
    'note': 'Take the inspection kit to the grounded aircraft.'})
assert recovery.status_code == 200
with A.db() as con:
    assert 'PAC8801' in con.execute("SELECT body FROM messages WHERE recipient='PAC0015' ORDER BY id DESC").fetchone()[0]
    con.execute("UPDATE aog_cases SET status='repairing' WHERE id=?", (int(aog_case['key'].split(':')[1]),))
    con.execute("UPDATE cargo_shipments SET status='AT_STATION' WHERE id=?", (sid,))
assert founder.post(url, json=hold).status_code == 409
assert founder.post(f"/api/staff/ops-exceptions/{aog_case['key']}/decision", json={
    'choice': 'recovery', 'target_pilot': 'PAC0015',
    'note': 'Take the inspection kit to the grounded aircraft.'}).status_code == 409
assert not any(c['kind'] == 'diversion' for c in founder.get('/api/staff/ops-exceptions').get_json()['cases'])

with A.db() as con:
    con.execute("INSERT INTO roles (pilot_id,role,note,since) VALUES (?,?,?,?)",
                ('PAC0014', 'dir_ops', 'Test operations scope', now))
assert pilot.get('/api/staff/ops-exceptions').status_code == 200
assert pilot.get('/api/staff/overview').status_code == 403
print('ops exception desk checks passed')
