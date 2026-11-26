"""Short-haul heavy jobs draw on a varied, seasonal pool of stories (short_heavy_jobs.py).
Run from the PAC folder: python tests/test_short_hop_stories.py"""
import collections, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import short_heavy_jobs as S  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

keys = [s["key"] for s in S.SCENARIOS]
check("there are far more than the original four stories", len(S.SCENARIOS) >= 25, len(S.SCENARIOS))
check("every story has a unique key", len(keys) == len(set(keys)))
check("every story fills in both cities", all("{dc}" in s["story"] and s["story"].format(oc="A", dc="B") for s in S.SCENARIOS))
check("every story has handling notes", all(s.get("notes") for s in S.SCENARIOS))

def keys_for(day, dest):
    return {s["key"] for s in S._stories(day, dest, {})}

check("Christmas trees in December", "xmas_trees" in keys_for("2026-12-05", "KBOS"))
check("but not in July", "xmas_trees" not in keys_for("2027-07-05", "KBOS"))
check("Christmas markets only in Europe", "xmas_market" in keys_for("2026-12-05", "EDDM") and "xmas_market" not in keys_for("2026-12-05", "KBOS"))
check("salmon season in Alaska in summer", "salmon_season" in keys_for("2027-07-05", "PANC") and "salmon_season" not in keys_for("2027-07-05", "EDDM"))
check("Lunar New Year blossoms in Asia", "lunar_flowers" in keys_for("2027-02-01", "VHHH") and "lunar_flowers" not in keys_for("2027-02-01", "KJFK"))
check("year-round stories appear everywhere", {"sort_overflow", "banknotes", "concert_rig"} <= keys_for("2027-05-05", "LIMC"))

for day, dest in (("2026-12-03", "KBOS"), ("2027-05-10", "EDDF"), ("2027-02-01", "VHHH")):
    rng, counts, got = random.Random(day), {}, []
    for _ in range(S.DAILY_LIMIT):
        sc = S._pick(rng, day, dest, counts)
        counts[sc["key"]] = counts.get(sc["key"], 0) + 1
        got.append(sc["key"])
    c = collections.Counter(got)
    check(f"a day's board to {dest} mixes many stories", len(c) >= 12, c)
    check(f"no story floods the board to {dest}", max(c.values()) <= S.MAX_PER_STORY, c.most_common(3))
    check(f"the original four are no longer most of it ({dest})", sum(c[k] for k in ("factory", "maintenance", "power", "machinery")) <= 12, c)

check("same day, same picks (the board doesn't reshuffle on refresh)",
      [S._pick(random.Random("d"), "2026-12-03", "KBOS", {})["key"] for _ in range(3)] ==
      [S._pick(random.Random("d"), "2026-12-03", "KBOS", {})["key"] for _ in range(3)])

print("\nSHORT HOP STORY TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
