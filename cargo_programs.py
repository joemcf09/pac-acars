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
    cols={r[1] for r in con.execute('PRAGMA table_info(cargo_campaigns)')}
    for col,typ in (('patch','TEXT'),('reward_cash','REAL DEFAULT 0'),('baseline_lbs','INTEGER DEFAULT 0'),('launch_at','REAL')):
        if col not in cols:con.execute(f'ALTER TABLE cargo_campaigns ADD COLUMN {col} {typ}')
    con.execute('''CREATE TABLE IF NOT EXISTS cargo_campaign_wrapups (campaign_id INTEGER PRIMARY KEY, at REAL NOT NULL,
        cargo_lbs REAL, flights INTEGER, pilots INTEGER, goal_met INTEGER, paid INTEGER DEFAULT 0)''')
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
        c['flown_lbs']=c['cargo_lbs'];c['cargo_lbs']=c['cargo_lbs']+(c.get('baseline_lbs') or 0)
        c['pct']=min(100,round(c['cargo_lbs']/c['target_lbs']*100,1))
        c['goal_met']=c['cargo_lbs']>=c['target_lbs']
        c['phase']='Draft' if c['state']=='draft' else 'Archived' if c['state']=='archived' else 'Upcoming' if now<c['starts'] else 'Ended' if now>=c['ends'] else 'Active'
        c['contributor_badge']=c['state']!='draft' and c['goal_met'] and c['personal_lbs']>0
        c['top']=top_contributors(con,c,dest) if c['state']!='draft' else []
        result.append(c)
    return result


def _window(c):
    return c['starts'],(min(c['ends'],c['archived_at']) if c.get('archived_at') else c['ends'])


def top_contributors(con, c, dest, n=5):
    marks=','.join('?' for _ in dest);lo,hi=_window(c)
    return [dict(r) for r in con.execute(f'''SELECT p.pilot_id AS id,COALESCE(r.name,p.pilot_id) AS name,SUM(p.payload_lbs) AS cargo_lbs,COUNT(*) AS flights
        FROM (SELECT pilot_id,payload_lbs FROM pireps WHERE {QUALIFY} AND filed_at>=? AND filed_at<? AND arr IN ({marks})) p
        LEFT JOIN pilots r ON r.id=p.pilot_id GROUP BY p.pilot_id ORDER BY cargo_lbs DESC LIMIT ?''',(lo,hi,*dest,n))]


def auto_launch(con, now=None):
    """Publishes drafts set to launch themselves once their launch time comes, with a news post for the crews."""
    now=now or time.time();done=[]
    for row in con.execute("SELECT * FROM cargo_campaigns WHERE state='draft' AND launch_at IS NOT NULL AND launch_at<=?",(now,)).fetchall():
        c=dict(row);dest=json.loads(c['destinations'])
        con.execute("UPDATE cargo_campaigns SET state='published' WHERE id=? AND state='draft'",(c['id'],))
        body=(f"{c['description']} Goal: {c['target_lbs']:,} lb to {' · '.join(dest)} by "
              f"{datetime.fromtimestamp(c['ends']-1,timezone.utc).strftime('%b %d')}."
              +(f" Every contributor earns the patch and ${float(c.get('reward_cash') or 0):,.0f} if we hit the target." if c.get('reward_cash') else ''))
        con.execute('INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)',
                    (now,'event',f"{c['title']} is live",body,1,c['ends'],'PAC Operations'))
        # and the Discord announcement (posted by the PAC bot), written into the same transaction
        try:
            import botlink
            if botlink.enabled():
                reward=float(c.get('reward_cash') or 0)
                text='\n'.join([c['description'],'',
                    f"🎯 **Shared goal:** {c['target_lbs']:,} lb delivered",
                    f"📍 **Destinations:** {' · '.join(dest)}",
                    f"📅 **{datetime.fromtimestamp(c['starts'],timezone.utc):%b %d} – {datetime.fromtimestamp(c['ends']-1,timezone.utc):%b %d, %Y} (UTC)**",'',
                    '**How to contribute:** fly any suitable PAC cargo flight into one of the destinations, complete it in PAC ACARS and file your PIREP. Every accepted delivery counts.','',
                    '🏅 **When we hit the target:** the campaign patch'+(f' and a **${reward:,.0f}** bonus to every contributor.' if reward>0 else ' for every contributor.'),'',
                    'Track progress under **Operations → Cargo campaigns**. Let\'s move the freight! ✈️'])
                con.execute('INSERT INTO bot_events (time, kind, data) VALUES (?,?,?)',(now,'site_news',json.dumps(
                    {'kind':'news','title':f"{c['title'].upper()} IS LIVE!",'body':text,'important':True,'author':'PAC Operations','updated':False,'number':None})))
        except Exception as e:print('campaign launch post:',e)
        done.append(c['id'])
    return done


