"""Staying active: the date each pilot's next flight is due, leave of absence, and reminders.

A pilot is due to fly within `activity_days` (45 by default) of their last flight, or of joining, or of the end of
their last leave of absence, whichever is latest. Pilots can take a leave of absence themselves (up to
`leave_max_days` at a time): the clock pauses and the roster shows them as On leave. Filing a flight ends the
leave early. The Discord bot sends a reminder `activity_remind_days` before the date.

The whole rule is off until staff switch `activity_rule_on` on (Staff › Activity): while it's off, pilots see no
due date, no leave form and no reminders. Nothing here removes anyone. Marking overdue pilots Inactive happens only if staff switch
`activity_auto_inactive` on, and Inactive pilots become Active again as soon as they file a flight.
"""
from __future__ import annotations

import json
import time

from flask import Blueprint, jsonify, request

bp = Blueprint("activity", __name__)
C = {}
DAY = 86400
LEAVE_YEAR_CAP = 120          # days of leave in any 365 days


def init(ctx):
    C.update(ctx)


def _st():
    return C["settings"]()


def policy(st=None):
    st = st or _st()

    def num(k, d, lo, hi):
        try:
            return max(lo, min(hi, int(float(st.get(k) or d))))
        except (TypeError, ValueError):
            return d
    return {"days": num("activity_days", 45, 14, 180), "remind_days": num("activity_remind_days", 7, 1, 30),
            "leave_max_days": num("leave_max_days", 60, 7, 120), "auto_inactive": st.get("activity_auto_inactive") is True,
            "enabled": st.get("activity_rule_on") is True}


def _prefs(row):
    try:
        p = json.loads(row["prefs"] or "{}")
        return p if isinstance(p, dict) else {}
    except (ValueError, TypeError, KeyError, IndexError):
        return {}


def _save_prefs(con, pid, prefs):
    con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(prefs), pid))


def _last_flight(con, pid):
    r = con.execute("""SELECT MAX(filed_at) FROM pireps WHERE pilot_id=? AND COALESCE(demo,0)=0
                       AND COALESCE(review_status,'') != 'Rejected'""", (pid,)).fetchone()
    return r[0] if r and r[0] else None


