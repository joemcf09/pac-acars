"""Editable PAC Academy courses, lessons and resources.

The original 737 cockpit tutorial stays in its static page. New material lives
in the existing site database so a deploy does not overwrite staff edits.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from flask import jsonify, request, send_file

MIME = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_FILE = 12 * 1024 * 1024


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS academy_content (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
        course_id INTEGER, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '', published INTEGER NOT NULL DEFAULT 0,
        position INTEGER NOT NULL DEFAULT 0, filename TEXT, stored_name TEXT,
        mime TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        FOREIGN KEY (course_id) REFERENCES academy_content(id))""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_academy_list ON academy_content(published, kind, course_id, position)")


def _row(r):
    d = dict(r)
    d["published"] = bool(d["published"])
    d["file_url"] = f"/api/academy/files/{d['id']}" if d["stored_name"] else None
    d.pop("stored_name")
    return d


def _valid_text(b):
    kind = b.get("kind")
    title = str(b.get("title") or "").strip()
    summary = str(b.get("summary") or "").strip()
    body = str(b.get("body") or "").strip()
    if kind not in ("course", "lesson", "resource"):
        raise ValueError("Choose a course, lesson or resource.")
    if not title or len(title) > 120 or len(summary) > 500 or len(body) > 20000:
        raise ValueError("Title is required (120 characters max); summary and body must fit their limits.")
    try:
        position = int(b.get("position") or 0)
    except (TypeError, ValueError):
        raise ValueError("Order must be a whole number.") from None
    if not 0 <= position <= 9999:
        raise ValueError("Order must be between 0 and 9999.")
    return kind, title, summary, body, position


def register(app, g):
    def file_dir():
        p = Path(g["DATA"]) / "academy-files"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @app.get("/api/academy/content")
    def academy_public():
        with g["db"]() as con:
            rows = con.execute("""SELECT * FROM academy_content WHERE published=1
                AND (kind!='lesson' OR course_id IN
                    (SELECT id FROM academy_content WHERE kind='course' AND published=1))
                ORDER BY position, id""").fetchall()
            return jsonify({"items": [_row(r) for r in rows]})

    @app.get("/api/academy/files/<int:item_id>")
    def academy_public_file(item_id):
        with g["db"]() as con:
            r = con.execute("""SELECT a.* FROM academy_content a
                LEFT JOIN academy_content c ON c.id=a.course_id
                WHERE a.id=? AND a.published=1 AND
                (a.kind!='lesson' OR c.published=1)""", (item_id,)).fetchone()
        if not r or not r["stored_name"]:
            return jsonify({"error": "Resource not found."}), 404
        p = file_dir() / r["stored_name"]
        if not p.is_file():
            return jsonify({"error": "Resource file is missing."}), 404
        return send_file(p, mimetype=r["mime"], as_attachment=True, download_name=r["filename"], max_age=0)

    @app.get("/api/staff/academy")
    def academy_staff_list():
        with g["db"]() as con:
            return jsonify({"items": [_row(r) for r in con.execute("SELECT * FROM academy_content ORDER BY position, id")]})

    @app.post("/api/staff/academy")
    def academy_save():
        b = request.get_json(silent=True) or {}
        try:
            kind, title, summary, body, position = _valid_text(b)
            item_id = int(b.get("id") or 0)
            parent_id = int(b.get("course_id") or 0)
            with g["db"]() as con:
                old = con.execute("SELECT * FROM academy_content WHERE id=?", (item_id,)).fetchone() if item_id else None
                if item_id and not old:
                    return jsonify({"error": "Item not found."}), 404
                if kind == "lesson":
                    parent = con.execute("SELECT id FROM academy_content WHERE id=? AND kind='course'", (parent_id,)).fetchone()
                    if not parent or parent_id == item_id:
                        raise ValueError("Choose an existing course for this lesson.")
                else:
                    parent_id = None
                if old and old["kind"] == "course" and kind != "course":
                    if con.execute("SELECT 1 FROM academy_content WHERE course_id=? LIMIT 1", (item_id,)).fetchone():
                        raise ValueError("Move or remove this course's lessons first.")
                now = time.time()
                if old:
                    con.execute("""UPDATE academy_content SET kind=?,course_id=?,title=?,summary=?,body=?,
                        published=?,position=?,updated_at=? WHERE id=?""",
                        (kind, parent_id, title, summary, body, int(bool(b.get("published"))), position, now, item_id))
                else:
                    cur = con.execute("""INSERT INTO academy_content
                        (kind,course_id,title,summary,body,published,position,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (kind, parent_id, title, summary, body, int(bool(b.get("published"))), position, now, now))
                    item_id = cur.lastrowid
                return jsonify({"item": _row(con.execute("SELECT * FROM academy_content WHERE id=?", (item_id,)).fetchone())})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/staff/academy/<int:item_id>/file")
    def academy_upload(item_id):
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "Choose a file."}), 400
        with g["db"]() as con:
            r = con.execute("SELECT * FROM academy_content WHERE id=?", (item_id,)).fetchone()
            if not r or r["kind"] != "resource":
                return jsonify({"error": "Create a resource first."}), 404
            name = Path(f.filename or "").name[:150]
            suffix = Path(name).suffix.lower()
            mime = f.mimetype
            if not name or mime not in MIME or suffix != MIME[mime]:
                return jsonify({"error": "Use a PDF, PNG, JPEG or WebP file."}), 400
            data = f.stream.read(MAX_FILE + 1)
            if not data or len(data) > MAX_FILE:
                return jsonify({"error": "File must be between 1 byte and 12 MB."}), 400
            if not (data.startswith(b"%PDF-") if mime == "application/pdf" else
                    data.startswith(b"\x89PNG\r\n\x1a\n") if mime == "image/png" else
                    data.startswith(b"\xff\xd8\xff") if mime == "image/jpeg" else
                    data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
                return jsonify({"error": "File contents do not match its type."}), 400
            stored = uuid.uuid4().hex + suffix
            (file_dir() / stored).write_bytes(data)
            con.execute("UPDATE academy_content SET filename=?,stored_name=?,mime=?,updated_at=? WHERE id=?",
                        (name, stored, mime, time.time(), item_id))
            if r["stored_name"]:
                (file_dir() / r["stored_name"]).unlink(missing_ok=True)
            return jsonify({"item": _row(con.execute("SELECT * FROM academy_content WHERE id=?", (item_id,)).fetchone())})

    @app.delete("/api/staff/academy/<int:item_id>")
    def academy_delete(item_id):
        with g["db"]() as con:
            r = con.execute("SELECT * FROM academy_content WHERE id=?", (item_id,)).fetchone()
            if not r:
                return jsonify({"error": "Item not found."}), 404
            if r["kind"] == "course" and con.execute("SELECT 1 FROM academy_content WHERE course_id=? LIMIT 1", (item_id,)).fetchone():
                return jsonify({"error": "Remove this course's lessons first."}), 409
            con.execute("DELETE FROM academy_content WHERE id=?", (item_id,))
            if r["stored_name"]:
                (file_dir() / r["stored_name"]).unlink(missing_ok=True)
            return jsonify({"deleted": item_id})
