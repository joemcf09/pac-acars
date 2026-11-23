"""Sending PAC's letters from the airline's own email account.

PAC connects to an ordinary mailbox (Gmail, Outlook, Fastmail, a domain mailbox) over SMTP and sends from it, so
letters arrive from operations@yourairline.com rather than your personal address. Sending happens in the
background with a time limit: a mail problem must never hold up approving a pilot.

Gmail and Outlook need an app password rather than your normal one, because PAC isn't a browser:
  Gmail      myaccount.google.com > Security > 2-Step Verification > App passwords (smtp.gmail.com, port 587)
  Outlook    account.microsoft.com > Security > App passwords (smtp-mail.outlook.com, port 587)
Most other providers use port 587 with STARTTLS, or port 465 with SSL.
"""
from __future__ import annotations

import re
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
TIMEOUT = 20
PRESETS = {                       # the common providers, so staff needn't look up the settings
    "gmail.com": ("smtp.gmail.com", 587, "starttls"),
    "googlemail.com": ("smtp.gmail.com", 587, "starttls"),
    "outlook.com": ("smtp-mail.outlook.com", 587, "starttls"),
    "hotmail.com": ("smtp-mail.outlook.com", 587, "starttls"),
    "live.com": ("smtp-mail.outlook.com", 587, "starttls"),
    "yahoo.com": ("smtp.mail.yahoo.com", 587, "starttls"),
    "fastmail.com": ("smtp.fastmail.com", 465, "ssl"),
    "zoho.com": ("smtp.zoho.com", 587, "starttls"),
    "icloud.com": ("smtp.mail.me.com", 587, "starttls"),
}
status = {"last_ok": None, "last_error": None, "sent": 0, "last_to": None}


# Sending services that also listen on spare ports, for servers whose host blocks 465 and 587 (DigitalOcean, Linode,
# Vultr and others do this on new accounts to stop spam).
ALT_PORTS = {
    "smtp.resend.com": [(2465, "ssl"), (2587, "starttls")],
    "smtp-relay.brevo.com": [(2525, "starttls")],
    "smtp.mailgun.org": [(2525, "starttls")],
    "smtp.eu.mailgun.org": [(2525, "starttls")],
    "smtp.sendgrid.net": [(2525, "starttls")],
    "smtp.postmarkapp.com": [(2525, "starttls")],
}
BLOCKED_HINT = ("Nothing answered on the usual mail ports, which almost always means the server's host blocks them "
                "(DigitalOcean does this on new accounts).")


def port_plan(host, port, sec):
    """The ports to try, in order: the one set, the other usual one, then any spare ports the service offers."""
    plan = [(port, sec)] + [t for t in ((587, "starttls"), (465, "ssl")) if t != (port, sec)]
    plan += [t for t in ALT_PORTS.get(host.lower(), []) if t not in plan]
    return plan


def valid_email(a):
    return bool(a and EMAIL_RE.match(str(a).strip()))


def guess(address):
    """Server settings for a well-known address, so staff only type the address and app password."""
    host, port, sec = PRESETS.get(str(address).rsplit("@", 1)[-1].lower(), ("", 587, "starttls"))
    return {"smtp_host": host, "smtp_port": port, "smtp_security": sec}


def config_ready(st):
    return bool(valid_email(st.get("mail_from")) and st.get("smtp_host") and clean_password(st.get("smtp_pass")))


def _build(st, to, subject, text, html=None, reply_to=None):
    m = EmailMessage()
    m["From"] = formataddr((st.get("mail_from_name") or "Pagani Air Cargo", st["mail_from"]))
    m["To"] = to
    m["Subject"] = subject
    m["Message-ID"] = make_msgid(domain=str(st["mail_from"]).rsplit("@", 1)[-1])
    if reply_to or st.get("mail_reply_to"):
        m["Reply-To"] = reply_to or st["mail_reply_to"]
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    return m


def clean_password(p):
    """App passwords are shown in groups of four ('abcd efgh ijkl mnop'); the spaces aren't part of the password."""
    return "".join(str(p or "").split())


