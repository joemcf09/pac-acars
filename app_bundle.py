"""The website's script, /static/app.js, is kept as numbered pieces in static/app/ so each part of the site can be
read and changed on its own (01-core.js, 02-missions.js, ...). Browsers still get one app.js: the pieces are joined
in file-name order, exactly as written, so the page behaves as if it were a single file (every function can call any
other, as before). A short comment marks where each piece starts, so a line in the browser's error console can be
traced back to its piece.

To add a piece, give it a number between its neighbours (07b-*.js sorts after 07-*.js). Order matters only for code
that runs while the page loads; functions can live anywhere."""
import hashlib
import threading
from pathlib import Path

PIECES = Path(__file__).resolve().parent / "static" / "app"
_lock = threading.Lock()
_cache = {}


def pieces():
    return sorted(PIECES.glob("*.js"))


def source():
    """(text, etag) of the joined script, rebuilt only when a piece changes."""
    files = pieces()
    key = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in files)
    with _lock:
        if _cache.get("key") != key:
            out = []
            for p in files:
                text = p.read_text(encoding="utf-8")
                out.append(f"/* ==== static/app/{p.name} ==== */\n{text}")
                if not text.endswith("\n"):
                    out.append("\n")
            joined = "".join(out)
            _cache.update(key=key, text=joined, etag=hashlib.sha1(joined.encode("utf-8")).hexdigest()[:20])
        return _cache["text"], _cache["etag"]


def locate(line):
    """Which piece, and which line in it, a line number of the joined /static/app.js falls on: "05-logbook.js:120"."""
    at = 1
    for p in pieces():
        n = p.read_text(encoding="utf-8").count("\n") + 1      # its header line, then its own lines
        if line < at + n:
            return f"{p.name}:{max(1, line - at)}"
        at += n
    return None


def plain_source():
    """The pieces joined with nothing added: what tests search when they look for something in the site's script."""
    return "".join(p.read_text(encoding="utf-8") for p in pieces())
