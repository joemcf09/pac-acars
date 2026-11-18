#!/usr/bin/env python3
"""Seed and verify pilot data for the deploy/rollback test harness.

Subcommands (all take the shared data dir as the first argument):
  seed      <data>            create a cargo reservation, a tracked-flight state
                              file, an uploaded file and a sentinel; write a manifest
  verify    <data>            assert every seeded item is byte-for-byte intact
  add-col   <data> <name>     simulate a newer version's additive migration
  read      <data>            prove the DB still reads (pilots + the booking)
"""
import hashlib
import json
import pathlib
import pickle
import sqlite3
import sys
import time
import types

def _db(data):
    return sqlite3.connect(str(pathlib.Path(data) / "logbook.db"))

def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def seed(data):
    d = pathlib.Path(data)
    (d / "gallery").mkdir(parents=True, exist_ok=True)
    (d / "flights").mkdir(parents=True, exist_ok=True)
    # a cargo reservation (one row per pilot, as the app stores it)
    requested_at = time.time()
    con = _db(data)
    con.execute("CREATE TABLE IF NOT EXISTS bookings (pilot_id TEXT PRIMARY KEY, data TEXT, requested_at REAL)")
    booking = {"flight_number": "PAC9401", "airframe": "N330PA", "origin": "LIMC",
               "destination": "EDDP", "requested_at": requested_at}
    con.execute("INSERT OR REPLACE INTO bookings VALUES (?,?,?)",
                ("PAC0001", json.dumps(booking), requested_at))
    con.commit(); con.close()
    # a tracked-flight state file at the path the app uses, valid and matching the
    # reservation so the app RESTORES it on restart rather than discarding it
    rec = types.SimpleNamespace(booking={"requested_at": requested_at, "flight_number": "PAC9401"})
    (d / "flights" / "PAC0001.pkl").write_bytes(pickle.dumps({"recorder": rec, "source": "MSFS"}))
    # an upload and a sentinel the app never touches
    (d / "gallery" / "keep.txt").write_text("an uploaded file that must survive\n")
    (d / "SENTINEL.txt").write_text("do not lose me\n")
    manifest = {
        "flights/PAC0001.pkl": _sha(d / "flights" / "PAC0001.pkl"),
        "gallery/keep.txt": _sha(d / "gallery" / "keep.txt"),
        "SENTINEL.txt": _sha(d / "SENTINEL.txt"),
        "logbook.db.booking": "PAC9401",
    }
    (d / ".manifest.json").write_text(json.dumps(manifest))
    print("seeded reservation, tracked-flight state, upload and sentinel")

def verify(data):
    d = pathlib.Path(data)
    man = json.loads((d / ".manifest.json").read_text())
    bad = []
    for rel, want in man.items():
        if rel == "logbook.db.booking":
            con = _db(data)
            row = con.execute("SELECT data FROM bookings WHERE pilot_id='PAC0001'").fetchone()
            con.close()
            if not row or json.loads(row[0]).get("flight_number") != want:
                bad.append(f"booking row (flight {want}) missing/changed")
            continue
        p = d / rel
        if not p.exists():
            bad.append(f"{rel} is GONE"); continue
        if _sha(p) != want:
            bad.append(f"{rel} CHANGED")
    if bad:
        print("DATA LOSS: " + "; ".join(bad)); sys.exit(1)
    print("all pilot data intact (reservation, flight-state, upload, sentinel)")

def add_col(data, name):
    con = _db(data)
    cols = [r[1] for r in con.execute("PRAGMA table_info(pilots)")]
    if name not in cols:
        con.execute(f"ALTER TABLE pilots ADD COLUMN {name} TEXT")
        con.commit()
    con.close()
    print(f"added column pilots.{name} (simulating a newer migration)")

def read(data):
    con = _db(data)
    n = con.execute("SELECT COUNT(*) FROM pilots").fetchone()[0]
    row = con.execute("SELECT data FROM bookings WHERE pilot_id='PAC0001'").fetchone()
    con.close()
    assert row, "booking unreadable"
    print(f"DB reads OK: {n} pilots, booking {json.loads(row[0])['flight_number']} present")

if __name__ == "__main__":
    cmd, data = sys.argv[1], sys.argv[2]
    {"seed": lambda: seed(data),
     "verify": lambda: verify(data),
     "add-col": lambda: add_col(data, sys.argv[3]),
     "read": lambda: read(data)}[cmd]()
