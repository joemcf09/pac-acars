"""The job board draws on a large, varied pool of cargo stories (va.JOB_TEMPLATES).
Run from the PAC folder: python tests/test_job_variety.py"""
import collections, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import va  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

T = va.JOB_TEMPLATES
kinds = [t[0] for t in T]
cats = collections.Counter(t[1] for t in T)
check("the job board has a large pool of stories", len(T) >= 75, len(T))
check("every story is distinct", len(kinds) == len(set(kinds)) and len({t[4] for t in T}) == len(T))
check("every board category has plenty of choice", all(cats[c] >= 8 for c in
      ("Express", "Premium", "Humanitarian", "Heavy lift", "Medical", "Special cargo", "Sports & events")), cats)
check("titles name the destination", all("{city}" in t[4] and t[4].format(city="X") and t[5].format(city="X") for t in T))
check("priorities are ones the board knows", {t[2] for t in T} <= {"Standard", "High", "Critical"})
check("load fractions are sensible", all(0 < t[6][0] <= t[6][1] <= 1 for t in T))
check("no single kind of work dominates", max(cats.values()) <= len(T) * 0.3, cats)

print("\nJOB VARIETY TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