def state(pid, con=None, now=None, st=None):
    """The pilot's activity: when the next flight is due and whether they're on leave. Tidies up a leave that has ended."""
    now = now or time.time()
    pol = policy(st)
    own = con is None
    con = con or C["db"]()
    try:
        row = con.execute("SELECT id, name, status, joined, prefs, discord_id FROM pilots WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        prefs = _prefs(row)
        last = _last_flight(con, pid)
        leave = prefs.get("leave")
        status = row["status"] or "Active"
        # a leave ends when its date passes or when the pilot files a flight after it started
        if leave and (now >= leave["until"] or (last and last > leave["from"])):
            end = min(now, leave["until"]) if not (last and last > leave["from"]) else last
            prefs.setdefault("leave_history", []).append([leave["from"], end, leave.get("reason", "")])
            prefs["leave_history"] = prefs["leave_history"][-12:]
            prefs.pop("leave", None)
            leave = None
            _save_prefs(con, pid, prefs)
            if status == "On leave":
                con.execute("UPDATE pilots SET status='Active' WHERE id=?", (pid,))
                status = "Active"
        if status == "Inactive" and last and pol["auto_inactive"] and last > (prefs.get("inactive_at") or 0):
            con.execute("UPDATE pilots SET status='Active' WHERE id=?", (pid,))     # back flying: active again
            status = "Active"
        hist = prefs.get("leave_history") or []
        last_leave_end = max((h[1] for h in hist), default=0)
        base = max(last or 0, row["joined"] or 0, last_leave_end)
        due = (leave["until"] if leave else base) + pol["days"] * DAY
        days_left = int((due - now) // DAY)
        used = sum(max(0, min(h[1], now) - max(h[0], now - 365 * DAY)) for h in hist if h[1] > now - 365 * DAY) / DAY
        if leave:
            used += (min(leave["until"], now + 365 * DAY) - max(leave["from"], now - 365 * DAY)) / DAY
        kind = "leave" if leave else "overdue" if days_left < 0 else "soon" if days_left <= pol["remind_days"] else "ok"
        if own:
            con.commit()
        return {"pilot_id": pid, "name": row["name"], "status": status, "state": kind, "due": due, "days_left": days_left,
                "last_flight": last, "policy_days": pol["days"], "remind_days": pol["remind_days"], "enabled": pol["enabled"],
                "leave": leave, "leave_max_days": pol["leave_max_days"],
                "leave_days_left_year": max(0, int(LEAVE_YEAR_CAP - used)), "auto_inactive": pol["auto_inactive"],
                "discord_id": row["discord_id"], "reminded": prefs.get("activity_reminded")}
    finally:
        if own:
            con.close()


def public(s):
    return {k: v for k, v in (s or {}).items() if k not in ("discord_id", "reminded")}


@bp.get("/api/pilot/activity")
def my_activity():
    return jsonify(public(state(C["va"].current_pilot_id())))


@bp.post("/api/pilot/leave")
def start_leave():
    pid = C["va"].current_pilot_id()
    b = request.json or {}
    pol = policy()
    try:
        days = int(b.get("days") or 0)
    except (TypeError, ValueError):
        days = 0
    if not pol["enabled"]:
        return jsonify({"error": "PAC has no activity requirement right now, so there's no leave to take. Fly whenever you like."}), 400
    if days < 3 or days > pol["leave_max_days"]:
        return jsonify({"error": f"Choose between 3 and {pol['leave_max_days']} days."}), 400
    reason = C["clean_text"](str(b.get("reason") or ""))[:200] if C.get("clean_text") else str(b.get("reason") or "")[:200]
    now = time.time()
    with C["db"]() as con:
        s = state(pid, con, now)
        if not s:
            return jsonify({"error": "Pilot not found."}), 404
        if s["leave"]:
            return jsonify({"error": "You're already on leave. End it first to change the dates."}), 400
        if s["status"] in ("Suspended", "Removed"):
            return jsonify({"error": "This account isn't active."}), 403
        if days > s["leave_days_left_year"]:
            return jsonify({"error": f"You have {s['leave_days_left_year']} days of leave left in this 12-month period (up to {LEAVE_YEAR_CAP} a year)."}), 400
        row = con.execute("SELECT prefs, status FROM pilots WHERE id=?", (pid,)).fetchone()
        prefs = _prefs(row)
        prefs["leave"] = {"from": now, "until": now + days * DAY, "reason": reason, "days": days}
        prefs.pop("activity_reminded", None)
        _save_prefs(con, pid, prefs)
        if (row["status"] or "Active") in ("Active", "Inactive"):
            con.execute("UPDATE pilots SET status='On leave' WHERE id=?", (pid,))
        out = state(pid, con, now)
    return jsonify(public(out))


@bp.delete("/api/pilot/leave")
def end_leave():
    pid = C["va"].current_pilot_id()
    now = time.time()
    with C["db"]() as con:
        row = con.execute("SELECT prefs, status FROM pilots WHERE id=?", (pid,)).fetchone()
        prefs = _prefs(row) if row else {}
        lv = prefs.pop("leave", None)
        if lv:
            prefs.setdefault("leave_history", []).append([lv["from"], now, lv.get("reason", "")])
            prefs["leave_history"] = prefs["leave_history"][-12:]
            _save_prefs(con, pid, prefs)
            if row["status"] == "On leave":
                con.execute("UPDATE pilots SET status='Active' WHERE id=?", (pid,))
        out = state(pid, con, now)
    return jsonify(public(out))


def sweep(now=None):
    """Every pilot's activity, worst first. With auto-inactive on, overdue pilots are marked Inactive."""
    now = now or time.time()
    pol = policy()
    out = []
    with C["db"]() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM pilots WHERE COALESCE(status,'Active') NOT IN ('Removed','Suspended')")]
        for pid in ids:
            s = state(pid, con, now)
            if not s:
                continue
            if pol["enabled"] and pol["auto_inactive"] and s["state"] == "overdue" and s["status"] == "Active":
                con.execute("UPDATE pilots SET status='Inactive' WHERE id=?", (pid,))
                row = con.execute("SELECT prefs FROM pilots WHERE id=?", (pid,)).fetchone()
                prefs = _prefs(row)
                prefs["inactive_at"] = now
                _save_prefs(con, pid, prefs)
                s["status"] = "Inactive"
            out.append(s)
    order = {"overdue": 0, "soon": 1, "leave": 2, "ok": 3}
    out.sort(key=lambda s: (order[s["state"]], s["days_left"]))
    return out


@bp.get("/api/staff/activity")
def staff_activity():
    rows = [public(s) for s in sweep()]
    return jsonify({"policy": policy(), "pilots": rows,
                    "counts": {k: sum(1 for s in rows if s["state"] == k) for k in ("overdue", "soon", "leave", "ok")}})


def reminders_due(now=None):
    """Linked, active pilots inside the reminder window who haven't been reminded for this due date."""
    if not policy()["enabled"]:
        return []
    out = []
    for s in sweep(now):
        if s["discord_id"] and s["state"] == "soon" and s["status"] == "Active" and s["days_left"] >= 0 \
                and s.get("reminded") != int(s["due"] // DAY):
            out.append({"pilot_id": s["pilot_id"], "name": s["name"], "discord_id": s["discord_id"], "due": s["due"],
                        "due_day": int(s["due"] // DAY), "days_left": s["days_left"]})
    return out


def mark_reminded(items):
    with C["db"]() as con:
        for it in items or []:
            row = con.execute("SELECT prefs FROM pilots WHERE id=?", (str(it.get("pilot_id")),)).fetchone()
            if not row:
                continue
            prefs = _prefs(row)
            prefs["activity_reminded"] = int(it.get("due_day") or 0)
            _save_prefs(con, str(it["pilot_id"]), prefs)
