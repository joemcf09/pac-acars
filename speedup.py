"""PAC website speed-up: a short server-side cache for the heavy start-up data, and browser caching for files that
don't change. The droplet has one CPU, so the home page's requests used to queue behind each other.

- GET /api/bootstrap, /api/va/home, /api/va/board: the answer is kept for a few seconds per visitor (60 s for
  visitors who aren't signed in, 10 s for pilots). Any change on the site (any POST, PUT or DELETE, such as a
  booking or a filed PIREP; not the ACARS position updates sent every few seconds) clears the cache at once, so nobody sees their own change late.
- Fonts, versioned files (?v=...) and resized images get browser caching, so repeat visits don't download them again.
Turn it off without undoing anything: set PAC_SPEEDUP=0 in the service and restart."""
import os
import threading
import time

from flask import request, session

CACHED = {"/api/bootstrap", "/api/va/home", "/api/va/board"}
# ACARS sends these every few seconds while someone flies; they don't change bookings or pages, so they don't clear the cache
LIVE = {"/api/acars/app/live", "/api/acars/app/checkpoint", "/api/acars/app/sayintentions"}
TTL_GUEST, TTL_PILOT = 60, 10
_store, _lock = {}, threading.Lock()


def _key():
    pid = None
    try:
        pid = session.get("pid")
    except Exception:
        pass
    return (request.path, request.query_string, pid or ""), bool(pid)


def init(app):
    if os.environ.get("PAC_SPEEDUP", "1") == "0":
        print("  speedup: off (PAC_SPEEDUP=0)")
        return

    @app.before_request
    def _speedup_hit():
        if request.method != "GET" or request.path not in CACHED:
            return None
        key, _ = _key()
        with _lock:
            hit = _store.get(key)
        if hit and hit[0] > time.time():
            resp = app.response_class(hit[1], status=200, mimetype="application/json")
            resp.headers["X-PAC-Cache"] = "hit"
            return resp
        return None

    @app.after_request
    def _speedup_store(resp):
        p = request.path
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and p not in LIVE:
            with _lock:
                _store.clear()                      # something changed: everyone gets fresh data
            return resp
        if request.method == "GET" and p in CACHED and resp.status_code == 200 and resp.mimetype == "application/json" \
                and "Set-Cookie" not in resp.headers and resp.headers.get("X-PAC-Cache") != "hit" and not resp.headers.get("X-PAC-No-Cache"):
            key, pilot = _key()
            with _lock:
                if len(_store) > 500:
                    _store.clear()
                _store[key] = (time.time() + (TTL_PILOT if pilot else TTL_GUEST), resp.get_data())
            resp.headers["X-PAC-Cache"] = "miss"
        # browser caching for files that don't change under the same address
        if request.method == "GET" and resp.status_code == 200 and "max-age" not in resp.headers.get("Cache-Control", ""):
            ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
            if p.startswith("/static/") and ext in ("woff2", "woff", "ttf"):
                resp.headers["Cache-Control"] = "public, max-age=2592000"            # fonts: 30 days
            elif p.startswith("/media/image") and "v=" in request.query_string.decode(errors="ignore"):
                resp.headers["Cache-Control"] = "public, max-age=2592000"            # resized photo, versioned address
            elif p.startswith("/media/image") or (p.startswith("/static/") and ext in ("png", "jpg", "jpeg", "webp", "svg", "gif")):
                resp.headers["Cache-Control"] = "public, max-age=86400"              # other images: a day
            elif p.startswith("/static/") and ext in ("css", "js") and request.args.get("v") \
                    and resp.headers.get("Cache-Control") != "no-cache":
                resp.headers["Cache-Control"] = "public, max-age=2592000"            # versioned css/js
        return resp

    print("  speedup: on (start-up data cached briefly, browser caching for fonts and images)")
