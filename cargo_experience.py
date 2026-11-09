"""Editorial shipment features and read-only recognition/receipts.

Cargo credit is always derived from cargo_programs.QUALIFY. No wallet writes.
"""
from contextlib import closing
import json
import sqlite3
import time
from flask import jsonify, request
from cargo_programs import QUALIFY, campaign_input


def migrate(con):
    con.execute('''CREATE TABLE IF NOT EXISTS cargo_features (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        description TEXT NOT NULL, starts REAL NOT NULL, ends REAL NOT NULL,
        destinations TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
        created_at REAL NOT NULL, created_by TEXT NOT NULL)''')


def awards(con, pid):
    result=[]
    for c in con.execute("SELECT * FROM cargo_campaigns WHERE state IN ('published','archived') ORDER BY starts DESC,id DESC").fetchall():
        dest=json.loads(c['destinations']); marks=','.join('?' for _ in dest)
        end=min(c['ends'],c['archived_at']) if c['archived_at'] else c['ends']
        row=con.execute(f'''SELECT COALESCE(SUM(payload_lbs),0) total,
            COALESCE(SUM(CASE WHEN pilot_id=? THEN payload_lbs ELSE 0 END),0) personal
            FROM pireps WHERE {QUALIFY} AND filed_at>=? AND filed_at<? AND arr IN ({marks})''',
            (pid,c['starts'],end,*dest)).fetchone()
        base=(c['baseline_lbs'] if 'baseline_lbs' in c.keys() else 0) or 0
        if row['total']+base>=c['target_lbs'] and row['personal']>0:
            # Deliberately public fields only; other pilots' totals and wallet are private.
            result.append(dict(id=c['id'],title=c['title'],year=time.strftime('%Y',time.gmtime(c['starts'])),destinations=dest,patch=c['patch'] if 'patch' in c.keys() else None))
    return result


def receipt(con, rid, pid, staff=False):
    row=con.execute('SELECT * FROM pireps WHERE id=?',(rid,)).fetchone()
    if row is None or (row['pilot_id']!=pid and not staff):return None
    p=dict(row)
    qualifies=con.execute(f'SELECT 1 FROM pireps WHERE id=? AND {QUALIFY}',(rid,)).fetchone() is not None
    contributions=[]
    if qualifies:
        for c in con.execute("SELECT * FROM cargo_campaigns WHERE state IN ('published','archived') ORDER BY starts DESC,id DESC").fetchall():
            end=min(c['ends'],c['archived_at']) if c['archived_at'] else c['ends']
            if c['starts']<=p['filed_at']<end and p['arr'] in json.loads(c['destinations']):
                contributions.append(dict(id=c['id'],title=c['title'],cargo_lbs=p['payload_lbs']))
    postings=[dict(r) for r in con.execute('SELECT kind,amount,description FROM wallet WHERE pilot_id=? AND pirep_id=? ORDER BY time,id',(p['pilot_id'],rid))]
    if qualifies:reason='Accepted qualifying cargo delivery.'
    elif p.get('review_status')=='Pending':reason='Awaiting staff review. No campaign cargo is credited yet.'
    else:reason='This report does not qualify for campaign cargo credit (review, flight type, payload, demo or destination rules).'
    return dict(id=rid,flight_number=p.get('flight_number'),dep=p.get('dep'),arr=p.get('arr'),filed_at=p.get('filed_at'),
                review_status=p.get('review_status'),status=p.get('status'),qualifies=qualifies,reason=reason,
                reported_cargo_lbs=p.get('payload_lbs') or 0,credited_cargo_lbs=p['payload_lbs'] if qualifies else 0,
                campaigns=contributions,postings=postings,posted_total=round(sum(r['amount'] for r in postings),2),
                awards=awards(con,p['pilot_id']) if qualifies else [])


