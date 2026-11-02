"""Bounded scheduled-route planning; never generates offers or reserves aircraft."""
from collections import defaultdict
from contextlib import closing
import json
import math
import sqlite3
import time
from flask import jsonify, request


def migrate(con):
    con.execute('''CREATE TABLE IF NOT EXISTS pilot_rotation_plans (
        pilot_id TEXT PRIMARY KEY, saved_at REAL NOT NULL, after_pirep INTEGER NOT NULL,
        data TEXT NOT NULL)''')


def options(body):
    if not isinstance(body, dict):
        raise ValueError('Choose an aircraft and time budget.')
    aircraft = body.get('aircraft')
    if not isinstance(aircraft, str) or len(aircraft) > 12:
        raise ValueError('Choose an aircraft.')
    minutes, turn = body.get('minutes'), body.get('turnaround', 20)
    if type(minutes) is not int or not 30 <= minutes <= 1440:
        raise ValueError('Time budget must be 30–1440 minutes.')
    if type(turn) is not int or not 0 <= turn <= 120:
        raise ValueError('Turnaround must be 0–120 minutes.')
    if type(body.get('return_home', True)) is not bool:
        raise ValueError('Choose whether to finish at home.')
    return dict(aircraft=aircraft, minutes=minutes, turnaround=turn,
                return_home=body.get('return_home', True))


def route_edges(routes, fleet, aircraft):
    """Conservative full-load planning, including explicit type-only restrictions."""
    ac = fleet.get(aircraft)
    if not ac or ac.get('retired'):
        return {}
    edges = {}
    for r in routes:
        try:
            minutes = float(r.get('target_block_min', 0))
            if not math.isfinite(minutes) or minutes <= 0:
                continue
            if (r.get('types_only') or r.get('tour') or r.get('rotation')) and aircraft not in r.get('aircraft', []):
                continue
            if r.get('payload_lbs', 0) > ac['max_payload_lbs'] or r.get('distance_nm', 0) * 1.05 > ac['range_nm']:
                continue
            if any(a.get('rwy_ft') and a['rwy_ft'] < ac['min_rwy_ft'] for a in (r['origin'], r['destination'])):
                continue
            if r['origin']['icao'] == r['destination']['icao']:
                continue
            edges[r['id']] = dict(id=r['id'], origin=r['origin']['icao'], destination=r['destination']['icao'],
                                  minutes=math.ceil(minutes), cargo=r.get('cargo', 'Cargo'),
                                  payload_lbs=r.get('payload_lbs', 0))
        except (KeyError, TypeError, ValueError):
            continue
    return edges


def itinerary(legs, opt):
    flight = sum(r['minutes'] for r in legs)
    return dict(legs=legs, flight_minutes=flight,
                total_minutes=flight + opt['turnaround'] * (len(legs) - 1), **opt)


def search(edges, here, hub, opt):
    by_origin = defaultdict(list)
    for edge in edges.values():
        by_origin[edge['origin']].append(edge)
    for outgoing in by_origin.values():
        outgoing.sort(key=lambda r: (r['minutes'], r['id']))
    frontier = [([], {here}, here, 0)]
    found = []
    examined = 0
    limited = False
    # Hard work budget: a dense or cyclic network cannot monopolize a web worker.
    for depth in range(4):
        following = []
        for legs, seen, origin, total in frontier:
            for edge in by_origin[origin]:
                examined += 1
                if examined > 12000:
                    limited = True
                    break
                dest = edge['destination']
                elapsed = total + edge['minutes'] + (opt['turnaround'] if legs else 0)
                if elapsed > opt['minutes'] or (dest in seen and dest not in (here, hub)):
                    continue
                path = legs + [edge]
                if not opt['return_home'] or dest == hub:
                    found.append(itinerary(path, opt))
                # A homecoming or return to the starting station ends this rotation.
                if dest not in seen and dest != hub:
                    following.append((path, seen | {dest}, dest, elapsed))
            if examined > 12000:
                break
        if examined > 12000:
            break
        if len(following) > 800:
            limited = True
        frontier = following[:800]
        if not frontier:
            break
    found.sort(key=lambda p: (-p['total_minutes'], -len(p['legs']), tuple(l['id'] for l in p['legs'])))
    return found[:3], limited


def completed_legs(plan, reports):
    index = 0
    for r in reports:
        if index == len(plan['legs']):
            break
        leg = plan['legs'][index]
        if (r['mission_id'] == leg['id'] and r['dep'] == leg['origin'] and r['arr'] == leg['destination']
                and r['aircraft'] == plan['aircraft']):
            index += 1
    return index


