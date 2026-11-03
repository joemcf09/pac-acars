"""Company-funded checkrides; canonical server-built missions and atomic fleet booking."""
import json
import time
from contextlib import closing

HUBS = ('KCVG', 'PANC', 'LIMC', 'KMIA', 'OMDW', 'VHHH')


def course_types(va, pid, course):
    if course == va.CHECKRIDE_ID:
        return [va.CHECKRIDE['aircraft']]
    entry = next((x for x in va.ratings_overview(pid) if x['checkride_id'] == course), None)
    if not entry or not entry['unlocked']:
        raise ValueError('This checkride is not available to your pilot. Check Qualifications.')
    return entry['types']


def resolve(va, spec):
    if not isinstance(spec, dict):
        raise ValueError('Choose your checkride options in Qualifications.')
    pid = va.current_pilot_id()
    course, mode, ac, origin, reg = (str(spec.get(k) or '') for k in ('course','mode','aircraft','origin','reg'))
    if mode not in ('dedicated','fleet') or ac not in course_types(va,pid,course):
        raise ValueError('Choose a supported training option and aircraft type.')
    if ac not in va.C['FLEET'] or va.C['FLEET'][ac].get('retired'):
        raise ValueError('This aircraft type is not available for training.')
    if mode == 'dedicated':
        if origin not in HUBS:
            raise ValueError('Choose one of the supported training airports.')
        reg = ''
    else:
        with closing(va.C['db']()) as con:
            row = con.execute('SELECT * FROM airframes WHERE reg=?',(reg,)).fetchone()
        if not row or row['type'] != ac or row['location'] != origin or row['status'] != 'Available':
            raise ValueError('That fleet aircraft is no longer available there. Refresh the training options.')
    if origin not in va.C['AIRPORTS'] or (va.C['AIRPORTS'][origin].get('rwy_ft') or 0) < (va.C['FLEET'][ac].get('min_rwy_ft') or 6000):
        raise ValueError('This airport does not meet the selected type’s training runway requirement.')
    route = va.checkride_mission(pid, va.rating_slug(va.rating_family(ac)), origin, aircraft=ac)
    if not route or route['origin']['icao'] != origin:
        raise ValueError('No suitable training route is available from this airport. Choose another airport.')
    line = course == va.CHECKRIDE_ID
    policy = dict(course=course,mode=mode,aircraft=ac,origin=origin,reg=reg,version=1)
    m = {k:route[k] for k in ('origin','destination','distance_nm','target_block_min','payload_lbs')}
    m.update(id=course,category='Checkride' if line else 'Type checkride',priority='Standard',reward=0,
             aircraft=[ac],types_only=True,cargo='Training ballast — no commercial shipment',region='Company training',
             title=('Line checkride' if line else va.rating_family(ac)+' type checkride')+f': {origin} to {route["destination"]["icao"]}',
             training=policy,briefing='Company-funded training. Same checkride standards in both modes. No flight pay, bonuses, profit share or campaign cargo credit. Successful, accepted checkride hours count toward your career. Retakes are free.')
    if not line:m['type_checkride']=va.rating_family(ac)
    return m


def options(va):
    pid=va.current_pilot_id()
    courses=[dict(id=va.CHECKRIDE_ID,name='737 line checkride',types=[va.CHECKRIDE['aircraft']],standard=va.CHECKRIDE)]
    courses += [dict(id=f['checkride_id'],name=f['family']+' type checkride',types=f['types'],standard=va.TYPE_CHECKRIDE) for f in va.ratings_overview(pid) if f['unlocked']]
    with closing(va.C['db']()) as con:
        frames=[dict(r) for r in con.execute("SELECT reg,type,location FROM airframes WHERE status='Available' ORDER BY location,reg")]
        me=con.execute('SELECT hub FROM pilots WHERE id=?',(pid,)).fetchone()
    home=(me['hub'] or '').upper() if me else ''
    hubs=sorted(HUBS,key=lambda h:h!=home)   # the pilot's own home base first, so it's the default training airport
    for c in courses:
        c['choices']=[]
        for ac in c['types']:
            for mode,origin,reg in [('dedicated',h,'') for h in hubs]+[('fleet',f['location'],f['reg']) for f in frames if f['type']==ac]:
                spec=dict(course=c['id'],mode=mode,aircraft=ac,origin=origin,reg=reg)
                try:m=resolve(va,spec)
                except ValueError:continue
                c['choices'].append(dict(spec=spec,destination=m['destination']['icao'],distance_nm=m['distance_nm'],block_min=m['target_block_min']))
    return dict(courses=courses)


def book(va, spec, ofp=None, context=None):
    c=context or va.C;pid=va.current_pilot_id();m=resolve(va,spec);t=m['training'];ac=t['aircraft']
    if ofp is not None:
        if not isinstance(ofp,dict):raise ValueError('Import a valid SimBrief plan.')
        errors,_=c['validate_ofp'](ofp,m,ac)
        if errors:raise ValueError('Checkride OFP: '+errors[0])
    booking=dict(mission=m,aircraft=ac,ofp=ofp,flight_number=m['id'],requested_at=time.time(),airframe=t['reg'] or None)
    booking['dispatch']=c['dispatch'].generate(booking,c['FLEET'],c['dispatch_pilot']())
    for key,airport in [('dep_stand','origin'),('arr_stand','destination')]:
        booking[key]=va.assign_stand(m[airport]['icao'],ac,booking['flight_number'],'dep' if key=='dep_stand' else 'arr',booking['airframe'])
    with closing(c['db']()) as con,con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT 1 FROM bookings WHERE pilot_id=?',(pid,)).fetchone():
            raise ValueError('Finish or cancel your current booking before starting a checkride.')
        pilot=con.execute('SELECT location FROM pilots WHERE id=?',(pid,)).fetchone()
        if not pilot:raise ValueError('Your pilot record is unavailable.')
        if t['mode']=='fleet':
            used=con.execute("UPDATE airframes SET status='Booked',updated=? WHERE reg=? AND type=? AND location=? AND status='Available'",(time.time(),t['reg'],ac,t['origin'])).rowcount
            if used!=1:raise ValueError('Another pilot has taken this aircraft. Refresh and choose another.')
            if pilot['location']!=t['origin']:
                va.add_tx(pid,'training_travel',0,f'Company checkride travel: {pilot["location"]} to {t["origin"]}',None,con)
                con.execute('UPDATE pilots SET location=? WHERE id=?',(t['origin'],pid))
        con.execute('INSERT INTO bookings(pilot_id,data,requested_at) VALUES(?,?,?)',(pid,json.dumps(booking),booking['requested_at']))
    # The booking is already committed; optional integrations must not turn success into a failure.
    try:c['start_ofp_watch'](booking)
    except Exception:pass
    return booking


def successful(detail):
    ck=detail.get('type_checkride') or detail.get('checkride') or {}
    return bool(ck.get('passed'))
