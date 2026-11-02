"""Cargo collections and cooperative campaigns derived from accepted PIREPs.

No rewards ledger, offer generation, or mutations of existing flight statistics.
Review reversals are reflected on the next read because credit is derived, not copied.
"""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import math
import re
import sqlite3
import time
from flask import jsonify, request

COLLECTIONS = (
    ('express_triangle', 'Express Triangle', 'Connect three PAC cargo gateways.', ('KCVG','KATL','KMIA')),
    ('great_lakes', 'Great Lakes Express', 'Deliver to four Great Lakes freight stations.', ('KORD','KDTW','KCLE','KBUF')),
    ('caribbean', 'Caribbean Supply Chain', 'Bring cargo to these island gateways.', ('MYNN','TJSJ','TNCM')),
    ('pacific', 'Pacific Freight Bridge', 'Connect the mainland, Alaska and Hawaii.', ('KLAX','PANC','PHNL')),
)
QUALIFY = """demo=0 AND review_status='Accepted' AND status!='Failed'
    AND payload_lbs>0 AND payload_lbs<10000000 AND filed_at>0
    AND pilot_id IS NOT NULL AND dep IS NOT NULL AND arr IS NOT NULL AND dep!=arr
    AND COALESCE(category,'') NOT IN ('Checkride','Type checkride','Ferry')
    AND (planned_arr IS NULL OR planned_arr='' OR planned_arr=arr)"""


