"""Generate against a snapshot; publish only if inputs have not changed."""
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

BOARDS = ('jobs', 'live_missions', 'urgent')
INPUTS = BOARDS + ('airframes', 'pilots')

def worker_data_dir():
    return Path(os.environ.get('PAC_DATA_DIR') or Path(__file__).resolve().parent / 'data').expanduser().resolve()

def rows(con, table):
    return {r[0]: tuple(r) for r in con.execute('SELECT * FROM ' + table)}

def publish(live, before, after):
    """Optimistic atomic publish: never replace a concurrent booking or pilot move."""
    live.execute('BEGIN IMMEDIATE')
    try:
        if any(rows(live, table) != before[table] for table in INPUTS):
            live.rollback()
            return False
        published_at = time.time()
        for table in BOARDS:
            columns = [r[1] for r in live.execute('PRAGMA table_info(' + table + ')')]
            key = columns[0]
            for id in before[table].keys() - after[table].keys():
                live.execute(f'DELETE FROM {table} WHERE {key}=?', (id,))
            for id, row in after[table].items():
                if before[table].get(id) == row:
                    continue
                # Dispatch timestamps reflect publication, so a bot polling
                # during generation cannot advance past an unpublished offer.
                if 'created' in columns:
                    ci = columns.index('created')
                    if id not in before[table] or row[ci] != before[table][id][ci]:
                        row = list(row); row[ci] = published_at
                        if 'data' in columns:
                            di = columns.index('data'); data = json.loads(row[di])
                            if 'created' in data: data['created'] = published_at
                            row[di] = json.dumps(data)
                        row = tuple(row)
                if id in before[table]:
                    assignments = ','.join(c + '=?' for c in columns[1:])
                    live.execute(f'UPDATE {table} SET {assignments} WHERE {key}=?', (*row[1:], id))
                else:
                    live.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})', row)
        live.commit()
        return True
    except BaseException:
        live.rollback()
        raise

def _run_once():
    import app as A
    import va
    started = time.monotonic()
    # Import initializes the existing application schema, then all expensive work
    # occurs on this private snapshot, never while holding the live write lock.
    with tempfile.TemporaryDirectory(prefix='mission-worker-', dir=A.DATA) as temp:
        path = Path(temp) / 'snapshot.db'
        with contextlib.closing(sqlite3.connect(A.DB_PATH, timeout=2)) as live:
            with contextlib.closing(sqlite3.connect(path)) as snap:
                live.backup(snap)
                before = {t: rows(snap, t) for t in INPUTS}
                locations = sorted({r[0] or va.HOME_BASE for r in snap.execute("SELECT location FROM pilots WHERE status='Active'")}) or [va.HOME_BASE]
        here = locations[int(time.time() // 120) % len(locations)]
        class SnapshotConnection(sqlite3.Connection):
            def __exit__(self, *args):
                try: return super().__exit__(*args)
                finally: self.close()
        def snapshot_db():
            con = sqlite3.connect(path, timeout=2, factory=SnapshotConnection)
            con.row_factory = sqlite3.Row
            return con
        original = va.C['db']
        va.C['db'] = snapshot_db
        try:
            for fn in (va.refresh_mission_board, va.refresh_jobs_today, va.refresh_urgent_missions):
                print('Generating ' + fn.__name__ + ' for ' + here, flush=True)
                fn(here=here)
        finally:
            va.C['db'] = original
        with contextlib.closing(sqlite3.connect(path)) as snap:
            after = {t: rows(snap, t) for t in BOARDS}
        with contextlib.closing(sqlite3.connect(A.DB_PATH, timeout=2)) as live:
            applied = publish(live, before, after)
        print(json.dumps({'published': applied, 'location': here, 'seconds': round(time.monotonic()-started, 2), 'reason': 'complete' if applied else 'concurrent activity; retry next run'}), flush=True)
        return applied


def record_status(data, **updates):
    import os
    path = Path(data) / 'mission-worker-status.json'
    try: state = json.loads(path.read_text())
    except (OSError, ValueError): state = {}
    if not isinstance(state, dict): state = {}
    state.update(updates)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state), encoding='utf-8')
    os.replace(temp, path)


def run_once():
    data = worker_data_dir()
    started = time.time()
    record_status(data, state='running', started_at=started, error=None)
    try:
        applied = _run_once()
        result = dict(state='success' if applied else 'deferred', finished_at=time.time(), duration_seconds=round(time.time()-started, 2), error=None)
        if applied: result['last_success_at'] = time.time()
        record_status(data, **result)
        return applied
    except BaseException as exc:
        record_status(data, state='failed', finished_at=time.time(), duration_seconds=round(time.time()-started, 2), error=type(exc).__name__)
        raise

def main():
    import fcntl
    import signal
    # Lock before importing app, so overlapping manual/timer runs do not race.
    data = worker_data_dir()
    with (data / 'mission-worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another worker is active; skipping.', flush=True)
            return
        def timed_out(signum, frame):
            raise TimeoutError('Mission generation exceeded 45 seconds; live offers unchanged unless already published')
        signal.signal(signal.SIGALRM, timed_out)
        signal.alarm(45)
        try:
            run_once()
        finally:
            signal.alarm(0)

if __name__ == '__main__':
    main()
