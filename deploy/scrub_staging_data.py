"""Removes the live site's secrets from a copy of its data, for the test copy.

    python3 scrub_staging_data.py /home/pac/pac-staging/shared/data

The test copy already refuses to send anything (PAC_STAGING=1); this is the second lock, so the copy doesn't even hold
the keys. Pilots, flights, bookings and settings stay as they are, so the test copy behaves like the live site."""
import json
import sys
from pathlib import Path

SECRET_SETTINGS = ("discord_webhook", "smtp_pass", "si_va_key", "discord_bot_token", "group_feed_key", "smtp_user")
SECRET_FILES = ("bot_secret", "hoppie_logon", "secret_key")


def scrub(data_dir):
    data = Path(data_dir)
    removed = []
    st_path = data / "settings.json"
    if st_path.exists():
        st = json.loads(st_path.read_text(encoding="utf-8") or "{}")
        for k in SECRET_SETTINGS:
            if st.get(k):
                st[k] = ""
                removed.append(k)
        st["si_enabled"] = False
        st_path.write_text(json.dumps(st, indent=2), encoding="utf-8")
    for name in SECRET_FILES:
        f = data / name
        if f.exists():
            f.unlink()
            removed.append(name)
    return removed


if __name__ == "__main__":
    gone = scrub(sys.argv[1])
    print("Removed from the copy: " + (", ".join(gone) if gone else "nothing (no secrets found)"))