def _attempt(host, port, sec, user, password, msg):
    """One connection attempt. Returns None when the message went, or an error description."""
    ctx = ssl.create_default_context()
    try:
        if sec == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=ctx) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=TIMEOUT) as s:
                s.ehlo()
                if sec != "none":
                    s.starttls(context=ctx)
                    s.ehlo()
                s.login(user, password)
                s.send_message(msg)
        return None
    except smtplib.SMTPAuthenticationError:
        return ("auth", "The mail server refused the sign-in. Use an app password (not your normal password), and check the address is right.")
    except smtplib.SMTPRecipientsRefused:
        return ("refused", "The mail server wouldn't accept that address.")
    except (smtplib.SMTPException, OSError) as e:
        return ("connect", f"Couldn't reach the mail server ({e.__class__.__name__}).")


def send(st, to, subject, text, html=None, wait=False, reply_to=None):
    """Send one letter. Returns (ok, error) when waiting; otherwise sends in the background and returns None.
    If the connection drops (a blocked or fussy port), PAC tries the provider's other port once before giving up."""
    import site_mode
    if site_mode.staging():                       # the test copy never emails real pilots
        status["last_error"] = site_mode.NOTE
        return (False, site_mode.NOTE) if wait else None
    if not config_ready(st):
        err = "PAC's email account isn't set up yet (Staff › Site and rules › Email)."
        status["last_error"] = err
        return (False, err) if wait else None
    if not valid_email(to):
        err = f"{to or 'That address'} isn't a valid email address."
        return (False, err) if wait else None
    msg = _build(st, to, subject, text, html, reply_to)
    host, port = st["smtp_host"].strip(), int(st.get("smtp_port") or 587)
    sec = (st.get("smtp_security") or "starttls").lower()
    user = (st.get("smtp_user") or st["mail_from"]).strip()
    password = clean_password(st.get("smtp_pass"))

    def run():
        tries = port_plan(host, port, sec) if port in (465, 587) else [(port, sec)]   # 587/465 may be blocked or mangled
        problem = None
        for i, (p_, sec_) in enumerate(tries):
            problem = _attempt(host, p_, sec_, user, password, msg)
            if problem is None:
                status.update(last_ok=time.time(), last_error=None, sent=status["sent"] + 1, last_to=to)
                if i:                          # the fallback worked: remember it so the next letter goes first time
                    status["suggest"] = {"smtp_port": p_, "smtp_security": sec_}
                return True, None
            if problem[0] in ("auth", "refused"):
                break                          # a wrong password or address won't be fixed by another port
        kind, err = problem
        if kind == "connect":
            err += (" PAC also tried the other ports this service uses. If PAC runs on a cloud server, its host is "
                    "probably blocking mail ports: run Check the connection in Staff › Site and rules › Email.")
        status["last_error"] = f"{time.strftime('%H:%M')} {err}"
        print("Email:", err)
        return False, err
    if wait:
        return run()
    threading.Thread(target=run, daemon=True).start()
    return None


def _short(v, n=180):
    t = v.decode(errors="replace") if isinstance(v, (bytes, bytearray)) else str(v)
    return t.replace("\n", " ")[:n]


