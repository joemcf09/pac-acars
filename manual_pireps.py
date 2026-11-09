"""Staff-reviewed untracked flights. No telemetry or score. On approval, staff may also complete the flight:
deliver its booked cargo, move the aircraft and pilot to the arrival airport and close the booking."""
import base64, binascii, json, re, time
from datetime import datetime, timezone
from flask import request, jsonify, Response


def migrate(con):
    con.execute('CREATE TABLE IF NOT EXISTS manual_pirep_evidence (pirep_id INTEGER PRIMARY KEY, mime TEXT NOT NULL, image BLOB NOT NULL)')


def review(va, report_id, body):
    import auth
    if not auth.is_staff():
        return jsonify(error='Staff only.'), 403
    with va.C['db']() as con:
        con.execute('BEGIN IMMEDIATE')
        r = con.execute('SELECT * FROM pireps WHERE id=?', (report_id,)).fetchone()
        if not r or r['source'] != 'Manual':
            return None
        if r['review_status'] != 'Pending':
            return jsonify(error='This manual report has already been reviewed.'), 409
        action = body.get('action')
        note = str(body.get('note') or '').strip()
        if action not in ('accept', 'reject') or not 5 <= len(note) <= 500:
            return jsonify(error='Choose accept or reject and enter a review note (5–500 characters).'), 400
        d = json.loads(r['detail'])
        d['manual']['reviewer'] = va.current_pilot_id()
        if action == 'accept':
            rank = va.career(r['pilot_id'], con)['rank']
            pay = va.flight_pay(r['block_min'], rank, 0)
            va.add_tx(r['pilot_id'], 'flight_pay', pay['flight_pay'], 'Manual flight approved: '+r['flight_number'], report_id, con)
            d['manual']['basic_pay'] = pay['flight_pay']
            if body.get('complete_flight'):
                d['manual']['completed'] = complete(con, r)
        con.execute('UPDATE pireps SET review_status=?,review_note=?,reviewed_at=?,detail=? WHERE id=?',
                    ('Accepted' if action=='accept' else 'Rejected',note,time.time(),json.dumps(d),report_id))
    return jsonify(ok=True)


def complete(con, r):
    """Staff ticked "deliver the cargo and move the aircraft": what the flight would have done had ACARS been running."""
    import cargo_network
    pilot, dep, arr, now = r['pilot_id'], r['dep'], r['arr'], time.time()
    out = {'cargo': 0, 'booking_closed': False, 'aircraft_moved': False, 'pilot_moved': False}
    row = con.execute('SELECT data FROM bookings WHERE pilot_id=?', (pilot,)).fetchone()
    booking = json.loads(row['data']) if row else None
    m = (booking or {}).get('mission') or {}
    if booking and (m.get('origin') or {}).get('icao') == dep and (m.get('destination') or {}).get('icao') == arr:
        if (booking.get('dispatch') or {}).get('shipments'):
            cargo_network.record_flight(con, booking, {'arr': arr, 'status': 'Delivered', 'flight_number': r['flight_number']}, r['id'], pilot)
            out['cargo'] = con.execute("SELECT COUNT(*) FROM cargo_movements WHERE pirep_id=? AND event_type='FLIGHT_ARRIVAL'", (r['id'],)).fetchone()[0]
        con.execute('DELETE FROM bookings WHERE pilot_id=?', (pilot,))
        out['booking_closed'] = True
    moved = con.execute("""UPDATE airframes SET location=?, status=CASE WHEN status='Booked' THEN 'Available' ELSE status END,
        last_flight=?, last_pilot=?, updated=? WHERE reg=? AND (location=? OR status='Booked')""", (arr, r['flight_number'], pilot, now, r['registration'], dep)).rowcount
    out['aircraft_moved'] = bool(moved)
    out['pilot_moved'] = bool(con.execute("UPDATE pilots SET location=? WHERE id=? AND (location=? OR location IS NULL OR location='')", (arr, pilot, dep)).rowcount)
    return out


