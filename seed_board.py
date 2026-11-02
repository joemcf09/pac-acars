"""Settles who holds the database write lock, then fills the mission board.

Run this with the website STOPPED (fix_board.sh does that for you). With nothing
else touching the database, two things become knowable that are invisible while
the site is running:

  1. Is the write lock held by something outside the website? If the lock is
     still taken with the service stopped, no amount of fixing va.py will help --
     the holder is a stray process or a leaked transaction somewhere else.

  2. How long does mission_board() take uncontended? That is the number that
     decides whether the generation loop is the problem.

Then it fills the board, because an empty board is what makes mission_board()
expensive: it generates LIVE_BOARD_SIZE (14) minus however many are already
open, so an empty board means the maximum amount of work, inside the write
transaction, on every single call. The site cannot dig itself out of that --
every attempt times out at 30 seconds and rolls back, so the board stays empty
and the next request repeats it. Filling it once, with nothing competing, drops
the per-request cost to almost nothing.

Nothing here deletes anything. It writes missions and reads counts.
"""
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def rule(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def counts(db_path):
    """Open missions per board, straight from the database."""
    out = {}
    con = sqlite3.connect(db_path, timeout=10)
    try:
        for key, sql in (
            ("live_open", "SELECT COUNT(*) FROM live_missions WHERE status='open'"),
            ("live_all", "SELECT COUNT(*) FROM live_missions"),
            ("jobs_open", "SELECT COUNT(*) FROM jobs WHERE status='open'"),
            ("jobs_all", "SELECT COUNT(*) FROM jobs"),
            ("urgent_open", "SELECT COUNT(*) FROM urgent WHERE status='open'"),
        ):
            try:
                out[key] = con.execute(sql).fetchone()[0]
            except sqlite3.Error as e:
                out[key] = f"unreadable ({e})"
    finally:
        con.close()
    return out


# ------------------------------------------------------------------ 1. the lock
rule("1. Is anything holding the write lock, with the website stopped?")

import app  # noqa: E402  wires up DB_PATH, airports, routes, fleet
import va   # noqa: E402

db_path = str(app.DB_PATH)
print(f"database: {db_path}")

probe = sqlite3.connect(db_path, timeout=5)
try:
    probe.execute("BEGIN IMMEDIATE")
    probe.execute("ROLLBACK")
    print("\nRESULT: the lock is FREE.")
    print("        So the holder was one of the website's own threads, which fits")
    print("        the generation loop holding it while it grinds. Carry on.")
    lock_free = True
except sqlite3.OperationalError as e:
    print(f"\nRESULT: the lock is STILL HELD with the website stopped -- {e}")
    print("        This is the finding that changes everything. Something other")
    print("        than the website has an open write transaction, so va.py is")
    print("        not the culprit. Find the holder before touching any code:")
    print(f"            lsof {db_path}")
    lock_free = False
finally:
    probe.close()

if not lock_free:
    print("\nStopping here on purpose. Filling the board cannot succeed while the")
    print("lock is held, and a half-finished attempt would muddy the picture.")
    raise SystemExit(2)


# --------------------------------------------------------------- 2. before
rule("2. What is on the boards before we start?")

before = counts(db_path)
for k, v in before.items():
    print(f"  {k:14} {v}")

size = getattr(va, "LIVE_BOARD_SIZE", "?")
print(f"\n  LIVE_BOARD_SIZE is {size}.")
if isinstance(before.get("live_open"), int):
    print(f"  Open now: {before['live_open']}, so mission_board() wants to generate "
          f"{max(0, (size if isinstance(size, int) else 0) - before['live_open'])}")
    print("  missions inside one write transaction. That is the cost we are removing.")


# ---------------------------------------------------------------- 3. timing
rule("3. How long does mission_board() take with nothing competing?")

t0 = time.time()
try:
    board = va.mission_board()
except Exception as e:
    print(f"FAILED after {time.time() - t0:.1f}s: {type(e).__name__}: {e}")
    print("\nThe website has NOT been restarted. Bring it up with: systemctl start pac")
    raise SystemExit(1)
first = time.time() - t0

mid = counts(db_path)
print(f"took {first:.1f}s")
print(f"board entries returned: {len(board)}")
print(f"live_missions open now: {mid.get('live_open')} (was {before.get('live_open')})")

if first > 20:
    print("\nREADING: slower than the 30s lock timeout tolerates under load.")
    print("         Generation is too slow and has to come out of the write")
    print("         transaction. Filling the board helps today; the loop still")
    print("         needs restructuring to stay fixed.")
elif first > 5:
    print("\nREADING: slow, but survivable now the board is full. Step 4 is the")
    print("         one that matters.")
else:
    print("\nREADING: fast uncontended. The empty board was the whole cost.")


# ------------------------------------------- 4. the call that predicts page loads
rule("4. Second call -- this predicts what your pages will actually do")

t1 = time.time()
try:
    va.mission_board()
    second = time.time() - t1
    after = counts(db_path)
    print(f"took {second:.2f}s with {after.get('live_open')} already open")
    if second < 2:
        print("\nThis is the result we wanted. With a full board the call is cheap,")
        print("so it stops parking the write lock and stops stalling every other")
        print("request behind it.")
    else:
        print("\nStill slow with a full board. That means the cost is NOT only")
        print("generation, and the next step is to find out what else is in that")
        print("transaction. Send me this output rather than changing anything.")
except Exception as e:
    print(f"second call failed: {type(e).__name__}: {e}")


rule("Done")
print("Start the website again:   systemctl start pac")
print("Leave the Discord bot stopped for now so the picture stays clean.")
