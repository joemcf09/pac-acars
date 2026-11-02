"""Builds data/airports.json from the OurAirports open data set.
Usage: python tools/build_airports.py airports.csv runways.csv"""
import csv, json, re, sys
from pathlib import Path

airports_csv, runways_csv = sys.argv[1], sys.argv[2]
PAVED = re.compile(r"ASP|CON|PEM|BIT|TAR|PAV|CEM", re.I)
rwy = {}
for r in csv.DictReader(open(runways_csv, encoding="utf-8")):
    if r["closed"] == "1":
        continue
    try:
        L = int(float(r["length_ft"] or 0))
    except ValueError:
        continue
    paved = bool(PAVED.search(r["surface"] or ""))
    cur = rwy.get(r["airport_ref"], (0, False))
    if L > cur[0]:
        rwy[r["airport_ref"]] = (L, paved)

out = []
for a in csv.DictReader(open(airports_csv, encoding="utf-8")):
    icao = (a["icao_code"] or a["gps_code"] or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{4}", icao) or a["type"] in ("closed", "heliport", "seaplane_base", "balloonport"):
        continue
    L, paved = rwy.get(a["id"], (0, False))
    big = a["type"] in ("large_airport", "medium_airport")
    if not big and not (paved and L >= 5000):
        continue
    if L and L < 4000:
        continue
    out.append([icao, a["iata_code"] or "", a["name"], a["municipality"] or "", a["iso_country"], a["continent"],
                round(float(a["latitude_deg"]), 4), round(float(a["longitude_deg"]), 4),
                int(float(a["elevation_ft"] or 0)), L, {"large_airport": "L", "medium_airport": "M"}.get(a["type"], "S")])
# de-duplicate ICAO, prefer larger type
seen = {}
for row in out:
    k = row[0]
    if k not in seen or "LMS".index(row[10]) < "LMS".index(seen[k][10]):
        seen[k] = row
rows = sorted(seen.values(), key=lambda r: r[0])

# runway ends with threshold coordinates, for touchdown analysis
import math
ref_to_icao = {}
for a in csv.DictReader(open(airports_csv, encoding="utf-8")):
    icao = (a["icao_code"] or a["gps_code"] or "").strip().upper()
    if icao in seen:
        ref_to_icao[a["id"]] = icao
def brg(la1, lo1, la2, lo2):
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    return (math.degrees(math.atan2(math.sin(dl) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) + 360) % 360
rw = {}
for r in csv.DictReader(open(runways_csv, encoding="utf-8")):
    icao = ref_to_icao.get(r["airport_ref"])
    if not icao or r["closed"] == "1":
        continue
    try:
        la1, lo1, la2, lo2 = (float(r[k]) for k in ("le_latitude_deg", "le_longitude_deg", "he_latitude_deg", "he_longitude_deg"))
    except ValueError:
        continue
    f = lambda k: int(float(r[k])) if r[k] else 0
    rw.setdefault(icao, []).append([r["le_ident"], round(la1, 6), round(lo1, 6), round(brg(la1, lo1, la2, lo2), 1), f("le_displaced_threshold_ft"),
                                    r["he_ident"], round(la2, 6), round(lo2, 6), round(brg(la2, lo2, la1, lo1), 1), f("he_displaced_threshold_ft"),
                                    f("length_ft"), f("width_ft")])
rdest = Path(__file__).resolve().parent.parent / "data" / "runways.json"
rdest.write_text(json.dumps(rw, separators=(",", ":")), encoding="utf-8")
print(sum(len(v) for v in rw.values()), "runways ->", rdest, rdest.stat().st_size // 1024, "KB")
dest = Path(__file__).resolve().parent.parent / "data" / "airports.json"
dest.write_text(json.dumps({"fields": ["icao", "iata", "name", "city", "country", "continent", "lat", "lon", "elev_ft", "rwy_ft", "size"], "rows": rows}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
print(len(rows), "airports ->", dest, dest.stat().st_size // 1024, "KB")
