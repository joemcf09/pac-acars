"""Staff-only read-only operational signals. Never starts services or generates work."""
import json
import math
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from flask import jsonify


def timestamp(value):
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else None


def age(now, value):
    value = timestamp(value)
    return max(0, now-value) if value and value <= now+60 else None


def worker_health(data, now):
    p = Path(data) / 'mission-worker-status.json'
    if not p.exists(): return {'level':'unknown','message':'No worker report yet. Wait for the next scheduled refresh.'}
    if p.stat().st_size > 65536: raise ValueError('Invalid report')
    s = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(s, dict): raise ValueError('Invalid report')
    state = s.get('state')
    elapsed = age(now, s.get('last_success_at'))
    started_age = age(now, s.get('started_at'))
    level, message = 'ok', 'Mission refresh is current.'
    if state == 'failed': level, message = 'warning', 'The last refresh failed. Check the mission worker journal.'
    elif state == 'running' and (started_age is None or started_age > 120): level, message = 'warning', 'Worker report is stale; the last run may have stopped.'
    elif elapsed is None or elapsed > 600: level, message = 'warning', 'No successful refresh recorded in the last 10 minutes.'
    elif state == 'deferred': level, message = 'notice', 'Publication deferred because pilot activity changed the inputs. The worker will retry.'
    elif state == 'running': level, message = 'notice', 'Refresh in progress.'
    elif state != 'success': level, message = 'unknown', 'Worker report has an unrecognized state.'
    return {'level':level,'message':message,'state':state if state in ('success','running','failed','deferred') else 'unknown',
            'last_success_at':timestamp(s.get('last_success_at')),'age_seconds':elapsed,
            'duration_seconds':s.get('duration_seconds') if isinstance(s.get('duration_seconds'),(int,float)) and math.isfinite(s['duration_seconds']) else None}


def board_health(db, now):
    day = time.strftime('%Y-%m-%d', time.gmtime(now))
    with closing(sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True,timeout=2)) as c:
        missions = c.execute("SELECT COUNT(*) FROM live_missions WHERE status='open' AND expires>=?",(now,)).fetchone()[0]
        urgent = c.execute("SELECT COUNT(*) FROM urgent WHERE status='open' AND expires>=?",(now,)).fetchone()[0]
        jobs = partners = 0
        for kind, raw in c.execute("SELECT kind,data FROM jobs WHERE status='open' AND (day=? OR kind='contract')",(day,)):
            d=json.loads(raw)
            if (d.get('expires') or float('inf')) < now:continue
            if kind=='contract':partners+=1
            else:jobs+=1
    return {'level':'ok' if missions+jobs+partners+urgent else 'warning','message':'Open, unexpired offers; booked flights and scheduled routes are excluded.',
            'counts':{'Missions':missions,'Jobs':jobs,'Partners':partners,'Urgent':urgent}}


def backup_health(folder, now):
    folder=Path(folder)
    if not folder.exists():return {'level':'warning','message':'No automatic or manual application backup found.'}
    found=[]
    for p in folder.iterdir():
        db=p/'logbook.db'
        if p.is_dir() and db.is_file() and db.stat().st_size:
            marker=p/'backup-complete.json';completed=None
            if marker.exists():completed=timestamp(json.loads(marker.read_text()).get('completed_at'))
            found.append((completed or db.stat().st_mtime,p.name,completed))
    if not found:return {'level':'warning','message':'No application database backup found.'}
    when,name,completed=max(found)
    elapsed=age(now,when)
    if completed is None:level,message='unknown','Backup files found, but this older backup has no completion record.'
    elif elapsed is None or elapsed>86400:level,message='warning','Latest completed application backup is older than 24 hours or has an invalid timestamp.'
    else:level,message='ok','Application backup completed within the last 24 hours.'
    return {'level':level,'message':message,'name':name,'completed_at':completed,'file_time':when,'age_seconds':elapsed,
            'note':'Completion does not verify restore integrity or an off-server copy. Deployment backups are separate.'}


def vatsim_flights(db, prefix, now, days=60):
    """PAC flights flown on VATSIM under PAC's own callsign prefix in the last `days`: what VATSIM's Virtual Airline
    Associate audit counts (50 flights by 10 pilots in 60 days, PGI callsigns). A flight counts when PAC ACARS saw the
    pilot connected to VATSIM for at least 60% of its checks with a callsign starting with the prefix."""
    with closing(sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True,timeout=2)) as c:
        rows=c.execute("""SELECT filed_at, pilot_id, dep, arr, flight_number, json_extract(detail,'$.online') FROM pireps
            WHERE filed_at>? AND COALESCE(demo,0)=0 AND COALESCE(review_status,'')!='Rejected'""",(now-days*86400,)).fetchall()
    total=len(rows);out=[]
    for filed,pilot,dep,arr,fn,on in rows:
        try:on=json.loads(on) if on else None
        except ValueError:on=None
        if not on or on.get('network')!='VATSIM' or (on.get('share') or 0)<0.6:continue
        cs=str(on.get('callsign') or '').upper()
        out.append({'date':time.strftime('%Y-%m-%d',time.gmtime(filed)),'callsign':cs,'dep':dep,'arr':arr,'pilot':pilot,
                    'counts':cs.startswith(prefix.upper())})
    return total,out


