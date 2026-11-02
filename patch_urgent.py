"""Throttles failed urgent-mission generation attempts.

THE BUG, confirmed by thread dumps taken while the site was stalled:

    Thread 228504 (active+gil): "waitress-3"
        _make_urgent (va.py:1489)
        urgent_missions (va.py:1514)
        urgent_list (app.py:2578)

Twenty dumps out of twenty, the same thread sitting on the same list
comprehension while every other thread idled. _make_urgent scans every station
and computes a great-circle distance for each, once per available airframe --
and it does that inside `with C["db"]() as con:`, so it holds the SQLite write
lock for the whole scan. Every other writer waits busy_timeout (30s) and fails
on its first write statement. That is why mission_board, jobs_today and the
bootstrap were all failing: they were casualties, not causes.

What makes it permanent is the gate:

    last = SELECT MAX(created) FROM urgent
    if len(rows) < URGENT_MAX and (not rows or now - last >= URGENT_EVERY_S):

`last` only advances when a mission is actually INSERTED. If _make_urgent
rejects every airframe and returns None, nothing is inserted, `last` does not
move, and the gate is still open on the very next request. So a failed attempt
costs the full scan and buys no delay, and every single page load repeats it.

THE FIX: remember when generation was last ATTEMPTED, not just when it last
succeeded, and refuse to retry for URGENT_RETRY_S. A successful attempt is
unaffected. A failing one now costs the scan once every few minutes instead of
once per request, which takes the write lock out of the request path.

This is deliberately the smallest change that stops the storm. It does not
restructure _make_urgent -- moving the scan out of the transaction is the proper
follow-up, once the site is stable and we are not changing two things at once.

Safety: verifies every expected line before writing, backs the file up, byte
compiles the result, and restores the backup if compilation fails. It also
checks that the known-bad `_GENERATE` lock is not present.

    sudo -u pac /home/pac/pac-acars/.venv/bin/python /home/pac/pac-acars/patch_urgent.py
"""
import py_compile
import re
import shutil
import sys
import time
from pathlib import Path

#   An alternate path may be passed as an argument, which is how this script is
#   tested against a copy before being run on the server.
VA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/pac/pac-acars/va.py")

GATE_RE = re.compile(
    r"^(\s*)if len\(rows\) < URGENT_MAX and \(not rows or now - last >= URGENT_EVERY_S\):\s*$"
)
ANCHOR_RE = re.compile(r"^URGENT_EVERY_S\s*=.*$")

NEW_CONSTANTS = [
    "URGENT_RETRY_S = 5 * 60         # a FAILED generation attempt is not retried for this long.\n",
    "                                # _make_urgent scans every station per airframe while holding\n",
    "                                # the write lock, and returns None if nothing qualifies. Without\n",
    "                                # this, every page load repeats that scan and starves all writers.\n",
    "_URGENT_TRY = [0.0]             # when generation was last attempted, successful or not.\n",
]


def fail(msg):
    print(f"\nABORTED: {msg}")
    print("Nothing was changed.")
    sys.exit(1)


def main():
    if not VA.exists():
        fail(f"{VA} does not exist")

    src = VA.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)

    print(f"file: {VA}  ({len(src):,} bytes, {len(lines):,} lines)")

    # --- sanity: the bad RLock from the earlier failed fix must not be here ---
    if "_GENERATE" in src:
        fail("this va.py contains `_GENERATE` -- the lock that caused the overnight "
             "502. The server should be running the reverted version. Do not patch "
             "this file; restore the correct va.py first.")
    print("check: no `_GENERATE` lock present -- good, this is the reverted version")

    # --- already patched? ---
    if "URGENT_RETRY_S" in src:
        print("\nThis file already has the throttle. Nothing to do.")
        return

    # --- locate the throttle constant anchor ---
    anchor = [i for i, ln in enumerate(lines) if ANCHOR_RE.match(ln)]
    if len(anchor) != 1:
        fail(f"expected exactly one `URGENT_EVERY_S =` line, found {len(anchor)}")
    anchor_i = anchor[0]
    print(f"check: URGENT_EVERY_S at line {anchor_i + 1}")

    # --- locate the gate ---
    gates = [i for i, ln in enumerate(lines) if GATE_RE.match(ln)]
    if len(gates) != 1:
        fail(f"expected exactly one generation gate line, found {len(gates)}. "
             "The file differs from what I analysed; send me the current va.py.")
    gate_i = gates[0]
    indent = GATE_RE.match(lines[gate_i]).group(1)
    print(f"check: generation gate at line {gate_i + 1} (indent {len(indent)} spaces)")

    # The line after the gate must be the `for _ in range(...)` loop.
    nxt = lines[gate_i + 1] if gate_i + 1 < len(lines) else ""
    if "for _ in range(" not in nxt:
        fail("the line after the gate is not the expected `for _ in range(...)` loop")
    print("check: generation loop follows the gate as expected")

    # --- build the replacement gate, preserving indentation ---
    new_gate = (
        f"{indent}if (len(rows) < URGENT_MAX and (not rows or now - last >= URGENT_EVERY_S)\n"
        f"{indent}        and now - _URGENT_TRY[0] >= URGENT_RETRY_S):\n"
        f"{indent}    _URGENT_TRY[0] = now        # count the attempt even if it finds nothing\n"
    )

    out = lines[:]
    out[gate_i:gate_i + 1] = [new_gate]
    out[anchor_i + 1:anchor_i + 1] = NEW_CONSTANTS

    # --- back up, write, verify ---
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = VA.with_suffix(f".py.before-urgent-throttle-{stamp}")
    shutil.copy2(VA, backup)
    print(f"\nbackup: {backup}")

    VA.write_text("".join(out), encoding="utf-8")

    try:
        py_compile.compile(str(VA), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(backup, VA)
        fail(f"the patched file does not compile, so the original was restored:\n{e}")

    print("check: patched file compiles")
    print("\nPatched. The change, in full:")
    print("-" * 66)
    print(f"  + URGENT_RETRY_S = 5 * 60   and   _URGENT_TRY = [0.0]")
    print(f"  ~ line {gate_i + 1}: the generation gate now also requires that no attempt")
    print(f"    was made in the last URGENT_RETRY_S seconds, and records each attempt.")
    print("-" * 66)
    print("\nRestart the website to pick it up:   systemctl restart pac")
    print(f"To undo:   cp {backup} {VA} && systemctl restart pac")


if __name__ == "__main__":
    main()
