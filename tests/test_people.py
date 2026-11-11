"""People on board: grooms, attendants, couriers and AOG engineers on the load sheet, and their reaction in the debrief.
Run from the PAC folder: python tests/test_people.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import people  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

horses = people.aboard({"cargo": "Thoroughbred racehorses in jet stalls, with grooms and a vet"}, {"AVI"})
check("racehorses fly with grooms and a vet", people.summary(horses) == "2 grooms and a veterinarian", people.summary(horses))
check("other animals get an attendant", people.summary(people.aboard({"cargo": "Zoo penguins"}, {"AVI"})) == "an animal attendant")
check("AOG recoveries carry engineers", people.total(people.aboard({"urgent_kind": "AOG", "id": "PAC8801"})) == 2)
check("valuables get a courier", people.aboard({"cargo": "Banknotes"}, {"VAL"})[0]["role"] == "Security courier")
check("ordinary freight carries nobody extra", people.aboard({"cargo": "Machinery"}, {"GEN"}) == [] and people.debrief_note([], -900) is None)
check("a hard landing shakes them", people.debrief_note(horses, -700, 2.2)["tone"] == "bad")
check("a firm landing or a bounce is noticed", people.debrief_note(horses, -300, 1.4, 1)["tone"] == "warn")
check("a smooth landing earns thanks", people.debrief_note(horses, -150, 1.2)["tone"] == "good")
check("one passenger reads as one", "courier on board was" in people.debrief_note(people.aboard({}, {"VAL"}), -700)["text"])
check("the load sheet shows them", "SUPY" in (ROOT / "static" / "dispatch.html").read_text(encoding="utf-8"))
print("\nPEOPLE TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
