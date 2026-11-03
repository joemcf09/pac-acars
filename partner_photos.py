"""Real-world photos of partner airlines' aircraft for landing and takeoff cards, from Wikimedia Commons.

For each partner airline and aircraft type, PAC asks the Wikimedia Commons API for photos of that airline's aircraft
(first by the airline's real registrations, then by airline and type), keeps only photos whose licence allows reuse
(public domain, CC0, CC BY, CC BY-SA; the most permissive first), records the photographer and the licence for the
credit line on the card, and downloads one display copy to data/partner_photos. Nothing is ever hot-linked.

Staff can ask for the next photo, pin a particular Commons file, or switch a combination back to the PAC photo.
If anything fails (no network, no suitable photo), the card simply uses the PAC photo as before.
"""
from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Response, abort, jsonify, request, send_file

API = "https://commons.wikimedia.org/w/api.php"
UA = "PaganiAirCargo-VA/1.0 (https://pac-va.com; flight simulation virtual airline; card photos with attribution)"
RETRY_S = 6 * 3600          # after a failed search, wait before asking Commons again
WIDTH = 1600                # display copy width

# how each partner and type is named on Commons
NAMES = {"ups": ["UPS Airlines", "UPS"], "fedex": ["FedEx Express", "FedEx", "Federal Express"], "atlas": ["Atlas Air"],
         "cathay": ["Cathay Cargo", "Cathay Pacific Cargo", "Cathay Pacific"], "emirates": ["Emirates SkyCargo", "Emirates"],
         "qatar": ["Qatar Airways Cargo", "Qatar Airways"]}
MODELS = {"A306F": ["A300"], "B763F": ["767"], "B752F": ["757"], "MD11F": ["MD-11", "MD11"], "B748F": ["747-8", "747-867", "747-87"],
          "B77F": ["777F", "777-F", "777"], "B742F": ["747-2"], "B738F": ["737-8"], "B722F": ["727"]}
SKIP_WORDS = ("cockpit", "interior", "cabin", "engine", "seat", "logo", "model", "toy", "wheel", "gear", "crash", "wreck", "livery drawing")


def licence_rank(short):
    """0 best ... 3 acceptable; None when the licence doesn't allow PAC to reuse the photo."""
    s = (short or "").strip().lower()
    if not s:
        return None
    if "public domain" in s or s.startswith("pd") or "cc0" in s:
        return 0
    if re.match(r"^cc[ -]by[ -]\d", s):
        return 1
    if re.match(r"^cc[ -]by-sa[ -]\d", s) or s.startswith("cc by-sa"):
        return 2
    return None   # NC, ND, GFDL-only, fair use, unknown: not used