def migrate(con):
    con.execute('''CREATE TABLE IF NOT EXISTS cargo_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
        starts REAL NOT NULL, ends REAL NOT NULL, target_lbs INTEGER NOT NULL,
        destinations TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
        created_at REAL NOT NULL, created_by TEXT NOT NULL, archived_at REAL)''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_cargo_pilot_reports ON pireps(pilot_id,review_status,demo,filed_at)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_cargo_campaign_reports ON pireps(review_status,demo,filed_at,arr)')


def passport(con, airports, pid):
    # SQL aggregates the logbook once. Airport metadata is the existing site dataset.
    rows = con.execute(f'''WITH deliveries AS (
        SELECT id,arr,filed_at,payload_lbs,
        ROW_NUMBER() OVER(PARTITION BY arr ORDER BY filed_at,id) AS position
        FROM pireps WHERE pilot_id=? AND {QUALIFY})
        SELECT arr,COUNT(*) AS deliveries,SUM(payload_lbs) AS cargo_lbs,MIN(filed_at) AS first,
        MAX(CASE WHEN position=1 THEN id END) AS first_pirep
        FROM deliveries GROUP BY arr ORDER BY first,arr''', (pid,)).fetchall()
    stamps = []
    unknown = 0
    for r in rows:
        a = airports.get(r['arr'])
        if not a:
            unknown += r['deliveries']
            continue
        stamps.append(dict(icao=r['arr'], name=a.get('name',''), city=a.get('city',''),
                           country=a.get('country',''), continent=a.get('continent',''),
                           lat=a.get('lat'), lon=a.get('lon'), first=r['first'], first_pirep=r['first_pirep'],
                           deliveries=r['deliveries'], cargo_lbs=round(r['cargo_lbs'],2)))
    lookup = {s['icao']:s for s in stamps}
    collections = []
    for key,title,description,required in COLLECTIONS:
        have = [i for i in required if i in lookup]
        earned = len(have)==len(required)
        collections.append(dict(id=key,title=title,description=description,required=list(required),
                                stamped=have,earned=earned,
                                earned_at=max(lookup[i]['first'] for i in required) if earned else None))
    return dict(stamps=stamps,collections=collections,unknown_deliveries=unknown,
                totals=dict(airports=len(stamps),countries=len({s['country'] for s in stamps if s['country']}),
                            deliveries=sum(s['deliveries'] for s in stamps),cargo_lbs=round(sum(s['cargo_lbs'] for s in stamps),2)))


def month_summary(con, airports, pid, month):
    start=datetime.strptime(month,'%Y-%m').replace(tzinfo=timezone.utc)
    end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    p=passport(con,airports,pid)
    lo,hi=start.timestamp(),end.timestamp()
    return dict(stamps=[s['icao'] for s in p['stamps'] if lo<=s['first']<hi],
                collections=[s['title'] for s in p['collections'] if s['earned_at'] and lo<=s['earned_at']<hi])


def campaign_input(b, airports):
    if not isinstance(b,dict): raise ValueError('Enter the campaign details.')
    title=b.get('title');description=b.get('description','')
    if not isinstance(title,str) or not 3<=len(title.strip())<=80: raise ValueError('Use a title of 3–80 characters.')
    if not isinstance(description,str) or len(description)>1000: raise ValueError('Description must be 1000 characters or fewer.')
    target=b.get('target_lbs')
    if type(target) is not int or not 1<=target<=1000000000: raise ValueError('Cargo target must be 1–1,000,000,000 whole pounds.')
    raw=b.get('destinations')
    if not isinstance(raw,list) or not 1<=len(raw)<=40 or any(not isinstance(i,str) for i in raw):
        raise ValueError('Choose 1–40 destination ICAO codes.')
    destinations=sorted(set(i.strip().upper() for i in raw))
    if any(not re.fullmatch('[A-Z0-9]{3,4}',i) or i not in airports for i in destinations):
        raise ValueError('Every destination must be a known airport ICAO code.')
    try:
        starts=datetime.strptime(b.get('start_date',''),'%Y-%m-%d').replace(tzinfo=timezone.utc)
        ends=datetime.strptime(b.get('end_date',''),'%Y-%m-%d').replace(tzinfo=timezone.utc)+timedelta(days=1)
    except (ValueError,TypeError,OverflowError): raise ValueError('Use valid start and end dates.')
    if not 2000<=starts.year<=2100 or not 2000<=ends.year<=2101 or ends<=starts or (ends-starts).days>366:
        raise ValueError('Use a campaign period of 1–366 days between 2000 and 2100.')
    return (title.strip(),description.strip(),starts.timestamp(),ends.timestamp(),target,json.dumps(destinations))


def campaigns(con, pid, staff=False):
    rows=con.execute("SELECT * FROM cargo_campaigns " + ("WHERE state!='discarded' " if staff else "WHERE state IN ('published','archived') ") +
                     "ORDER BY CASE WHEN state IN ('draft','published') THEN 0 ELSE 1 END,created_at DESC,id DESC LIMIT 100").fetchall()
    result=[];now=time.time()
    for row in rows:
        c=dict(row);dest=json.loads(c.pop('destinations'));c.pop('created_by',None)
        marks=','.join('?' for _ in dest)
        tally=con.execute(f'''SELECT COALESCE(SUM(payload_lbs),0) AS cargo_lbs,COUNT(*) AS flights,
            COUNT(DISTINCT pilot_id) AS pilots,
            COALESCE(SUM(CASE WHEN pilot_id=? THEN payload_lbs ELSE 0 END),0) AS personal_lbs
            FROM pireps WHERE {QUALIFY} AND filed_at>=? AND filed_at<? AND arr IN ({marks})''',
            (pid,c['starts'],min(c['ends'],c['archived_at']) if c['archived_at'] else c['ends'],*dest)).fetchone()
        c.update(dict(tally));c['destinations']=dest
        c['pct']=min(100,round(c['cargo_lbs']/c['target_lbs']*100,1))
        c['goal_met']=c['cargo_lbs']>=c['target_lbs']
        c['phase']='Draft' if c['state']=='draft' else 'Archived' if c['state']=='archived' else 'Upcoming' if now<c['starts'] else 'Ended' if now>=c['ends'] else 'Active'
        c['contributor_badge']=c['state']!='draft' and c['goal_met'] and c['personal_lbs']>0
        result.append(c)
    return result


def register(app,context):
    def db():
        con=sqlite3.connect(context['DB_PATH'],timeout=2);con.row_factory=sqlite3.Row;return con
    def reply(body,status=200):
        r=jsonify(body);r.status_code=status;r.headers['Cache-Control']='private, no-store';return r
    def user(staff=False):
        import auth
        p=auth.current()
        if not p:return None,reply({'error':'Please sign in.'},401)
        if staff and not p.get('staff'):return None,reply({'error':'Staff access required.'},403)
        return p,None

    @app.get('/api/pilot/cargo-passport')
    def cargo_passport():
        p,error=user()
        if error is not None:return error
        with closing(db()) as con:
            data=passport(con,context['AIRPORTS'],p['id'])
        return reply(data)

    @app.get('/api/pilot/cargo-campaigns')
    def cargo_campaigns():
        p,error=user()
        if error is not None:return error
        with closing(db()) as con:data=campaigns(con,p['id'])
        return reply({'campaigns':data})

    @app.route('/api/staff/cargo-campaigns',methods=['GET','POST'])
    def staff_cargo_campaigns():
        p,error=user(True)
        if error is not None:return error
        if request.method=='GET':
            with closing(db()) as con:data=campaigns(con,p['id'],True)
            return reply({'campaigns':data})
        try:values=campaign_input(request.get_json(silent=True),context['AIRPORTS'])
        except ValueError as exc:return reply({'error':str(exc)},400)
        with closing(db()) as con,con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute("SELECT COUNT(*) FROM cargo_campaigns WHERE state IN ('draft','published')").fetchone()[0]>=20:
                return reply({'error':'Archive an old campaign before adding another (20 open campaigns maximum).'},409)
            cur=con.execute('''INSERT INTO cargo_campaigns
                (title,description,starts,ends,target_lbs,destinations,created_at,created_by)
                VALUES(?,?,?,?,?,?,?,?)''',(*values,time.time(),p['id']))
            cid=cur.lastrowid
        return reply({'id':cid},201)

    @app.post('/api/staff/cargo-campaigns/<int:cid>')
    def campaign_action(cid):
        p,error=user(True)
        if error is not None:return error
        b=request.get_json(silent=True)
        action=b.get('action') if isinstance(b,dict) else None
        if action not in ('publish','archive'):return reply({'error':'Choose publish or archive.'},400)
        with closing(db()) as con,con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT state FROM cargo_campaigns WHERE id=?',(cid,)).fetchone()
            if not row or row['state']=='discarded':return reply({'error':'Campaign not found.'},404)
            if action=='publish' and row['state']!='draft':return reply({'error':'Only drafts can be published.'},409)
            if action=='archive' and row['state']=='draft':
                # Discarded drafts remain staff-only; never expose them by archiving.
                con.execute("UPDATE cargo_campaigns SET state='discarded',archived_at=? WHERE id=?",(time.time(),cid))
            else:
                con.execute('UPDATE cargo_campaigns SET state=?,archived_at=COALESCE(archived_at,?) WHERE id=?',
                            ('published' if action=='publish' else 'archived',time.time() if action=='archive' else None,cid))
        return reply({'ok':True})
