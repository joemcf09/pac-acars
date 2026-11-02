"""Staged SimBrief TLR reader. Preserves source data; never computes aircraft performance.
Not connected to the production application. Units need validation against real exports.
"""
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def _xml_value(node):
    if not len(node):
        return (node.text or '').strip()
    result = {}
    for child in node:
        key = child.tag.rsplit('}', 1)[-1]
        value = _xml_value(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def read_export(path):
    data = Path(path).read_bytes()
    if len(data) > 20_000_000:
        raise ValueError('Export exceeds the 20 MB limit.')
    text = data.decode('utf-8-sig')
    if text.lstrip().startswith('<'):
        # No DTDs or entity expansion, including alternate XML encodings.
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise ValueError('XML document types and entities are not accepted.')
        root = ET.fromstring(text)
        if root.tag.rsplit('}', 1)[-1] != 'OFP':
            raise ValueError('Expected a SimBrief OFP XML root.')
        raw = _xml_value(root)
    else:
        raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError('Expected an OFP object.')
    return inspect_performance(raw)


def inspect_performance(raw):
    raw = raw.get('OFP', raw)
    if not isinstance(raw, dict):
        raise ValueError('Invalid OFP object.')
    def obj(key):
        value = raw.get(key)
        return value if isinstance(value, dict) else {}
    tlr = obj('tlr')
    result = {
        'schema_version': 1, 'source': 'SimBrief OFP runway analysis',
        'status': 'unavailable', 'validated_for_use': False,
        'request_id': obj('params').get('request_id'),
        'generated': obj('params').get('time_generated'),
        'aircraft_icao': obj('aircraft').get('icaocode'),
        'registration': obj('aircraft').get('reg'),
        'ofp_weight_unit': obj('params').get('units'),
        'unit_status': 'TLR field units require verification; no conversions applied',
        'phases': {}, 'issues': [],
        'snapshot_sha256': hashlib.sha256(json.dumps(tlr, sort_keys=True).encode()).hexdigest(),
    }
    for phase in ('takeoff', 'landing'):
        source = tlr.get(phase)
        if not isinstance(source, dict) or not source:
            result['issues'].append(f'{phase}: no runway analysis supplied')
            continue
        conditions = source.get('conditions')
        conditions = conditions if isinstance(conditions, dict) else {}
        rows = source.get('runway', [])
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            rows = []
        rows = [copy.deepcopy(r) for r in rows if isinstance(r, dict)]
        planned = conditions.get('planned_runway')
        selected = [r for r in rows if planned and r.get('identifier') == planned]
        if len(selected) != 1:
            result['issues'].append(f'{phase}: planned runway missing, ambiguous or unmatched')
        airport_key = 'origin' if phase == 'takeoff' else 'destination'
        airport = obj(airport_key).get('icao_code')
        if not airport or conditions.get('airport_icao') != airport:
            result['issues'].append(f'{phase}: airport does not match OFP or is missing')
        result['phases'][phase] = {
            'conditions': copy.deepcopy(conditions),
            'runways': rows, 'selected_runway': selected[0] if len(selected) == 1 else None,
            'distance_dry': copy.deepcopy(source.get('distance_dry')),
            'distance_wet': copy.deepcopy(source.get('distance_wet')),
            'raw': copy.deepcopy(source),
        }
    if result['phases']:
        result['status'] = 'imported_unverified'
        result['issues'].append('Aircraft/add-on applicability and units have not been validated.')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Inspect a SimBrief export locally; no network or live changes.')
    parser.add_argument('export')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = read_export(args.export)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f"{report['status']}: {len(report['phases'])} phase(s). Report saved. No aircraft calculations performed.")

def import_notams(raw):
    """Normalize both SimBrief representations; preserve text, dates and location."""
    raw = raw.get('OFP', raw)
    def rows(value):
        return value if isinstance(value,list) else [value] if isinstance(value,dict) else []
    def field(n,*keys):
        return next((n[k] for k in keys if isinstance(n.get(k),str) and n[k]), '')
    entries={}
    containers=[]
    legacy=raw.get('notams')
    if isinstance(legacy,dict):containers.extend(rows(legacy.get('notamdrec')))
    for role in ('origin','destination','alternate'):
        for airport in rows(raw.get(role)):
            ns=airport.get('notams')
            if isinstance(ns,dict):containers.extend(rows(ns.get('notam')))
    for n in containers:
        loc=field(n,'location_icao','icao_id','cns_location_id')
        ident=field(n,'notam_id')
        text=field(n,'notam_raw','notam_text')
        if not ident or not text:continue
        part=field(n,'notam_part') or '1'
        entries[(loc,ident,part)]={'notam_id':ident,'part':part,'location_icao':loc,
            'date_effective':field(n,'date_effective','notam_effective_dtg'),
            'date_expire':field(n,'date_expire','notam_expire_dtg'),
            'date_expire_is_estimated':field(n,'date_expire_is_estimated'),
            'notam_schedule':field(n,'notam_schedule'),'notam_raw':text}
    return {'source':'SimBrief OFP','status':'imported' if entries else 'unavailable',
            'entries':list(entries.values()),'coverage':'Imported source coverage; not independently verified'}


def import_briefing(raw):
    raw=raw.get('OFP',raw)
    params=raw.get('params') if isinstance(raw.get('params'),dict) else {}
    text=raw.get('text') if isinstance(raw.get('text'),dict) else {}
    ac=raw.get('aircraft') if isinstance(raw.get('aircraft'),dict) else {}
    performance=inspect_performance(raw)
    report=text.get('tlr_section')
    report=report if isinstance(report,str) else ''
    fixes=(raw.get('navlog') or {}).get('fix',[]) if isinstance(raw.get('navlog'),dict) else []
    if isinstance(fixes,dict):fixes=[fixes]
    if not isinstance(fixes,list):fixes=[]
    keys=('ident','time_leg','time_total','fuel_plan_onboard','distance','pos_lat','pos_long')
    return {'version':1,'source':'SimBrief OFP','request_id':params.get('request_id'),
            'generated':params.get('time_generated'),'units':params.get('units'),
            'aircraft':{k:ac.get(k) for k in ('icaocode','name','engines','reg')},
            'performance':performance,'performance_report':report,
            'notams':import_notams(raw),
            'navlog':[{k:f.get(k) for k in keys} for f in fixes if isinstance(f,dict)]}
