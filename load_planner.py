"""PAC position-allocation exercise. Not an aircraft weight-and-balance approval."""
import copy
import time

SOURCE = 'https://www.boeing.com/content/dam/boeing/boeingdotcom/commercial/airports/acaps/737NG_REV_B.pdf'
MAIN_COUNTS = {'B738F': 10, 'B722F': 12}
PRESET_NAMES = {'B738F': '737 BCF simulation', 'B722F': '727-200F simulation'}

def main_positions(booking):
    """The movable main-deck positions: the verified 737/727 layouts, or the main deck PAC's dispatcher built for any
    other freighter."""
    a = booking.get('aircraft')
    if a in MAIN_COUNTS:
        return [f'M{i:02}' for i in range(1, MAIN_COUNTS[a] + 1)]
    return [str(x) for x in (((booking.get('dispatch') or {}).get('deck') or {}).get('main') or [])]


def describe(booking, revision):
    d = booking.get('dispatch') or {}
    return {'revision': revision, 'requested_at': booking['requested_at'],
            'flight': booking['flight_number'], 'airframe': booking.get('airframe'),
            'aircraft': booking.get('aircraft'), 'positions': d.get('positions', []),
            'source': SOURCE if booking.get('aircraft') == 'B738F' else None,
            'saved': d.get('load_plan'), 'signed': bool(booking.get('signed')),
            'main': main_positions(booking), 'aircraft_name': d.get('aircraft_name') or booking.get('aircraft'),
            'max_payload_lbs': (d.get('weights') or {}).get('max_payload_lbs'), 'deck': d.get('deck')}

def rearrange(booking, assignments):
    """Only reposition existing units, preserving weight, identity and all references."""
    aircraft = booking.get('aircraft')
    main = main_positions(booking)
    if not main:
        raise ValueError('This flight has no main-deck positions to plan.')
    d = copy.deepcopy(booking['dispatch'])
    units = d.get('positions', [])
    old = {p['pos']: p for p in units}
    if not isinstance(assignments, dict) or set(assignments) != set(old):
        raise ValueError('Submit exactly one assignment for every existing unit.')
    values = list(assignments.values())
    if any(not isinstance(v, str) for v in values) or len(set(values)) != len(values):
        raise ValueError('Each position can hold only one unit.')
    standard = set(main)
    for origin, target in assignments.items():
        # Compact and bulk units lack verified geometry: preserve their existing placement.
        if origin not in standard and target != origin:
            raise ValueError('Compact and lower-hold placements are fixed in this version.')
        if origin in standard and target not in standard:
            raise ValueError(f'Main-deck units must stay in positions {main[0]}–{main[-1]}.')
    if all(k == v for k, v in assignments.items()):
        return None
    for p in units: p['pos'] = assignments[p['pos']]
    units.sort(key=lambda p:(not p['pos'].startswith('M'), p['pos']))
    for item in d.get('dg', []): item['pos'] = assignments.get(item['pos'], item['pos'])
    for item in d.get('onward', []): item['pos'] = assignments.get(item['pos'], item['pos'])
    for shipment in d.get('shipments', []):
        shipment['units'] = [assignments.get(pos, pos) for pos in shipment['units']]
    d['load_plan'] = {'saved_at': time.time(), 'preset': PRESET_NAMES.get(aircraft, f'{aircraft} main-deck plan'),
                      'note': 'Position allocation only. CG, trim, contour, restraint, floor loading and DG segregation are not verified.'}
    return d