def register(app, context):
    def connection():
        c = sqlite3.connect(context['DB_PATH'], timeout=2)
        c.row_factory = sqlite3.Row
        return c

    def snapshot():
        # Reuse the dashboard's authoritative session identity and qualification rules.
        return app.view_functions['briefing']().get_json()

    def response(body, status=200):
        r = jsonify(body)
        r.status_code = status
        r.headers['Cache-Control'] = 'private, no-store'
        return r

    def validate(opt, d):
        if opt['aircraft'] not in d['eligible_types']:
            raise ValueError('This aircraft is not available for your current qualifications.')
        if d['checkride_needed']:
            raise ValueError('Complete your checkride before planning a rotation.')

    @app.route('/api/pilot/rotation-plan', methods=['GET', 'POST', 'DELETE'])
    def rotation_plan():
        import auth
        who = auth.current()
        if not who:
            return response({'error': 'Please sign in.'}, 401)
        pid = who['id']
        if request.method == 'DELETE':
            with closing(connection()) as con, con:
                con.execute('DELETE FROM pilot_rotation_plans WHERE pilot_id=?', (pid,))
            return response({'ok': True})
        d = snapshot()
        if request.method == 'GET':
            with closing(connection()) as con:
                row = con.execute('SELECT * FROM pilot_rotation_plans WHERE pilot_id=?', (pid,)).fetchone()
                saved = json.loads(row['data']) if row else None
                if saved:
                    reports = con.execute("""SELECT mission_id,dep,arr,aircraft FROM pireps
                        WHERE pilot_id=? AND id>? AND demo=0 AND review_status='Accepted'
                        AND status!='Failed' ORDER BY id""", (pid, row['after_pirep'])).fetchall()
                    saved['completed'] = completed_legs(saved, reports)
                    saved['saved_at'] = row['saved_at']
            return response({'saved': saved, 'location': d['location']['icao'], 'hub': d['hub']['icao'],
                             'eligible_types': d['eligible_types'], 'booking': bool(d['booking']),
                             'checkride_needed': d['checkride_needed']})
        try:
            b = request.get_json(silent=True)
            opt = options(b)
            validate(opt, d)
            edges = route_edges(context['ROUTES'].values(), context['FLEET'], opt['aircraft'])
            ids = b.get('route_ids')
            if not isinstance(ids, list) or not 1 <= len(ids) <= 4 or any(not isinstance(i, str) or i not in edges for i in ids):
                raise ValueError('Choose a valid itinerary of one to four scheduled legs.')
            if len(set(ids)) != len(ids):
                raise ValueError('An itinerary cannot repeat the same route.')
            legs = [edges[i] for i in ids]
            if legs[0]['origin'] != d['location']['icao'] or any(a['destination'] != b['origin'] for a,b in zip(legs, legs[1:])):
                raise ValueError('Your location or routes changed. Find a new rotation.')
            if opt['return_home'] and legs[-1]['destination'] != d['hub']['icao']:
                raise ValueError('This itinerary does not finish at your home hub.')
            plan = itinerary(legs, opt)
            if plan['total_minutes'] > opt['minutes']:
                raise ValueError('This itinerary exceeds your time budget.')
            with closing(connection()) as con, con:
                last = con.execute('SELECT COALESCE(MAX(id),0) FROM pireps WHERE pilot_id=?', (pid,)).fetchone()[0]
                con.execute('INSERT OR REPLACE INTO pilot_rotation_plans VALUES(?,?,?,?)',
                            (pid, time.time(), last, json.dumps(plan)))
            return response({'ok': True})
        except ValueError as exc:
            return response({'error': str(exc)}, 400)

    @app.post('/api/pilot/rotation-options')
    def rotation_options():
        import auth
        if not auth.current():
            return response({'error': 'Please sign in.'}, 401)
        try:
            opt = options(request.get_json(silent=True))
            d = snapshot()
            validate(opt, d)
            edges = route_edges(context['ROUTES'].values(), context['FLEET'], opt['aircraft'])
            plans, limited = search(edges, d['location']['icao'], d['hub']['icao'], opt)
            with closing(connection()) as con:
                available = con.execute("SELECT COUNT(*) FROM airframes WHERE type=? AND location=? AND status='Available'",
                                        (opt['aircraft'], d['location']['icao'])).fetchone()[0]
            return response({'plans': plans, 'limited': limited, 'available_airframes': available,
                             'airframes_enforced': context['settings']().get('enforce_airframes', True),
                             'booking': bool(d['booking'])})
        except ValueError as exc:
            return response({'error': str(exc)}, 400)