def _plain(htmltext):
    t = re.sub(r"<[^>]+>", "", htmltext or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()[:80]


class PartnerPhotos:
    def __init__(self, data_dir: Path, partners: dict, fleet: dict):
        self.dir = Path(data_dir) / "partner_photos"
        self.index_path = self.dir / "index.json"
        self.partners, self.fleet = partners, fleet
        self.lock = threading.Lock()
        self.busy = set()
        self.started_all = False
        self.cand_cache = {}        # "partner|type" -> (time, candidates) for the staff photo browser
        self.thumb_cache = {}       # small preview images for the staff photo browser

    # ------------------------------------------------------------ index
    def _load(self):
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, idx):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, indent=1), encoding="utf-8")
        tmp.replace(self.index_path)

    def combos(self):
        return [(k, t) for k, p in self.partners.items() for t in p.get("types", [])]

    # ------------------------------------------------------------ Commons
    def _api(self, **params):
        params.update(format="json", formatversion="2")
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    def _search(self, query, limit=20):
        j = self._api(action="query", list="search", srsearch=query + " filetype:bitmap", srnamespace=6, srlimit=limit)
        return [x["title"] for x in (j.get("query") or {}).get("search", [])]

    def _info(self, titles):
        out = []
        for i in range(0, len(titles), 20):
            j = self._api(action="query", prop="imageinfo", titles="|".join(titles[i:i + 20]),
                          iiprop="url|size|mime|extmetadata", iiurlwidth=WIDTH)
            small = {}
            try:   # a small preview of each photo for the staff browser
                js = self._api(action="query", prop="imageinfo", titles="|".join(titles[i:i + 20]), iiprop="url", iiurlwidth=480)
                small = {pg["title"]: ((pg.get("imageinfo") or [{}])[0]).get("thumburl") for pg in (js.get("query") or {}).get("pages", [])}
            except Exception:
                pass
            for pg in (j.get("query") or {}).get("pages", []):
                ii = (pg.get("imageinfo") or [None])[0]
                if not ii:
                    continue
                meta = ii.get("extmetadata") or {}
                lic = (meta.get("LicenseShortName") or {}).get("value", "")
                out.append({"file": pg["title"], "width": ii.get("width") or 0, "height": ii.get("height") or 1,
                            "mime": ii.get("mime", ""), "thumb": ii.get("thumburl") or ii.get("url"),
                            "preview": small.get(pg["title"]) or ii.get("thumburl") or ii.get("url"),
                            "page": ii.get("descriptionurl") or "", "licence": _plain(lic), "rank": licence_rank(_plain(lic)),
                            "licence_url": (meta.get("LicenseUrl") or {}).get("value", ""),
                            "artist": _plain((meta.get("Artist") or {}).get("value", "")) or "Unknown photographer"})
        return out

    def all_candidates(self, key, ac, fresh=False):
        """Every suitable photo for this partner and type, best first; remembered for an hour."""
        k = f"{key}|{ac}"
        hit = self.cand_cache.get(k)
        if hit and not fresh and time.time() - hit[0] < 3600:
            return hit[1]
        cands = self.candidates(key, ac)
        self.cand_cache[k] = (time.time(), cands)
        return cands

    def candidates(self, key, ac, skip=()):
        """Suitable photos for this partner and type, best first."""
        p = self.partners.get(key) or {}
        regs = ((p.get("registrations") or {}).get(ac) or [])[:10]
        names, models = NAMES.get(key, [p.get("name", key)]), MODELS.get(ac, [ac])
        titles, seen = [], set()

        def take(ts, test):
            for t in ts:
                low = t.lower()
                if t in seen or t in skip or any(w in low for w in SKIP_WORDS) or not test(low):
                    continue
                seen.add(t)
                titles.append(t)

        for reg in regs:                                   # by registration: right airline and right type for sure
            take(self._search(f'"{reg}"', 10), lambda low, r=reg.lower(): r in low or r.replace("-", "") in low)
            if len(titles) >= 12:
                break
        if len(titles) < 6:                                # then by airline and type
            for name in names[:2]:
                for model in models[:2]:
                    take(self._search(f'"{name}" {model}', 20),
                         lambda low: any(n.lower().split()[0] in low for n in names) and any(m.lower() in low for m in models))
        info = [c for c in self._info(titles[:40]) if c["rank"] is not None and c["mime"] in ("image/jpeg", "image/png", "image/webp")
                and c["width"] >= 1000 and 1.2 <= c["width"] / max(1, c["height"]) <= 2.6]
        return sorted(info, key=lambda c: (c["rank"], -min(c["width"], 4000)))

    def _download(self, key, ac, c):
        self.dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(c["thumb"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read(15_000_000)
        ext = {"image/png": ".png", "image/webp": ".webp"}.get(c["mime"], ".jpg")
        for old in self.dir.glob(f"{key}-{ac}.*"):
            if old.suffix != ".json":
                old.unlink(missing_ok=True)
        dest = self.dir / f"{key}-{ac}{ext}"
        dest.write_bytes(body)
        return dest.name

    # ------------------------------------------------------------ choose and keep
    def fetch(self, key, ac, pin_file=None, after=None):
        """Find (or pin) a photo for one combination and download it. Safe to call from a thread."""
        k = f"{key}|{ac}"
        with self.lock:
            if k in self.busy:
                return
            self.busy.add(k)
        try:
            idx = self._load()
            cur = idx.get(k) or {}
            if cur.get("off"):
                return
            if pin_file:
                pin_file = pin_file if pin_file.startswith("File:") else "File:" + pin_file
                got = [c for c in self._info([pin_file]) if c["rank"] is not None]
                if not got:
                    raise ValueError("That Commons file can't be used: it's missing or its licence doesn't allow reuse.")
                best = got[0]
            elif after is not None:
                # "Next photo": the one after the current photo, going back to the first after the last
                cands = self.all_candidates(key, ac)
                files = [c["file"] for c in cands]
                best = cands[(files.index(after) + 1) % len(cands)] if after in files else (cands[0] if cands else None)
            else:
                cands = self.all_candidates(key, ac)
                best = cands[0] if cands else None
            if not best:
                idx[k] = {**cur, "tried": time.time(), "local": None, "error": "No freely licensed photo found on Commons."}
            else:
                local = self._download(key, ac, best)
                idx[k] = {"file": best["file"], "page": best["page"], "artist": best["artist"], "licence": best["licence"],
                          "licence_url": best["licence_url"], "local": local, "fetched": time.time(), "tried": time.time(),
                          "skip": cur.get("skip") or [], "pinned": bool(pin_file)}
            self._save(idx)
        except Exception as e:  # network or Commons trouble: the PAC photo stays in use
            idx = self._load()
            idx[k] = {**(idx.get(k) or {}), "tried": time.time(), "error": str(e)[:200]}
            self._save(idx)
            if pin_file:
                raise
        finally:
            with self.lock:
                self.busy.discard(k)

    def ensure_all(self):
        """Once per process: fetch every combination that has never had a photo (or failed a while ago), one by one."""
        if self.started_all:
            return
        self.started_all = True

        def run():
            for key, ac in self.combos():
                e = self._load().get(f"{key}|{ac}") or {}
                if e.get("off") or (e.get("local") and (self.dir / e["local"]).is_file()):
                    continue
                if e.get("tried") and time.time() - e["tried"] < RETRY_S:
                    continue
                self.fetch(key, ac)
                time.sleep(2)               # be gentle with Commons
        threading.Thread(target=run, daemon=True).start()

    def public(self):
        """{"partner|type": {url, artist, licence, licence_url, page}} for the photos ready to use."""
        out = {}
        for k, e in self._load().items():
            if e.get("off") or not e.get("local") or not (self.dir / e["local"]).is_file():
                continue
            key, ac = k.split("|", 1)
            out[k] = {"url": f"/api/partner-photo/{key}/{ac}?v={int(e.get('fetched') or 0)}", "artist": e.get("artist"),
                      "licence": e.get("licence"), "licence_url": e.get("licence_url"), "page": e.get("page"), "file": e.get("file")}
        return out

    def staff_view(self):
        idx = self._load()
        return [{"partner": k, "partner_name": (self.partners.get(k) or {}).get("name", k), "aircraft": t,
                 "aircraft_name": (self.fleet.get(t) or {}).get("name", t), **{x: (idx.get(f"{k}|{t}") or {}).get(x) for x in
                 ("file", "page", "artist", "licence", "error", "off", "pinned", "fetched")},
                 "url": self.public().get(f"{k}|{t}", {}).get("url")} for k, t in self.combos()]

    def browse(self, key, ac):
        if (key, ac) not in self.combos():
            raise ValueError("That partner doesn't fly that type.")
        cur = (self._load().get(f"{key}|{ac}") or {}).get("file")
        return [{"file": c["file"], "artist": c["artist"], "licence": c["licence"], "page": c["page"], "current": c["file"] == cur,
                 "preview": "/api/staff/partner-photos/preview?u=" + urllib.parse.quote(c.get("preview") or c["thumb"], safe="")}
                for c in self.all_candidates(key, ac)]

    def preview(self, url):
        """Fetch a small Commons preview for the staff browser (only from Wikimedia's image server)."""
        u = urllib.parse.urlparse(url or "")
        if u.scheme != "https" or u.hostname != "upload.wikimedia.org":
            raise ValueError("Not a Commons image.")
        hit = self.thumb_cache.get(url)
        if hit:
            return hit
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            body, mime = r.read(3_000_000), r.headers.get_content_type()
        if len(self.thumb_cache) > 300:
            self.thumb_cache.clear()
        self.thumb_cache[url] = (body, mime)
        return body, mime

    def staff_action(self, key, ac, action, file=None):
        k = f"{key}|{ac}"
        if (key, ac) not in self.combos():
            raise ValueError("That partner doesn't fly that type.")
        idx = self._load()
        cur = idx.get(k) or {}
        if action == "next":           # the next photo in the list, looping back to the first
            idx[k] = {kk: v for kk, v in cur.items() if kk != "off"}
            self._save(idx)
            self.fetch(key, ac, after=cur.get("file") or "")
        elif action == "pac":          # use the PAC photo for this combination
            idx[k] = {**cur, "off": True}
            self._save(idx)
        elif action == "auto":         # back to automatic choice
            idx[k] = {}
            self._save(idx)
            self.fetch(key, ac)
        elif action == "pin" and file:  # a photo chosen in the browser (or a pasted Commons file name)
            idx[k] = {}
            self._save(idx)
            self.fetch(key, ac, pin_file=str(file).strip())
        else:
            raise ValueError("Choose next, pac, auto or pin (with a Commons file name).")
        return self.staff_view()


def register(app, data_dir, partners, fleet):
    pp = PartnerPhotos(data_dir, partners, fleet)

    @app.get("/api/partner-photos")
    def partner_photos_list():
        pp.ensure_all()
        return jsonify(pp.public())

    @app.get("/api/partner-photo/<key>/<ac>")
    def partner_photo_file(key, ac):
        e = pp._load().get(f"{key}|{ac}") or {}
        if e.get("off") or not e.get("local"):
            pp.ensure_all()
            abort(404)
        path = (pp.dir / e["local"]).resolve()
        if not path.is_relative_to(pp.dir.resolve()) or not path.is_file():
            abort(404)
        return send_file(path, max_age=7 * 86400, conditional=True)

    @app.get("/api/staff/partner-photos")
    def partner_photos_staff():
        pp.ensure_all()
        return jsonify(pp.staff_view())

    @app.get("/api/staff/partner-photos/<key>/<ac>/browse")
    def partner_photos_browse(key, ac):
        try:
            return jsonify(pp.browse(key, ac))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Wikimedia Commons couldn't be reached: {e}"}), 502

    @app.get("/api/staff/partner-photos/preview")
    def partner_photos_preview():
        try:
            body, mime = pp.preview(request.args.get("u", ""))
        except ValueError:
            abort(400)
        except Exception:
            abort(502)
        return Response(body, mimetype=mime, headers={"Cache-Control": "private, max-age=86400"})

    @app.post("/api/staff/partner-photos/<key>/<ac>")
    def partner_photos_staff_action(key, ac):
        b = request.json or {}
        try:
            return jsonify(pp.staff_action(key, ac, b.get("action"), b.get("file")))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Wikimedia Commons couldn't be reached: {e}"}), 502

    return pp
