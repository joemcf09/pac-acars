"""Loadsheet to the cockpit over Hoppie's ACARS.

PAC Load Control sends the final loadsheet as a telex from the station PACLD to the flight's callsign, the way a real
load controller uplinks it before pushback. The pilot logs on in the aircraft as usual with their own Hoppie code.
PAC's own logon code lives in data/hoppie_logon (or the PAC_HOPPIE_LOGON environment variable) and never leaves the
server. If Hoppie can't be reached, nothing else is affected: the PDF loadsheet works as always."""
from __future__ import annotations

import os
import re
import time
import urllib.parse
import urllib.request

STATION = "PACLD"
URL = "https://www.hoppie.nl/acars/system/connect.html"


def _file(data_dir):
    return os.path.join(str(data_dir), "hoppie_logon")


def logon(data_dir):
    k = os.environ.get("PAC_HOPPIE_LOGON", "").strip()
    if not k:
        try:
            k = open(_file(data_dir), encoding="utf-8").read().strip()
        except OSError:
            k = ""
    return k


def save_logon(data_dir, code):
    code = str(code or "").strip()
    if code and not re.fullmatch(r"[A-Za-z0-9]{6,40}", code):
        raise ValueError("That doesn't look like a Hoppie logon code (letters and numbers only).")
    p = _file(data_dir)
    if not code:
        try:
            os.remove(p)
        except OSError:
            pass
        return
    with open(p, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _n(v):
    return "----" if v is None else f"{int(round(v)):,}".replace(",", "")


def telex(d, paper, callsign, edno=1, now=None):
    """The loadsheet as an ACARS telex: short upper-case lines that fit a cockpit screen or printer."""
    now = now or time.time()
    ls, lim = paper.get("loadsheet") or {}, paper.get("limits") or {}
    m = d.get("mission") or {}
    dep = (m.get("origin") or {}).get("icao") or d.get("dep") or ""
    arr = (m.get("destination") or {}).get("icao") or d.get("arr") or ""
    t = time.gmtime(now)
    lines = [f"LOADSHEET FINAL {time.strftime('%H%MZ', t)}", f"EDNO {edno}",
             f"{callsign}/{time.strftime('%d%b', t).upper()} {dep} {arr}",
             f"{d.get('aircraft') or ''} {d.get('tail') or ''}  CREW {ls.get('crew') or '-'}",
             f"ZFW {_n(ls.get('zfw')):>7}  MAX {_n(lim.get('mzfw'))}",
             f"TOF {_n(ls.get('tof')):>7}",
             f"TOW {_n(ls.get('tow')):>7}  MAX {_n(lim.get('mtow'))}",
             f"TIF {_n(ls.get('trip')):>7}",
             f"LAW {_n(ls.get('law')):>7}  MAX {_n(lim.get('mlw'))}",
             f"UNDERLOAD {_n(ls.get('underload'))}"]
    if ls.get("mac_zfw") is not None:
        lines.append(f"MACZFW {ls['mac_zfw']}  MACTOW {ls.get('mac_tow')}")
    lim_cg = ls.get("cg_limits")
    if lim_cg and ls.get("mac_tow") is not None:
        worst = max(ls.get("mac_zfw") or 0, ls.get("mac_tow") or 0)
        low = min(ls.get("mac_zfw") or 99, ls.get("mac_tow") or 99)
        state = "OUTSIDE LIMITS" if worst > lim_cg[1] or low < lim_cg[0] else "NEAR AFT LIMIT" if worst > lim_cg[1] - 2 else "WITHIN LIMITS"
        lines.append(f"CG LIMITS {lim_cg[0]:g}-{lim_cg[1]:g} MAC")
        lines.append(state)
    if ls.get("trim"):
        lines.append("TRIM " + str(ls["trim"]).replace(" (TAKEOFF REF)", "").replace(" UNITS", "U"))
    lines.append(f"PAYLOAD {_n(ls.get('payload'))} LB")
    if ls.get("supy"):
        lines.append(f"SUPY {ls['supy']}")
    dg = d.get("dg") or []
    lines.append(f"DG {len(dg)} ITEMS SEE NOTOC" if dg else "DG NIL  NOTOC NIL")
    lines += ["LMC NIL", "WEIGHTS IN LB", "-- PAC LOAD CONTROL --"]
    # the A300's MCDU shows 24 characters a line: wrap anything longer at a space
    out = []
    for ln in lines:
        while len(ln) > 24:
            cut = ln.rfind(" ", 0, 25)
            cut = cut if cut > 0 else 24
            out.append(ln[:cut].rstrip()); ln = ln[cut:].lstrip()
        out.append(ln)
    return "\n".join(out).upper()


def send(code, to, text, timeout=8):
    """Sends a telex. Returns None when it went through, otherwise the reason."""
    if not code:
        return "PAC's Hoppie logon code isn't set up yet."
    body = urllib.parse.urlencode({"logon": code, "from": STATION, "to": to.upper(), "type": "telex", "packet": text}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, data=body, headers={"User-Agent": "PAC-LoadControl/1.0"}), timeout=timeout) as r:
            reply = r.read().decode("utf-8", "replace").strip()
    except Exception:
        return "Hoppie's ACARS can't be reached right now. Use the printed loadsheet."
    if reply.lower().startswith("ok"):
        return None
    return "Hoppie refused the message: " + re.sub(r"[{}]", "", reply)[:120]
