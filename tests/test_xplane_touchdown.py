"""X-Plane touchdown rate: taken from the true vertical speed in the last packet before the wheels touch."""
import os, socket, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim_sources import XPlaneSource

failures = []
def check(name, ok, info=""):
    print(("  ok  " if ok else "FAIL  ") + name, "" if ok else info)
    if not ok: failures.append(name)

src = XPlaneSource()
src.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); src.sock.bind(("127.0.0.1", 0))
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
IDX = {k: i for i, (k, _) in enumerate(src.DATAREFS)}

def send(**vals):
    body = b"".join(struct.pack("<if", IDX[k], v) for k, v in vals.items())
    tx.sendto(b"RREF\x00" + body, src.sock.getsockname())
    time.sleep(0.02)

base = dict(lat=25.0, lon=-77.0, on_ground=0.0)
# a flare: true vertical speed falls from -4.0 to -1.56 m/s (-307 fpm) while the lagging VSI still reads -470
for vy in (-4.0, -3.0, -2.2, -1.56):
    send(**base, vy_ms=vy, vs_fpm=-470.0)
s = src.read()
check("no touchdown rate while airborne", s.touchdown_fpm is None, s.touchdown_fpm)
send(**{**base, "on_ground": 1.0}, vy_ms=-0.1, vs_fpm=-470.0)
s = src.read()
check("touchdown is the last airborne true rate (about -307 fpm)", s.touchdown_fpm is not None and abs(s.touchdown_fpm + 307) < 2, s.touchdown_fpm)
check("the lagging VSI value isn't used", round(s.touchdown_fpm) != -470)
send(**{**base, "on_ground": 1.0}, vy_ms=0.0)
check("rollout doesn't create a second touchdown", src._air_vy is None)
print(); print("XPLANE TOUCHDOWN TEST PASSED" if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