def vatsim_readiness(db, prefix, now):
    total,flights=vatsim_flights(db,prefix,now)
    ok=[f for f in flights if f['counts']]
    pilots=len({f['pilot'] for f in ok})
    share=round(100*len(ok)/total) if total else 0
    ready=len(ok)>=50 and pilots>=10
    wrong=len(flights)-len(ok)
    msg=('Meets VATSIM\'s Virtual Airline Associate activity requirement. You can apply at my.vatsim.net.' if ready else
         f'VATSIM needs 50 flights by 10 pilots in 60 days under {prefix} callsigns: {max(0,50-len(ok))} flights and {max(0,10-pilots)} pilots to go.')
    if not ready and share>80:msg+=f' {share}% of PAC\'s flights are on VATSIM: over 80%, VATSIM may waive the activity numbers, so it\'s worth asking when you apply.'
    if wrong:msg+=f' {wrong} VATSIM flight{"s" if wrong>1 else ""} used another callsign and don\'t count: file as {prefix}.'
    return {'level':'ok' if ready else 'notice','message':msg,'counts':{'VATSIM flights':len(ok),'Pilots':pilots,
            'Online share':f'{share}%','Other callsigns':wrong}}


def register(app, context):
    @app.get('/api/staff/operations-health')
    def health():
        import auth, botlink
        who=auth.current()
        if not who or not who.get('staff'):return jsonify({'error':'Staff access required.'}),403
        now=time.time()
        def safe(fn):
            try:return fn()
            except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):return {'level':'unknown','message':'This health signal could not be read. Check the server journal.'}
        def discord():
            enabled=bool(botlink.enabled());last=timestamp(botlink._seen.get('poll'));elapsed=age(now,last)
            return {'level':'notice' if not enabled else 'ok' if elapsed is not None and elapsed<30 else 'warning',
                    'message':'Bot is disabled in site settings.' if not enabled else 'Recent event-poll heartbeat detected.' if elapsed is not None and elapsed<30 else 'No event-poll heartbeat in the last 30 seconds.',
                    'last_seen':last,'age_seconds':elapsed,'note':'Heartbeat indicates communication with PAC; it does not prove Discord message delivery.'}
        response=jsonify({'checked_at':now,'worker':safe(lambda:worker_health(context['DATA'],now)),
                          'boards':safe(lambda:board_health(context['DB_PATH'],now)),
                          'discord':safe(discord),'backups':safe(lambda:backup_health(context['BACKUP_DIR'],now)),
                          'vatsim':safe(lambda:vatsim_readiness(context['DB_PATH'],context['filing_icao'](),now))})
        response.headers['Cache-Control']='private, no-store'
        return response


    @app.get('/healthz')
    def healthz():
        """For an outside monitor (UptimeRobot): 200 "OK" when the mission worker, mission boards, Discord bot and backups are
        healthy, 503 naming what isn't. Public, so it says only which part has a problem, never any data."""
        import botlink
        now=time.time()
        problems=[]
        def check(name, fn):
            try:
                if fn().get('level') in ('warning','unknown'):problems.append(name)
            except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):problems.append(name)
        check('mission worker',lambda:worker_health(context['DATA'],now))
        check('mission boards',lambda:board_health(context['DB_PATH'],now))
        def bot():   # looser than the staff page (30 s): a monitor checking every 5 minutes shouldn't alarm on a short blip
            if not botlink.enabled():return {'level':'ok'}
            elapsed=age(now,timestamp(botlink._seen.get('poll')))
            return {'level':'ok' if elapsed is not None and elapsed<180 else 'warning'}
        check('discord bot',bot)
        check('backups',lambda:backup_health(context['BACKUP_DIR'],now))
        body,code=('OK',200) if not problems else ('PROBLEM: '+', '.join(problems),503)
        return body,code,{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}


    @app.get('/api/staff/vatsim-flights.csv')
    def vatsim_csv():
        """The flight list VATSIM's audit asks for: callsign, origin, destination and date (no pilot names)."""
        import auth
        who=auth.current()
        if not who or not who.get('staff'):return jsonify({'error':'Staff access required.'}),403
        _,flights=vatsim_flights(context['DB_PATH'],context['filing_icao'](),time.time())
        lines=['callsign,origin,destination,date']+[f"{f['callsign']},{f['dep']},{f['arr']},{f['date']}" for f in flights if f['counts']]
        return '\n'.join(lines)+'\n',200,{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename="pac-vatsim-flights.csv"'}
