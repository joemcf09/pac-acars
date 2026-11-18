"""A retry after interrupted PIREP finalization must not duplicate records or effects."""
import json
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import analysis  # noqa: E402
import app as A  # noqa: E402
import va  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402


def main():
    failures = []

    def check(name, condition, detail=""):
        print(f"  {'ok ' if condition else 'FAIL '}{name}{'' if condition else ' · ' + str(detail)}")
        if not condition:
            failures.append(name)

    original_db_path, original_data, original_db = A.DB_PATH, A.DATA, A.db
    original_context_db = va.C["db"]
    original_pilot_id, original_after_file = va.current_pilot_id, va.after_file
    with tempfile.TemporaryDirectory(prefix="pac-pirep-retry-") as temp:
        temp_path = Path(temp)
        A.DB_PATH = temp_path / "logbook.db"
        A.DATA = temp_path / "data"
        A.DATA.mkdir()
        disk_db = original_db()
        memory_uri = f"file:pac-pirep-retry-{id(disk_db)}?mode=memory&cache=shared"
        memory_anchor = sqlite3.connect(memory_uri, uri=True)
        memory_anchor.row_factory = sqlite3.Row
        disk_db.backup(memory_anchor)
        disk_db.close()

        def test_db():
            con = sqlite3.connect(memory_uri, uri=True)
            con.row_factory = sqlite3.Row
            return con

        A.db = test_db
        va.C["db"] = test_db
        va.current_pilot_id = lambda: "PAC0001"
        try:
            with closing(A.db()) as con, con:
                con.execute("INSERT INTO airframes (reg, type, location, status) VALUES ('NTESTPC', 'B733F', 'KCVG', 'Available')")
            mission = A.ROUTES["PAC1022"]
            booking = {"mission": mission, "aircraft": "B733F", "ofp": None,
                       "flight_number": "PAC1022", "airframe": "NTESTPC", "requested_at": time.time()}
            recorder = FlightRecorder(booking)
            runways = analysis.runways(ROOT / "data")
            for sample in fly("KCVG", runways["KCVG"][0][0], "KCLT", runways["KCLT"][0][0]):
                recorder.update(sample)
            # Exercise the 1.2 app record handoff before the website files the PIREP.
            recorder.eng_starts = [{"n": 2, "seq": 1}, {"n": 1, "seq": 2}]
            recorder.single_eng_taxi = True
            recorder.dep_config = {"beacon": True, "nav": True, "landing": None}
            recorder.arr_config = {"beacon": False, "nav": True, "landing": False}
            recorder = FlightRecorder.from_export(booking, recorder.export())
            A.save_booking(booking, "PAC0001")
            A.SESSIONS["PAC0001"] = dict(A.SESSION_BLANK, recorder=recorder)

            def interrupt_before_effects(*args):
                raise RuntimeError("simulated interruption before finalization")

            va.after_file = interrupt_before_effects
            try:
                with A.app.test_request_context("/api/pirep", method="POST", json={}):
                    A.file_pirep()
            except RuntimeError as exc:
                check("the first filing is interrupted before side effects", "before finalization" in str(exc), exc)
            else:
                check("the first filing is interrupted before side effects", False, "no interruption occurred")

            def interrupt_after_effects(*args):
                original_after_file(*args)
                raise RuntimeError("simulated interruption before booking cleanup")

            va.after_file = interrupt_after_effects
            try:
                with A.app.test_request_context("/api/pirep", method="POST", json={}):
                    A.file_pirep()
            except RuntimeError as exc:
                check("retry is interrupted after side effects", "before booking cleanup" in str(exc), exc)
            else:
                check("retry is interrupted after side effects", False, "no interruption occurred")

            va.after_file = original_after_file
            with A.app.test_request_context("/api/pirep", method="POST", json={}):
                response = A.file_pirep()
            check("retry completes successfully", response.status_code == 200, response.status_code)

            with closing(A.db()) as con, con:
                report_count = con.execute(
                    "SELECT COUNT(*) FROM pireps WHERE pilot_id='PAC0001' AND booking_key=?",
                    (str(booking["requested_at"]),)).fetchone()[0]
                effect_count = con.execute(
                    "SELECT COUNT(*) FROM pirep_effects WHERE pirep_id IN "
                    "(SELECT id FROM pireps WHERE pilot_id='PAC0001' AND booking_key=?)",
                    (str(booking["requested_at"]),)).fetchone()[0]
                pay_count = con.execute(
                    "SELECT COUNT(*) FROM wallet WHERE kind='flight_pay' AND pirep_id IN "
                    "(SELECT id FROM pireps WHERE pilot_id='PAC0001' AND booking_key=?)",
                    (str(booking["requested_at"]),)).fetchone()[0]
                report = con.execute(
                    "SELECT flight_min, detail FROM pireps WHERE pilot_id='PAC0001' AND booking_key=?",
                    (str(booking["requested_at"]),)).fetchone()
                airframe = con.execute("SELECT hours, cycles, location FROM airframes WHERE reg='NTESTPC'").fetchone()
            saved_config = json.loads(report["detail"])["flight_configuration"]
            check("engine starts survive the handoff and filing",
                  [e["n"] for e in saved_config["eng_starts"]] == [2, 1])
            check("single-engine taxi survives the handoff and filing",
                  saved_config["single_eng_taxi"] is True)
            check("departure and arrival lights survive the handoff and filing",
                  saved_config["dep_config"]["landing"] is None
                  and saved_config["arr_config"]["landing"] is False)
            check("one PIREP exists for the booking", report_count == 1, report_count)
            check("one finalization marker exists", effect_count == 1, effect_count)
            check("flight pay was recorded once", pay_count == 1, pay_count)
            check("airframe hours and cycles were applied once",
                  airframe["cycles"] == 1 and abs(airframe["hours"] - report["flight_min"] / 60) < 0.001,
                  dict(airframe))
            check("airframe moved to the arrival station", airframe["location"] == "KCLT", airframe["location"])
            check("the booking is cleared after retry", A.load_booking("PAC0001") is None)
        finally:
            memory_anchor.close()
            va.current_pilot_id = original_pilot_id
            va.after_file = original_after_file
            A.db = original_db
            va.C["db"] = original_context_db
            A.DB_PATH, A.DATA = original_db_path, original_data
            A.SESSIONS.pop("PAC0001", None)

    print("\nPIREP RETRY TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
