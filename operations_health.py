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
                          'discord':safe(discord),'backups':safe(lambda:backup_health(context['BACKUP_DIR'],now))})
        response.headers['Cache-Control']='private, no-store'
        return response
