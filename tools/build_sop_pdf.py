"""Builds static/sop/PAC-SOP.pdf from tools/sop/pac-sop.html.

The numbers in the document (start sequences, start-time targets, taxi allowances, time windows) are filled in from
flight_timing.py, so the PDF can never disagree with what the website checks. Run this after changing either file:

    python tools/build_sop_pdf.py

It needs Playwright with Chromium (pip install playwright, then: playwright install chromium) and is only for whoever
maintains the document. The PDF itself is committed, so deploying never needs a browser."""
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import flight_timing as ft  # noqa: E402

SRC = ROOT / "tools" / "sop" / "pac-sop.html"
OUT = ROOT / "static" / "sop" / "PAC-SOP.pdf"
LOGO = ROOT / "static" / "pac-wordmark-red.png"


def _seq(count):
    listed = ft.STANDARD_SEQUENCES.get(count)
    return " or ".join(" &rarr; ".join(map(str, s)) for s in listed) if listed else "None defined yet"


def _span(count):
    s = ft.ENGINE_START_MAX_SPAN_S[count]
    return f"{s // 60} minutes after the first start"


def fill(html: str) -> str:
    logo = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()
    values = {"LOGO": logo, "SEQ_2": _seq(2), "SEQ_4": _seq(4), "SPAN_2": _span(2), "SPAN_3": _span(3), "SPAN_4": _span(4),
              "TAXI_L": "%d to %d" % ft.TAXI_ALLOWANCE_MIN["L"], "TAXI_M": "%d to %d" % ft.TAXI_ALLOWANCE_MIN["M"],
              "TAXI_S": "%d to %d" % ft.TAXI_ALLOWANCE_MIN["S"],
              "GRACE_DEP": str(ft.DEPARTURE_GRACE_MIN), "GRACE_ARR": str(ft.ARRIVAL_GRACE_MIN)}
    for k, v in values.items():
        html = html.replace("{{%s}}" % k, v)
    left = [w for w in ("{{",) if w in html]
    if left:
        raise SystemExit("unfilled placeholder left in the document")
    return html


def main():
    from playwright.sync_api import sync_playwright
    html = fill(SRC.read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.pdf(path=str(OUT), format="Letter", print_background=True, prefer_css_page_size=True)
        browser.close()
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