def register(app,context):
    def db():
        con=sqlite3.connect(context['DB_PATH'],timeout=5);con.row_factory=sqlite3.Row;return con
    with closing(db()) as con,con:migrate(con)
    def reply(data,status=200):
        r=jsonify(data);r.status_code=status;r.headers['Cache-Control']='private, no-store';return r
    def user(staff=False):
        import auth
        p=auth.current()
        if not p:return None,reply({'error':'Please sign in.'},401)
        if staff and not p.get('staff'):return None,reply({'error':'Staff access required.'},403)
        return p,None

    @app.get('/api/pilot/delivery-receipt/<int:rid>')
    def delivery_receipt(rid):
        p,error=user()
        if error is not None:return error
        with closing(db()) as con:data=receipt(con,rid,p['id'],bool(p.get('staff')))
        return reply(data) if data else reply({'error':'Receipt not found.'},404)

    @app.get('/api/pilot/featured-shipment')
    def featured_shipment():
        p,error=user()
        if error is not None:return error
        now=time.time()
        with closing(db()) as con:
            rows=con.execute("SELECT id,title,description,starts,ends,destinations FROM cargo_features WHERE state='published' AND starts<=? AND ends>? ORDER BY starts DESC,id DESC LIMIT 1",(now,now)).fetchall()
        data=[{**dict(r),'destinations':json.loads(r['destinations'])} for r in rows]
        return reply({'shipment':data[0] if data else None})

    @app.route('/api/staff/featured-shipments',methods=['GET','POST'])
    def staff_features():
        p,error=user(True)
        if error is not None:return error
        if request.method=='GET':
            with closing(db()) as con:
                rows=con.execute('SELECT id,title,description,starts,ends,destinations,state FROM cargo_features ORDER BY created_at DESC,id DESC LIMIT 100').fetchall()
            return reply({'shipments':[{**dict(r),'destinations':json.loads(r['destinations'])} for r in rows]})
        body=request.get_json(silent=True)
        try:
            if not isinstance(body,dict):raise ValueError('Enter shipment details.')
            title,desc,start,end,_,dest=campaign_input({**body,'target_lbs':1},context['AIRPORTS'])
            if not desc:raise ValueError('Add a short cargo story.')
            if end-start>14*86400:raise ValueError('Choose a feature lasting 1–14 days.')
        except ValueError as e:return reply({'error':str(e)},400)
        with closing(db()) as con,con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute("SELECT COUNT(*) FROM cargo_features WHERE state='draft'").fetchone()[0]>=20:return reply({'error':'Archive an old draft first (20 draft limit).'},409)
            cur=con.execute('INSERT INTO cargo_features(title,description,starts,ends,destinations,created_at,created_by) VALUES(?,?,?,?,?,?,?)',(title,desc,start,end,dest,time.time(),p['id']))
            rid=cur.lastrowid
        return reply({'id':rid},201)

    @app.post('/api/staff/featured-shipments/<int:fid>')
    def feature_action(fid):
        p,error=user(True)
        if error is not None:return error
        body=request.get_json(silent=True);action=body.get('action') if isinstance(body,dict) else None
        if action not in ('publish','archive'):return reply({'error':'Choose publish or archive.'},400)
        with closing(db()) as con,con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT * FROM cargo_features WHERE id=?',(fid,)).fetchone()
            if not row:return reply({'error':'Shipment not found.'},404)
            if action=='publish':
                if row['state']!='draft':return reply({'error':'Only drafts can be published.'},409)
                if row['ends']<=time.time():return reply({'error':'These dates have ended. Create a new draft.'},409)
                if con.execute("SELECT 1 FROM cargo_features WHERE state='published' AND starts<? AND ends>?",(row['ends'],row['starts'])).fetchone():return reply({'error':'A published shipment already covers these dates. Archive it or use different dates.'},409)
            con.execute('UPDATE cargo_features SET state=? WHERE id=?',('published' if action=='publish' else 'archived',fid))
        return reply({'ok':True})
