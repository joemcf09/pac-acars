"""Email on a server whose host blocks the usual mail ports (DigitalOcean and others): PAC finds a spare port."""
import contextlib
import smtplib
import socket
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mailer  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


OPEN = set()        # ports that answer in this test
sent = []


@contextlib.contextmanager
def fake_conn(addr, timeout=None):
    if addr[1] not in OPEN:
        raise TimeoutError("timed out")
    yield None


class FakeSMTP:
    def __init__(self, host, port, timeout=None, context=None):
        if port not in OPEN:
            raise TimeoutError("timed out")
        self.port, self.esmtp_features = port, {"auth": "PLAIN LOGIN"}

    def ehlo(self): pass
    def starttls(self, context=None): pass
    def set_debuglevel(self, n): pass
    def login(self, u, p): pass
    def send_message(self, msg): sent.append(self.port)
    def quit(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


socket.create_connection = fake_conn
smtplib.SMTP = smtplib.SMTP_SSL = FakeSMTP
socket.gethostbyname = lambda h: "192.0.2.1"
ST = {"smtp_host": "smtp.resend.com", "smtp_port": 465, "smtp_security": "ssl", "smtp_user": "resend",
      "smtp_pass": "re_test", "mail_from": "ops@pac-va.com", "mail_from_name": "Pagani Air Cargo"}

OPEN.clear(); OPEN.update({2465, 2587})
d = mailer.diagnose(ST)
check("the check tries Resend's spare ports when 465 and 587 are blocked", [p["port"] for p in d["ports"]] == [465, 587, 2465, 2587], d["ports"])
check("it explains the host is blocking mail ports", "host blocks" in (d.get("advice") or ""), d.get("advice"))
check("it offers the port that works", d.get("suggest") == {"smtp_port": 2465, "smtp_security": "ssl"}, d.get("suggest"))

ok, err = mailer.send(ST, "pilot@example.com", "Welcome", "Hello", wait=True)
check("a letter still goes out on the spare port", ok and sent[-1] == 2465, err)
check("PAC remembers the port that worked", mailer.status.get("suggest") == {"smtp_port": 2465, "smtp_security": "ssl"})

OPEN.clear(); OPEN.update({465, 587, 2465})
d = mailer.diagnose(ST)
check("spare ports aren't tried when a usual port works", [p["port"] for p in d["ports"]] == [465, 587] and not d.get("advice"), d["ports"])

OPEN.clear()
d = mailer.diagnose({**ST, "smtp_host": "smtp.gmail.com", "smtp_user": "x@gmail.com"})
check("Gmail blocked: suggests a service with a spare port", "Resend" in (d.get("advice") or ""), d.get("advice"))
ok, err = mailer.send({**ST, "smtp_host": "smtp.gmail.com"}, "pilot@example.com", "Welcome", "Hello", wait=True)
check("…and a failed letter points to the connection check", not ok and "Check the connection" in err, err)

print("\n" + ("MAIL PORTS TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
