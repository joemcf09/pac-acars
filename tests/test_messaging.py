"""Crew mail data logic: direct send, staff broadcast fan-out, unread counting, read, per-side delete, and the
inbox/sent/unread filters (mirrors the endpoint SQL against the real schema)."""
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import messaging

con = sqlite3.connect(":memory:")
con.row_factory = sqlite3.Row
con.execute("CREATE TABLE pilots (id TEXT PRIMARY KEY, name TEXT, status TEXT, staff INT)")
for pid, name, staff in [("PAC0001", "Joseph", 1), ("PAC0014", "Alan", 0), ("PAC0002", "Jose", 0)]:
    con.execute("INSERT INTO pilots VALUES (?,?,?,?)", (pid, name, "Active", staff))
messaging.migrate(con)

fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got}]"))
    if not ok:
        fails.append(name)

def send(sender, to, subject, body):
    recips = [to] if to not in ("ALL",) else [r[0] for r in con.execute("SELECT id FROM pilots WHERE status='Active' AND id!=?", (sender,))]
    for rc in recips:
        con.execute("INSERT INTO messages (sender, recipient, subject, body, time) VALUES (?,?,?,?,?)", (sender, rc, subject, body, time.time()))
    con.commit(); return len(recips)

# Alan sends Joseph a direct message
send("PAC0014", "PAC0001", "Livery question", "Hey, what red hex do we use?")
check("Joseph has 1 unread", messaging.unread_count(con, "PAC0001") == 1, messaging.unread_count(con, "PAC0001"))
check("Alan has 0 unread", messaging.unread_count(con, "PAC0014") == 0)

# Joseph (staff) broadcasts to everyone -> fan-out to the other 2 pilots
n = send("PAC0001", "ALL", "Welcome", "Glad to have you all.")
check("broadcast fanned out to 2 pilots", n == 2, n)
check("Alan now has 1 unread (the broadcast)", messaging.unread_count(con, "PAC0014") == 1, messaging.unread_count(con, "PAC0014"))

# inbox / sent filters
inbox_joseph = con.execute("SELECT * FROM messages WHERE recipient='PAC0001' AND del_r=0").fetchall()
sent_joseph = con.execute("SELECT * FROM messages WHERE sender='PAC0001' AND del_s=0").fetchall()
check("Joseph inbox has 1 (Alan's note)", len(inbox_joseph) == 1, len(inbox_joseph))
check("Joseph sent has 2 (the broadcast copies)", len(sent_joseph) == 2, len(sent_joseph))

# Joseph reads Alan's note
mid = inbox_joseph[0]["id"]
con.execute("UPDATE messages SET read_at=? WHERE id=?", (time.time(), mid)); con.commit()
check("after reading, Joseph has 0 unread", messaging.unread_count(con, "PAC0001") == 0, messaging.unread_count(con, "PAC0001"))

# per-side delete: Joseph deletes his copy (recipient side); Alan's Sent copy is untouched
con.execute("UPDATE messages SET del_r=1 WHERE id=?", (mid,)); con.commit()
check("message gone from Joseph's inbox", len(con.execute("SELECT 1 FROM messages WHERE recipient='PAC0001' AND del_r=0").fetchall()) == 0)
check("still in Alan's sent", len(con.execute("SELECT 1 FROM messages WHERE sender='PAC0014' AND del_s=0").fetchall()) == 1)

# unread filter shows only unread incoming
alan_unread = con.execute("SELECT * FROM messages WHERE recipient='PAC0014' AND del_r=0 AND read_at IS NULL").fetchall()
check("Alan unread box shows the broadcast", len(alan_unread) == 1, len(alan_unread))

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
