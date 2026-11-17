"""Crew mail: simple in-site messages between pilots, plus staff notices.

A message is one row with a sender and a recipient. Read state is per row. Staff can send to everyone, which
fans out one copy per active pilot so read tracking stays simple. Each side can delete its own copy (soft delete),
so a message stays readable for the other party. Nothing here touches secrets, pay or settings.
"""
import time


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, recipient TEXT,
        subject TEXT, body TEXT, time REAL, read_at REAL, del_s INTEGER DEFAULT 0, del_r INTEGER DEFAULT 0)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_msg_recipient ON messages(recipient, del_r, read_at)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_msg_sender ON messages(sender, del_s)")


def unread_count(con, pid):
    try:
        return con.execute("SELECT COUNT(*) FROM messages WHERE recipient=? AND del_r=0 AND read_at IS NULL", (pid,)).fetchone()[0]
    except Exception:
        return 0


def register(app, g):
    from flask import jsonify, request
    db = g["db"]
    va = g["va"]

    with db() as con:          # make sure the table exists before anything reads it (e.g. the nav unread badge)
        migrate(con)
        con.commit()

    def pid():
        return va.current_pilot_id()

    def _is_staff(con, who):
        r = con.execute("SELECT staff FROM pilots WHERE id=?", (who,)).fetchone()
        return bool(r and r[0])

    def _snippet(body):
        s = " ".join((body or "").split())
        return s[:140] + ("…" if len(s) > 140 else "")

    def _row(r, me, full=False):
        return {"id": r["id"], "sender": r["sender"], "sender_name": r["sender_name"] or r["sender"],
                "recipient": r["recipient"], "recipient_name": r["recipient_name"] or r["recipient"],
                "subject": r["subject"] or "(no subject)", "time": r["time"],
                "read": r["read_at"] is not None, "incoming": r["recipient"] == me,
                "body": r["body"] if full else _snippet(r["body"])}

    LIST_SQL = """SELECT m.*, ps.name AS sender_name, pr.name AS recipient_name FROM messages m
        LEFT JOIN pilots ps ON ps.id=m.sender LEFT JOIN pilots pr ON pr.id=m.recipient """

    @app.get("/api/messages")
    def list_messages():
        me = pid()
        box = request.args.get("box", "inbox")
        with db() as con:
            if box == "sent":
                rows = con.execute(LIST_SQL + "WHERE m.sender=? AND m.del_s=0 ORDER BY m.time DESC LIMIT 300", (me,)).fetchall()
            elif box == "unread":
                rows = con.execute(LIST_SQL + "WHERE m.recipient=? AND m.del_r=0 AND m.read_at IS NULL ORDER BY m.time DESC LIMIT 300", (me,)).fetchall()
            else:
                rows = con.execute(LIST_SQL + "WHERE m.recipient=? AND m.del_r=0 ORDER BY m.time DESC LIMIT 300", (me,)).fetchall()
            return jsonify({"messages": [_row(r, me) for r in rows], "unread": unread_count(con, me), "box": box})

    @app.get("/api/messages/recipients")
    def recipients():
        me = pid()
        with db() as con:
            staff = _is_staff(con, me)
            rows = con.execute("SELECT id, name FROM pilots WHERE COALESCE(status,'Active')='Active' AND id!=? ORDER BY name", (me,)).fetchall()
        return jsonify({"pilots": [{"id": r["id"], "name": r["name"] or r["id"]} for r in rows], "can_broadcast": staff})

    @app.get("/api/messages/<int:mid>")
    def get_message(mid):
        me = pid()
        with db() as con:
            r = con.execute(LIST_SQL + "WHERE m.id=?", (mid,)).fetchone()
            if not r or me not in (r["sender"], r["recipient"]):
                return jsonify({"error": "Message not found."}), 404
            if r["recipient"] == me and r["read_at"] is None:
                con.execute("UPDATE messages SET read_at=? WHERE id=?", (time.time(), mid))
                con.commit()
            return jsonify(_row(r, me, full=True))

    @app.post("/api/messages")
    def send_message():
        me = pid()
        b = request.get_json(silent=True)
        b = b if isinstance(b, dict) else {}
        to = str(b.get("to", "")).strip().upper()
        subject = str(b.get("subject", "")).strip()[:140]
        body = str(b.get("body", "")).strip()[:4000]
        if not body:
            return jsonify({"error": "Write a message before sending."}), 400
        if not to:
            return jsonify({"error": "Choose who to send it to."}), 400
        with db() as con:
            if to in ("ALL", "EVERYONE"):
                if not _is_staff(con, me):
                    return jsonify({"error": "Only staff can message the whole crew."}), 403
                recips = [r[0] for r in con.execute("SELECT id FROM pilots WHERE COALESCE(status,'Active')='Active' AND id!=?", (me,)).fetchall()]
            else:
                if not con.execute("SELECT 1 FROM pilots WHERE id=?", (to,)).fetchone():
                    return jsonify({"error": "There's no PAC pilot with that ID."}), 400
                recips = [to]
            now = time.time()
            for rc in recips:
                con.execute("INSERT INTO messages (sender, recipient, subject, body, time) VALUES (?,?,?,?,?)", (me, rc, subject, body, now))
            con.commit()
        return jsonify({"ok": True, "sent": len(recips)})

    @app.post("/api/messages/<int:mid>/delete")
    def delete_message(mid):
        me = pid()
        with db() as con:
            r = con.execute("SELECT sender, recipient FROM messages WHERE id=?", (mid,)).fetchone()
            if not r:
                return jsonify({"error": "Message not found."}), 404
            if r["recipient"] == me:
                con.execute("UPDATE messages SET del_r=1 WHERE id=?", (mid,))
            if r["sender"] == me:
                con.execute("UPDATE messages SET del_s=1 WHERE id=?", (mid,))
            con.commit()
        return jsonify({"ok": True})
