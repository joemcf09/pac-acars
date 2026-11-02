"""The letters PAC sends to applicants.

Plain text (which every mail program accepts) and an HTML version in PAC's colours. Edit the wording here; the
placeholders in braces are filled in by letter(). Anything not set, like the Discord invite, is simply left out.

Placeholders: {name} {first_name} {pilot_id} {link} {hub} {hub_name} {airline} {site} {discord} {staff_name}
{reason} {expires_days} {sim}
"""

ACCEPTED_SUBJECT = "Welcome to Pagani Air Cargo — your pilot ID is {pilot_id}"
ACCEPTED = """Dear {first_name},

Welcome to Pagani Air Cargo. Your application has been accepted.

  Pilot ID    {pilot_id}
  Home base   {hub} {hub_name}
  Status      Active, line checkride pending

Setting up your account
Use the link below to choose your password and sign in for the first time. It works once and expires in
{expires_days} days; if it lapses, ask staff for a new one.

  {link}

Your first steps
  1. Sign in and finish your pilot profile: photo, callsign and any hours you flew before joining.
  2. Download PAC ACARS from the Downloads page and install it. It tracks your flight, talks to dispatch
     and files your report.
  3. Read the pilot handbook. It's short on purpose and tells you how we fly.
  4. Fly your line checkride, PAC001 from Cincinnati to Nashville in the 737-800BCF. Score 80 or better with a
     landing softer than 400 fpm and you're a line pilot.
{discord_block}
Anything you're unsure about, reply to this message or ask in dispatch. Welcome aboard.

{staff_name}
Pagani Air Cargo — Operations Control, Cincinnati
{site_line}"""

REJECTED_SUBJECT = "Your application to Pagani Air Cargo"
REJECTED = """Dear {first_name},

Thank you for applying to Pagani Air Cargo, and for taking the time to tell us about your flying.

We're not able to offer you a place at the moment.
{reason_block}
This isn't a judgement on you as a pilot. We keep the roster small so every pilot gets proper attention, and we
can only take on so many at once. You're welcome to apply again later; a fresh application is always read
properly.

Clear skies, wherever you fly.

{staff_name}
Pagani Air Cargo — Operations Control, Cincinnati
{site_line}"""

REMINDER_SUBJECT = "Pagani Air Cargo — your sign-in link"
REMINDER = """Dear {first_name},

Here's a fresh link to set your Pagani Air Cargo password. It works once and expires in {expires_days} days.

  {link}

Your pilot ID is {pilot_id}. If you didn't ask for this, you can ignore it: the link is useless without your
email, and your account isn't affected.

{staff_name}
Pagani Air Cargo — Operations Control, Cincinnati
{site_line}"""

DISCORD_BLOCK = """
Our Discord
Crew talk, screenshots and live flight posts: {discord}
"""

REASON_BLOCK = """
  {reason}
"""

HTML_WRAP = """<!doctype html>
<html><body style="margin:0;background:#F4F5F7;padding:24px;font-family:-apple-system,'Segoe UI',system-ui,sans-serif;color:#1E2126">
<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #E3E5E8">
<tr><td style="background:#C80000;padding:18px 24px">
  <span style="color:#fff;font-size:22px;font-weight:800;letter-spacing:.06em">PAGANI AIR CARGO</span><br>
  <span style="color:rgba(255,255,255,.9);font-size:13px">Operations Control &middot; Cincinnati</span></td></tr>
<tr><td style="padding:24px;font-size:15px;line-height:1.6">{body}</td></tr>
<tr><td style="padding:14px 24px;border-top:1px solid #E3E5E8;color:#5E6470;font-size:12px">
  Pagani Air Cargo is a virtual airline for flight simulator pilots. No real-world flights are operated.</td></tr>
</table></body></html>"""


def _first_name(name):
    return (str(name or "").strip().split() or ["pilot"])[0]


def letter(kind, *, name="", pilot_id="", link="", hub="KCVG", hub_name="", site="", discord="", staff_name="PAC Operations Control",
           reason="", expires_days=7, airline="Pagani Air Cargo"):
    """Returns {subject, text, html} for 'accepted', 'rejected' or 'reminder'."""
    bodies = {"accepted": (ACCEPTED_SUBJECT, ACCEPTED), "rejected": (REJECTED_SUBJECT, REJECTED), "reminder": (REMINDER_SUBJECT, REMINDER)}
    subject_t, body_t = bodies[kind]
    fields = {"name": name, "first_name": _first_name(name), "pilot_id": pilot_id, "link": link, "hub": hub,
              "hub_name": f"({hub_name})" if hub_name else "", "airline": airline, "site": site, "discord": discord,
              "staff_name": staff_name, "reason": reason, "expires_days": expires_days,
              "discord_block": DISCORD_BLOCK.format(discord=discord) if discord else "",
              "reason_block": REASON_BLOCK.format(reason=reason) if reason else "",
              "site_line": site or ""}
    text = body_t.format(**fields).strip()
    subject = subject_t.format(**fields)

    # the same words as HTML: paragraphs, indented blocks kept as they are, and the link as a button
    html_parts = []
    for block in text.split("\n\n"):
        if link and link in block:
            before = block.split(link)[0].strip()
            if before:
                html_parts.append(f'<p style="margin:0 0 14px">{_esc(before)}</p>')
            html_parts.append(f'<p style="margin:0 0 18px"><a href="{_esc(link)}" style="background:#C80000;color:#fff;'
                              f'text-decoration:none;padding:11px 20px;display:inline-block;font-weight:700">Set your password</a></p>'
                              f'<p style="margin:0 0 18px;font-size:12px;color:#5E6470;word-break:break-all">{_esc(link)}</p>')
        elif block.startswith("  "):
            rows = "".join(f'<tr><td style="padding:3px 16px 3px 0;color:#5E6470">{_esc(r.strip())}</td></tr>' for r in block.split("\n"))
            html_parts.append(f'<table role="presentation" style="margin:0 0 14px;font-size:14px">{rows}</table>')
        else:
            html_parts.append(f'<p style="margin:0 0 14px">{_esc(block).replace(chr(10), "<br>")}</p>')
    return {"subject": subject, "text": text, "html": HTML_WRAP.format(body="".join(html_parts))}


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
