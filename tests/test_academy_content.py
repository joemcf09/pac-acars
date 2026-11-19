"""Academy drafts, publication and resource downloads survive database reopening."""
import io
import sqlite3
import sys
import tempfile
from pathlib import Path

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import academy_content
import payroll


def test_academy_publication_and_upload():
    assert payroll.ROLE_STIPEND["academy_director"] == 3000
    assert payroll.ROLE_STIPEND["academy_director"] > payroll.ROLE_STIPEND["dir_ops"]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "academy.db"
        opened = []

        def db():
            con = sqlite3.connect(path)
            con.row_factory = sqlite3.Row
            academy_content.migrate(con)
            opened.append(con)
            return con

        app = Flask(__name__)
        academy_content.register(app, {"db": db, "DATA": td})
        client = app.test_client()
        draft = client.post("/api/staff/academy", json={"kind": "course", "title": "Cargo basics", "summary": "Start here", "body": "Intro"}).json["item"]
        assert client.get("/api/academy/content").json["items"] == []
        lesson = client.post("/api/staff/academy", json={"kind": "lesson", "course_id": draft["id"], "title": "ULDs", "body": "Load safely", "published": True}).json["item"]
        assert client.get("/api/academy/content").json["items"] == []
        client.post("/api/staff/academy", json={**draft, "published": True})
        assert {x["id"] for x in client.get("/api/academy/content").json["items"]} == {draft["id"], lesson["id"]}
        resource = client.post("/api/staff/academy", json={"kind": "resource", "title": "Checklist", "published": True}).json["item"]
        bad = client.post(f"/api/staff/academy/{resource['id']}/file", data={"file": (io.BytesIO(b"not a pdf"), "fake.pdf", "application/pdf")})
        assert bad.status_code == 400
        good = client.post(f"/api/staff/academy/{resource['id']}/file", data={"file": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "checklist.pdf", "application/pdf")})
        assert good.status_code == 200
        assert client.get(f"/api/academy/files/{resource['id']}").data.startswith(b"%PDF-")
        client.post("/api/staff/academy", json={**resource, "published": False})
        assert client.get(f"/api/academy/files/{resource['id']}").status_code == 404
        assert client.delete(f"/api/staff/academy/{draft['id']}").status_code == 409
        assert client.delete(f"/api/staff/academy/{lesson['id']}").status_code == 200
        for con in opened:
            con.close()
