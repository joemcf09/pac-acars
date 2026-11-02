"""Fictional customer briefs; never grant partner privileges or bonus pay."""
import json
from pathlib import Path
CUSTOMERS=json.loads(Path(__file__).with_name('charter_customers.json').read_text(encoding='utf-8'))

def apply(mission,spec):
    key=spec.get('customer_id')
    if not key:
        if spec.get('shipment_id'): raise ValueError('Choose a charter customer for this shipment.')
        return
    if not isinstance(key,str): raise ValueError('Choose a valid charter customer.')
    c=next((c for c in CUSTOMERS if c['id']==key),None)
    shipment=next((s for s in c['shipments'] if s['id']==spec.get('shipment_id')),None) if c else None
    if not c or not shipment: raise ValueError('Choose a valid customer and shipment.')
    if mission['category']=='Ferry': raise ValueError('Customer shipments require cargo. Choose Independent charter for a ferry.')
    mission['charter'].update(customer_id=key,shipment_id=shipment['id'])
    mission['customer']={'id':key,'name':c['name'],'logo':c['logo'],'simulated':True}
    mission['title']=c['name']+' · '+shipment['title']+': '+mission['origin']['icao']+' to '+mission['destination']['icao']
    mission['briefing']='Fictional PAC customer assignment. '+shipment['brief']+' '+mission['briefing']+' PAC operates this flight; no affiliation, sponsorship or endorsement is implied.'
    mission['handling']={'label':'Simulated customer · '+c['name'],'notes':['Verify packaging, cargo-door clearance, loading limits and restraint requirements for the actual load.','Customer choice does not reserve a tail, waive qualifications or add a pay bonus.']}