def register(app, va):
    import auth
    @app.post('/api/manual-pireps')
    def submit():
        if not auth.current():
            return jsonify(error='Please sign in.'),401
        if request.content_length and request.content_length > 3000000:
            return jsonify(error='Screenshot must be under 2 MB.'),413
        b=request.get_json(silent=True)
        if not isinstance(b,dict): return jsonify(error='Invalid report.'),400
        try:
            def field(k,lo,hi):
                v=b.get(k,'')
                if not isinstance(v,str) or not lo<=len(v.strip())<=hi: raise ValueError('Check '+k+'.')
                return v.strip()
            flight=field('flight',2,12).upper();dep=field('dep',4,4).upper();arr=field('arr',4,4).upper()
            if not re.fullmatch('[A-Z0-9-]+',flight): raise ValueError('Use letters and numbers for the flight number.')
            if dep==arr or dep not in va.C['AIRPORTS'] or arr not in va.C['AIRPORTS']: raise ValueError('Choose two different known ICAO airports.')
            aircraft=field('aircraft',2,20);tail=field('tail',2,20).upper()
            if aircraft not in va.C['FLEET']: raise ValueError('Choose a PAC aircraft type.')
            reason=field('reason',10,2000);evidence_note=field('evidence_note',0,2000)
            minutes=float(b.get('minutes',0))
            if not 5<=minutes<=1440 or not minutes.is_integer(): raise ValueError('Enter block time in whole minutes (5–1440).')
            start=datetime.fromisoformat(field('departed',16,25).replace('Z','+00:00'))
            if start.tzinfo is None: start=start.replace(tzinfo=timezone.utc)
            start=start.timestamp();now=time.time()
            if not now-30*86400<=start<=now or start+minutes*60>now: raise ValueError('Enter a completed flight within the last 30 days, in UTC.')
            image=None;mime=None
            raw=b.get('screenshot') or ''
            if raw:
                if not isinstance(raw,str) or len(raw)>2800000: raise ValueError('Screenshot must be under 2 MB.')
                head,encoded=raw.split(',',1);image=base64.b64decode(encoded,validate=True)
                if len(image)>2*1024*1024: raise ValueError('Screenshot must be under 2 MB.')
                if head=='data:image/png;base64' and image.startswith(b'\x89PNG\r\n\x1a\n'): mime='image/png'
                elif head=='data:image/jpeg;base64' and image.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
                else: raise ValueError('Use a PNG or JPEG screenshot.')
        except (ValueError,TypeError,OverflowError,binascii.Error):
            return jsonify(error='Check the flight details: valid airports/type, UTC departure within 30 days, completed block time (5–1440 minutes), a reason of 10–2000 characters, and optional PNG/JPEG under 2 MB.'),400
        pid=va.current_pilot_id()
        with va.C['db']() as con:
            con.execute('BEGIN IMMEDIATE')
            frame=con.execute('SELECT type FROM airframes WHERE reg=?',(tail,)).fetchone()
            if not frame or frame['type']!=aircraft: return jsonify(error='Tail number must match the selected PAC aircraft type.'),400
            if con.execute("SELECT COUNT(*) FROM pireps WHERE pilot_id=? AND source='Manual' AND review_status='Pending'",(pid,)).fetchone()[0]>=5:
                return jsonify(error='You already have five manual reports awaiting review.'),409
            for r in con.execute('SELECT detail,filed_at FROM pireps WHERE pilot_id=? AND dep=? AND arr=? AND aircraft=?',(pid,dep,arr,aircraft)):
                d=json.loads(r['detail'] or '{}');out=(d.get('manual') or {}).get('departed') or (d.get('oooi') or {}).get('out')
                if out and abs(float(out)-start)<1800: return jsonify(error='A report already exists for this flight. Ask staff to review it.'),409
            detail={'manual':{'departed':start,'submitted':now,'reason':reason,'evidence_note':evidence_note,'has_screenshot':bool(image)},'oooi':{},'breakdown':[]}
            data=dict(filed_at=now,mission_id='MANUAL',mission_title='Manual flight report',category='Manual',flight_number=flight,aircraft=aircraft,registration=tail,airframe=tail,dep=dep,arr=arr,planned_arr=arr,block_min=minutes,flight_min=None,distance_nm=None,fuel_used_lbs=None,payload_lbs=0,landing_rate=None,landing_g=None,score=None,grade='Unscored',status='Manual',points=0,demo=0,source='Manual',remarks=reason,detail=json.dumps(detail),pilot_id=pid,review_status='Pending',flags=json.dumps(['Manual report: no ACARS telemetry. Staff review required.']),bonus_points=0,revenue=None,cost=None,profit=None)
            keys=list(data);cur=con.execute('INSERT INTO pireps ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',list(data.values()));rid=cur.lastrowid
            if image: con.execute('INSERT INTO manual_pirep_evidence VALUES (?,?,?)',(rid,mime,image))
        return jsonify(ok=True,id=rid),201

    @app.get('/api/manual-pireps/<int:rid>/evidence')
    def evidence(rid):
        if not auth.current(): return jsonify(error='Please sign in.'),401
        with va.C['db']() as con:
            r=con.execute('SELECT p.pilot_id,e.mime,e.image FROM manual_pirep_evidence e JOIN pireps p ON p.id=e.pirep_id WHERE p.id=?',(rid,)).fetchone()
        if not r or (r['pilot_id']!=va.current_pilot_id() and not auth.is_staff()): return jsonify(error='Not found.'),404
        return Response(r['image'],mimetype=r['mime'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Disposition':'inline; filename="flight-evidence"'})
