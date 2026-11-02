"""Posting PAC flights to a Discord channel through a webhook (Server settings > Integrations > Webhooks).

Nothing here may slow down or break flying: every post runs in the background with a time limit,
and a failure is only remembered (shown in Staff > Site and rules), never raised.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
import uuid

WEBHOOK_RE = re.compile(r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")
RED, GREEN, AMBER, GREY = 0xC80000, 0x1F9D55, 0xF2A900, 0x5E6470
GRADE_COLOUR = {"A": GREEN, "B": 0x4BA36B, "C": AMBER, "D": 0xE07B00, "F": RED}
status = {"last_ok": None, "last_error": None, "sent": 0}


def valid_webhook(url):
    return bool(url and WEBHOOK_RE.match(url.strip()))


def _send(url, payload, image=None, filename="image.png"):
    """POST to the webhook: JSON, or multipart with one image attached."""
    headers = {"User-Agent": "PAC-Flight-Operations/1.0"}
    if image is None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    else:
        boundary = "----PAC" + uuid.uuid4().hex
        parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\nContent-Type: application/json\r\n\r\n".encode()
                 + json.dumps(payload).encode() + b"\r\n",
                 f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n".encode()
                 + image + b"\r\n", f"--{boundary}--\r\n".encode()]
        body = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url.strip() + "?wait=false", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.status


def post(url, payload, image=None, filename="image.png", wait=False):
    """Send in the background (or wait, for the test button). Returns (ok, error) when waiting."""
    if not valid_webhook(url):
        status["last_error"] = "The Discord webhook address isn't valid."
        return (False, status["last_error"]) if wait else None
    payload = {"username": "PAC Operations", **payload}

    def run():
        try:
            _send(url, payload, image, filename)
            status.update(last_ok=time.time(), last_error=None, sent=status["sent"] + 1)
            return True, None
        except urllib.error.HTTPError as e:
            msg = f"Discord answered HTTP {e.code}" + (" (the webhook was deleted or the address is wrong)" if e.code in (401, 404) else "")
        except Exception as e:  # offline, timeout
            msg = f"Couldn't reach Discord ({e.__class__.__name__})"
        status["last_error"] = f"{time.strftime('%H:%M')} {msg}"
        print("Discord:", msg)
        return False, msg
    if wait:
        return run()
    threading.Thread(target=run, daemon=True).start()
    return None


def _footer():
    return {"text": "Pagani Air Cargo · flight simulation"}


def departure_embed(b, st):
    m = b["mission"]
    fields = [{"name": "Route", "value": f"{m['origin']['icao']} → {m['destination']['icao']}", "inline": True},
              {"name": "Aircraft", "value": f"{b.get('aircraft_name') or b['aircraft']}{' · ' + b['airframe'] if b.get('airframe') else ''}", "inline": True},
              {"name": "Cargo", "value": f"{m.get('payload_lbs', 0):,} lb · {m.get('cargo') or '—'}"[:1000], "inline": False}]
    if b.get("pilot_name"):
        fields.append({"name": "Pilot", "value": b["pilot_name"], "inline": True})
    if (b.get("ofp") or {}).get("cruise_ft"):
        fields.append({"name": "Cruise", "value": f"FL{round(b['ofp']['cruise_ft'] / 100):03d}", "inline": True})
    return {"embeds": [{"title": f"🛫 {b['flight_number']} departed {m['origin']['icao']}", "description": m.get("title", ""),
                        "color": RED, "fields": fields, "footer": _footer(), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]}


def arrival_embed(p, pilot_name=None):
    la = p.get("landing_analysis") or {}
    rate = p.get("landing_rate")
    verdict = (la.get("verdict") or "").title()
    block = p.get("block_min") or 0
    fields = [{"name": "Landing", "value": f"{rate} fpm{' · ' + verdict if verdict else ''}" if rate is not None else "—", "inline": True},
              {"name": "Grade", "value": f"{p.get('grade', '—')} · {p.get('score', '—')}/100", "inline": True},
              {"name": "Block time", "value": f"{int(block // 60)}h {int(block % 60):02d}m", "inline": True}]
    if la.get("runway"):
        fields.append({"name": "Runway", "value": f"{la.get('airport', '')} {la['runway']}".strip(), "inline": True})
    fields.append({"name": "Points", "value": f"{p.get('points', 0):,}", "inline": True})
    if pilot_name:
        fields.append({"name": "Pilot", "value": pilot_name, "inline": True})
    return {"embeds": [{"title": f"🛬 {p.get('flight_number', '')} arrived {p.get('arr', '')}", "description": f"{p.get('mission_title') or ''} · {p.get('status', '')}",
                        "color": GRADE_COLOUR.get(p.get("grade"), GREY), "fields": fields, "footer": _footer(),
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]}
