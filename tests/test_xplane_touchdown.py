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
    send(**base, vy_ms=vy, vs_fpm=-470.0)   # no height above ground in this part: falls back to the true rate
s = src.read()
check("no touchdown rate while airborne", s.touchdown_fpm is None, s.touchdown_fpm)
send(**{**base, "on_ground": 1.0}, vy_ms=-0.1, vs_fpm=-470.0)
s = src.read()
check("touchdown is the last airborne true rate (about -307 fpm)", s.touchdown_fpm is not None and abs(s.touchdown_fpm + 307) < 2, s.touchdown_fpm)
check("the lagging VSI value isn't used", round(s.touchdown_fpm) != -470)
send(**{**base, "on_ground": 1.0}, vy_ms=0.0)
check("rollout doesn't create a second touchdown", src._air_vy is None)

print("Sloping runway (PAC8800 at ZGOW): sea-level vertical speed -455 fpm, but the height above the ground barely changes")
src2 = XPlaneSource()
src2.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); src2.sock.bind(("127.0.0.1", 0))
def send2(**vals):
    body = b"".join(struct.pack("<if", IDX[k], v) for k, v in vals.items())
    tx.sendto(b"RREF\x00" + body, src2.sock.getsockname()); time.sleep(0.05); src2.read()
agl = 1.2
for i in range(14):                 # 0.7 s of samples: sinking toward the ground at 0.67 m/s (132 fpm)
    send2(**base, vy_ms=-2.31, vs_fpm=-455.0, agl_m=agl); agl -= 0.67 * 0.05
send2(**{**base, "on_ground": 1.0}, vy_ms=-0.1, vs_fpm=-455.0, agl_m=agl)
s2 = src2.read()
check("touchdown is measured against the ground (about -132 fpm), not sea level (-455)",
      s2 and s2.touchdown_fpm is not None and abs(s2.touchdown_fpm + 132) < 35, s2 and s2.touchdown_fpm)
print(); print("XPLANE TOUCHDOWN TEST PASSED" if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