def diagnose(st):
    """Check PAC's email settings step by step, so a failure says which step broke: finding the server (DNS),
    connecting (a firewall or ISP block), securing the connection (TLS, often antivirus), or signing in (password)."""
    import socket
    host = (st.get("smtp_host") or "").strip()
    user = (st.get("smtp_user") or st.get("mail_from") or "").strip()
    password = clean_password(st.get("smtp_pass"))
    out = {"host": host, "user": user, "password_length": len(password), "steps": [], "ports": []}
    if not host:
        out["steps"].append(["Settings", False, "No mail server is set."])
        return out
    try:
        ip = socket.gethostbyname(host)
        out["steps"].append(["Finding the server", True, f"{host} is {ip}"])
    except OSError as e:
        out["steps"].append(["Finding the server", False, f"{host} couldn't be looked up ({e.__class__.__name__}). Check the server address."])
        return out
    want = (int(st.get("smtp_port") or 587), (st.get("smtp_security") or "starttls").lower())
    usual = [want] + [t for t in ((587, "starttls"), (465, "ssl")) if t != want]
    spare = [t for t in ALT_PORTS.get(host.lower(), []) if t not in usual]
    out["spare_ports"] = [p for p, _ in spare]
    tries = usual + spare
    for i, (port, sec) in enumerate(tries):
        if i == len(usual) and any(r["connect"] for r in out["ports"]):
            break                          # a usual port connects: the spare ones aren't needed
        r = {"port": port, "security": sec, "connect": None, "secure": None, "login": None, "note": ""}
        t0 = time.time()
        try:
            with socket.create_connection((host, port), timeout=10):
                r["connect"] = True
        except OSError as e:
            r["connect"] = False
            r["note"] = f"Nothing answered on port {port} ({e.__class__.__name__}). Usually a firewall, antivirus or ISP block."
            out["ports"].append(r)
            continue
        try:
            ctx = ssl.create_default_context()
            if sec == "ssl":
                s_ = smtplib.SMTP_SSL(host, port, timeout=15, context=ctx)
            else:
                s_ = smtplib.SMTP(host, port, timeout=15)
                s_.ehlo()
                if sec != "none":
                    s_.starttls(context=ctx)
                    s_.ehlo()
            r["secure"] = True if sec != "none" else None
            r["auth_methods"] = sorted(getattr(s_, "esmtp_features", {}).get("auth", "").split()) or ["(none offered)"]
            import contextlib
            import io
            log = io.StringIO()
            s_.set_debuglevel(1)
            try:
                with contextlib.redirect_stderr(log):
                    s_.login(user, password)
                r["login"] = True
                r["note"] = "This port works."
            except smtplib.SMTPAuthenticationError as e:
                r["login"] = False
                r["note"] = f"Sign-in refused: {getattr(e, 'smtp_code', '')} {_short(getattr(e, 'smtp_error', b''))}"
            except (smtplib.SMTPException, OSError) as e:
                r["login"] = False
                r["note"] = f"The server dropped the connection during sign-in ({e.__class__.__name__})."
            finally:
                s_.set_debuglevel(0)
                said = [ln[6:].strip() for ln in log.getvalue().splitlines() if ln.startswith("reply:") and "b'" in ln]
                clean = []
                for x in said[-4:]:
                    t = x.strip()
                    if t.startswith("b'") or t.startswith('b"'):
                        t = t[2:-1]
                    t = t.replace("\\r\\n", " ").replace("\\n", " ").strip()
                    if t and not t.startswith("250"):
                        clean.append(t)
                r["server_said"] = clean[-2:]
                try:
                    s_.quit()
                except Exception:
                    pass
        except ssl.SSLError as e:
            r["secure"] = False
            r["note"] = f"The secure connection failed ({e.__class__.__name__}). Antivirus mail scanning is the usual cause."
        except (smtplib.SMTPException, OSError) as e:
            r["secure"] = False
            r["note"] = (f"The server dropped the connection while securing it ({e.__class__.__name__}). Antivirus mail "
                         "scanning or a firewall is the usual cause.")
        r["seconds"] = round(time.time() - t0, 1)
        out["ports"].append(r)
    usual_blocked = all(r["connect"] is False for r in out["ports"] if r["port"] in (465, 587))
    works = [r for r in out["ports"] if r.get("login")]
    if usual_blocked:
        if works:
            out["advice"] = (f"{BLOCKED_HINT} Port {works[0]['port']} works instead: set Port to {works[0]['port']} and "
                             f"Security to {'SSL' if works[0]['security'] == 'ssl' else 'STARTTLS'}, then save.")
            out["suggest"] = {"smtp_port": works[0]["port"], "smtp_security": works[0]["security"]}
        elif spare:
            out["advice"] = f"{BLOCKED_HINT} The spare ports didn't work either, so ask your host to unblock mail."
        else:
            out["advice"] = (f"{BLOCKED_HINT} Use a sending service with a spare port, such as Resend (port 2465, SSL), "
                             "or ask your host to unblock mail.")
    return out
