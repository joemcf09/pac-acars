"""The board's "Start from your station" box counts flights you can fly right now, and says so, so it never reads
"0 flights from KPHX" above a list of flights from KPHX. Run from the PAC folder: python tests/test_board_ready_wording.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app_bundle  # noqa: E402

failures = []
def check(name, cond):
    print(("  ok  " if cond else "  FAIL ") + name)
    if not cond: failures.append(name)

js = app_bundle.plain_source()
fn = js.split("function renderMissionChoiceBar()")[1].split("\nfunction ")[0]
check("the count says the flights are ready to fly", "ready to fly from" in fn)
check("an empty count says nothing is ready right now", "No flights ready to fly from" in fn)
check("it says how many more from here need an aircraft or a rating", "an aircraft moved here or a rating first" in fn)
check("with nothing ready, the button shows the flights from here instead of an empty list", "S.fromHere = true" in fn)
check("the old wording is gone", "to review from" not in fn)

print("\nBOARD READY WORDING TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
