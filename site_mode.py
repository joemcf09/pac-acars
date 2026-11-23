"""Is this PAC's test copy (staging.pac-va.com)?

The test copy runs the same code on a copy of the live data, so it would otherwise inherit the live Discord webhooks,
email account, Hoppie logon and SayIntentions key, and post to the real Discord, email real pilots or answer real cockpits. With
PAC_STAGING=1 in its service, nothing leaves the server: Discord posts, emails, Hoppie telexes and
SayIntentions pushes are switched off here, at the one place each is sent from, whatever the copied settings say. Reading things (weather, VATSIM, SimBrief) is fine."""
import os

NOTE = "This is PAC's test site: it never sends Discord posts, emails, Hoppie messages or SayIntentions updates."


def staging():
    return os.environ.get("PAC_STAGING", "").strip().lower() in ("1", "true", "yes")