def wrap_up(con, add_tx=None, now=None):
    """Closes each campaign once, after its end date or as soon as staff archive it: a news post with the result and top contributors,
    and the campaign's cash reward (if any) paid once to every contributor when the target was reached."""
    now=now or time.time();done=[]
    for row in con.execute("""SELECT * FROM cargo_campaigns c WHERE ((state='published' AND ends<=?) OR (state='archived' AND archived_at IS NOT NULL))
            AND NOT EXISTS (SELECT 1 FROM cargo_campaign_wrapups w WHERE w.campaign_id=c.id)""",(now,)).fetchall():
        c=dict(row);dest=json.loads(c['destinations']);marks=','.join('?' for _ in dest);lo,hi=_window(c)
        t=con.execute(f'''SELECT COALESCE(SUM(payload_lbs),0) lbs,COUNT(*) flights,COUNT(DISTINCT pilot_id) pilots
            FROM pireps WHERE {QUALIFY} AND filed_at>=? AND filed_at<? AND arr IN ({marks})''',(lo,hi,*dest)).fetchone()
        total=t['lbs']+(c.get('baseline_lbs') or 0);met=total>=c['target_lbs']
        everyone=top_contributors(con,c,dest,n=1000);paid=0
        reward=float(c.get('reward_cash') or 0)
        if met and reward>0 and add_tx:
            for p in everyone:
                add_tx(p['id'],'campaign',reward,f"{c['title']}: contributor reward",None,con);paid+=1
        lines=[f"{'Target reached' if met else 'Final total'}: {total:,.0f} of {c['target_lbs']:,} lb to {' · '.join(dest)}.",
               f"{t['flights']} deliveries by {max(t['pilots'],len(everyone))} pilots."]
        if everyone:
            lines.append('Top contributors: '+', '.join(f"{p['name']} ({p['cargo_lbs']:,.0f} lb)" for p in everyone[:5])+'.')
        if met:
            lines.append('Every contributor earned the campaign patch'+(f' and a ${reward:,.0f} bonus, paid to their wallet.' if reward>0 else '.'))
        else:
            lines.append('Thank you to everyone who flew. The next operation is coming.')
        con.execute('INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)',
                    (now,'event',f"{c['title']}: {'mission accomplished' if met else 'operation closed'}",' '.join(lines),1,now+21*86400,'PAC Operations'))
        con.execute('INSERT INTO cargo_campaign_wrapups (campaign_id,at,cargo_lbs,flights,pilots,goal_met,paid) VALUES (?,?,?,?,?,?,?)',
                    (c['id'],now,total,t['flights'],t['pilots'],int(met),paid))
        done.append(c['id'])
    return done


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

    def close_ended():
        try:
            with closing(db()) as con,con:
                con.execute('BEGIN IMMEDIATE');auto_launch(con);wrap_up(con,context['va'].add_tx)
        except Exception as e:print('campaign wrap-up:',e)

    @app.get('/api/pilot/cargo-campaigns')
    def cargo_campaigns():
        p,error=user()
        if error is not None:return error
        close_ended()
        with closing(db()) as con:data=campaigns(con,p['id'])
        return reply({'campaigns':data})

    @app.route('/api/staff/cargo-campaigns',methods=['GET','POST'])
    def staff_cargo_campaigns():
        p,error=user(True)
        if error is not None:return error
        if request.method=='GET':
            close_ended()
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
        if action=='extras':
            patch=str(b.get('patch') or '').strip()[:300]
            if patch and not re.fullmatch(r'(/static/[\w./-]+|https://[\w./%-]+)\.(png|jpg|jpeg|svg|webp)',patch,re.I):
                return reply({'error':'Patch must be an image link (PNG, JPG, SVG or WebP).'},400)
            try:reward=max(0.0,min(1e6,float(b.get('reward_cash') or 0)));base=max(0,min(10**9,int(b.get('baseline_lbs') or 0)))
            except (TypeError,ValueError):return reply({'error':'Reward and starting pounds must be numbers.'},400)
            with closing(db()) as con,con:
                if not con.execute("SELECT 1 FROM cargo_campaigns WHERE id=? AND state!='discarded'",(cid,)).fetchone():return reply({'error':'Campaign not found.'},404)
                if con.execute('SELECT 1 FROM cargo_campaign_wrapups WHERE campaign_id=?',(cid,)).fetchone():return reply({'error':'This campaign has already closed and paid out.'},409)
                con.execute('UPDATE cargo_campaigns SET patch=?,reward_cash=?,baseline_lbs=? WHERE id=?',(patch or None,reward,base,cid))
            return reply({'ok':True})
        if action=='edit':
            try:values=campaign_input(b,context['AIRPORTS'])
            except ValueError as exc:return reply({'error':str(exc)},400)
            with closing(db()) as con,con:
                con.execute('BEGIN IMMEDIATE')
                row=con.execute('SELECT state FROM cargo_campaigns WHERE id=?',(cid,)).fetchone()
                if not row or row['state']=='discarded':return reply({'error':'Campaign not found.'},404)
                if row['state']!='draft':return reply({'error':'Only drafts can be edited. Published campaigns keep their rules.'},409)
                con.execute('UPDATE cargo_campaigns SET title=?,description=?,starts=?,ends=?,target_lbs=?,destinations=? WHERE id=?',(*values,cid))
            return reply({'ok':True})
        if action in ('schedule','unschedule'):
            with closing(db()) as con,con:
                row=con.execute('SELECT state,starts FROM cargo_campaigns WHERE id=?',(cid,)).fetchone()
                if not row or row['state']!='draft':return reply({'error':'Only drafts can be set to launch.'},409)
                when=None
                if action=='schedule':
                    try:
                        when=(datetime.strptime(b['launch_date'],'%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() if b.get('launch_date') else row['starts'])
                    except (ValueError,TypeError):return reply({'error':'Use a valid launch date.'},400)
                con.execute('UPDATE cargo_campaigns SET launch_at=? WHERE id=?',(when,cid))
            close_ended()          # a launch date that has already passed goes live now
            return reply({'ok':True})
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
        if action=='archive':close_ended()      # pays the reward and posts the result right away
        return reply({'ok':True})
