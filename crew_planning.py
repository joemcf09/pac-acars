"""Member-only flight coordination. No booking, wallet or flight-credit writes."""
import sqlite3,time,math
from contextlib import closing
from flask import request,jsonify

def register(app,context):
    def db():
        c=sqlite3.connect(context['DB_PATH'],timeout=10);c.row_factory=sqlite3.Row;return c
    with closing(db()) as c,c:
        c.execute('CREATE TABLE IF NOT EXISTS crew_plans (id INTEGER PRIMARY KEY,owner TEXT NOT NULL,owner_name TEXT NOT NULL,dep TEXT NOT NULL,arr TEXT NOT NULL,aircraft TEXT NOT NULL,departure REAL NOT NULL,mode TEXT NOT NULL,simulator TEXT NOT NULL,addon TEXT NOT NULL,note TEXT NOT NULL,contact TEXT NOT NULL,capacity INTEGER NOT NULL,state TEXT NOT NULL,created REAL NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS crew_plan_members (plan_id INTEGER NOT NULL,pilot TEXT NOT NULL,name TEXT NOT NULL,contact TEXT NOT NULL,joined REAL NOT NULL,PRIMARY KEY(plan_id,pilot))')
    def reply(data,status=200):
        r=jsonify(data);r.status_code=status;r.headers['Cache-Control']='private, no-store';return r
    def text(b,k,limit,required=False):
        v=b.get(k,'')
        if not isinstance(v,str):raise ValueError('Invalid '+k)
        v=v.strip()
        if len(v)>limit or (required and not v):raise ValueError('Check '+k)
        return v
    @app.route('/api/crew-plans',methods=['GET','POST'])
    @app.post('/api/crew-plans/<int:plan_id>/<action>')
    def crew_plans(plan_id=None,action=None):
        import auth
        p=auth.current()
        if not p:return reply({'error':'Please sign in.'},401)
        pid=p['id'];name=p.get('name') or pid;now=time.time()
        try:
            if request.method=='GET':
                with closing(db()) as c:
                    # Expired posts disappear automatically; owners can still close recent posts.
                    rows=c.execute("SELECT * FROM crew_plans WHERE (departure>? AND state IN ('open','complete')) OR (owner=? AND departure>? ) ORDER BY departure LIMIT 150",(now,pid,now-86400*7)).fetchall()
                    plans=[]
                    for r in rows:
                        q=dict(r);q['members']=[dict(x) for x in c.execute('SELECT pilot,name,contact FROM crew_plan_members WHERE plan_id=? ORDER BY joined',(q['id'],))];q['expired']=q['departure']<=now;q['can_manage']=pid==q['owner'] or bool(p.get('staff'));plans.append(q)
                return reply({'plans':plans,'now':now})
            b=request.get_json(silent=True)
            if not isinstance(b,dict):raise ValueError('Expected a form.')
            with closing(db()) as c,c:
                c.execute('BEGIN IMMEDIATE')
                if plan_id is None:
                    dep=text(b,'dep',4,True).upper();arr=text(b,'arr',4,True).upper();ac=text(b,'aircraft',20,True)
                    if dep==arr or dep not in context['AIRPORTS'] or arr not in context['AIRPORTS']:raise ValueError('Choose two different known ICAO airports.')
                    if ac not in context['FLEET'] or context['FLEET'][ac].get('retired'):raise ValueError('Choose a current PAC aircraft type.')
                    departure=b.get('departure')
                    if isinstance(departure,bool) or not isinstance(departure,(int,float)) or not math.isfinite(departure) or not now<departure<=now+30*86400:raise ValueError('Choose a departure within the next 30 days.')
                    mode=b.get('mode');capacity=b.get('capacity')
                    if mode not in ('shared','group'):raise ValueError('Choose a flight format.')
                    if type(capacity) is not int or not 1<=capacity<=10:raise ValueError('Choose 1–10 joining pilots.')
                    if mode=='shared':capacity=1
                    if c.execute("SELECT COUNT(*) FROM crew_plans WHERE owner=? AND departure>? AND state IN ('open','complete')",(pid,now)).fetchone()[0]>=5:raise ValueError('You already have five upcoming posts.')
                    sim=text(b,'simulator',60,True);addon=text(b,'addon',100,mode=='shared');note=text(b,'note',800);contact=text(b,'contact',80)
                    if c.execute('SELECT 1 FROM crew_plans WHERE owner=? AND dep=? AND arr=? AND departure=? AND state!=?',(pid,dep,arr,departure,'cancelled')).fetchone():raise ValueError('That flight is already posted.')
                    c.execute('INSERT INTO crew_plans(owner,owner_name,dep,arr,aircraft,departure,mode,simulator,addon,note,contact,capacity,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,name,dep,arr,ac,departure,mode,sim,addon,note,contact,capacity,'open',now))
                    return reply({'ok':True},201)
                r=c.execute('SELECT * FROM crew_plans WHERE id=?',(plan_id,)).fetchone()
                if not r:return reply({'error':'Post not found.'},404)
                owner=pid==r['owner'];staff=bool(p.get('staff'))
                if action in ('complete','reopen','cancel','finish'):
                    if not(owner or staff):return reply({'error':'Only the organizer or staff can manage this post.'},403)
                    if r['state'] in ('cancelled','finished'):raise ValueError('This post is closed.')
                    if action in ('complete','reopen') and r['departure']<=now:raise ValueError('This departure has passed.')
                    state={'complete':'complete','reopen':'open','cancel':'cancelled','finish':'finished'}[action]
                    c.execute('UPDATE crew_plans SET state=? WHERE id=?',(state,plan_id))
                elif action=='leave':
                    c.execute('DELETE FROM crew_plan_members WHERE plan_id=? AND pilot=?',(plan_id,pid))
                elif action=='join':
                    if owner:raise ValueError('You are already the organizer.')
                    if r['state']!='open' or r['departure']<=now:raise ValueError('This post is no longer accepting crew.')
                    if c.execute('SELECT 1 FROM crew_plan_members WHERE plan_id=? AND pilot=?',(plan_id,pid)).fetchone():return reply({'ok':True})
                    if c.execute('SELECT COUNT(*) FROM crew_plan_members WHERE plan_id=?',(plan_id,)).fetchone()[0]>=r['capacity']:raise ValueError('The crew places are full.')
                    c.execute('INSERT INTO crew_plan_members VALUES(?,?,?,?,?)',(plan_id,pid,name,text(b,'contact',80),now))
                else:raise ValueError('Unknown action.')
            return reply({'ok':True})
        except ValueError as e:return reply({'error':str(e)},400)
    @app.get('/api/fleet-reservations')
    def fleet_reservations():
        import auth,json
        if not auth.current():return reply({'error':'Please sign in.'},401)
        result={}
        with closing(db()) as c:
            for row in c.execute('SELECT b.pilot_id,b.data,p.name FROM bookings b LEFT JOIN pilots p ON p.id=b.pilot_id'):
                try:b=json.loads(row['data'])
                except (ValueError,TypeError):continue
                if not isinstance(b,dict) or not b.get('airframe'):continue
                mission=b.get('mission') or {}
                result[b['airframe']]={'pilot_id':row['pilot_id'],'pilot_name':row['name'] or row['pilot_id'],'flight':b.get('flight_number') or '', 'dep':(mission.get('origin') or {}).get('icao',''),'arr':(mission.get('destination') or {}).get('icao','')}
        active={f['reg']:{'on_ground':bool(f.get('on_ground')),'flight':f.get('flight','')} for f in context.get('live_flights',lambda member:[])(True) if f.get('reg')}
        return reply({'reservations':result,'active_airframes':active})
