"""Build the fictional PAC Academy cargo paperwork PDFs.

Requires reportlab. The generated PDFs are committed so deployment has no
document-generation dependency.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

OUT = Path(__file__).resolve().parent.parent / "static" / "academy"
RED = colors.HexColor("#c80000")
INK = colors.HexColor("#202329")
MUTED = colors.HexColor("#666d76")
LINE = colors.HexColor("#ced2d7")
PALE = colors.HexColor("#f4f5f6")

styles = {
    "brand": ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=32, leading=32, textColor=RED),
    "brand_sub": ParagraphStyle("brand_sub", fontName="Helvetica", fontSize=8, leading=10, tracking=1.2, textColor=INK),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=23, alignment=TA_RIGHT, textColor=INK),
    "eyebrow": ParagraphStyle("eyebrow", fontName="Helvetica", fontSize=8, leading=10, alignment=TA_RIGHT, textColor=MUTED),
    "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=MUTED),
    "value": ParagraphStyle("value", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=INK),
    "route": ParagraphStyle("route", fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=INK),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=15, textColor=INK),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=9, leading=13, textColor=MUTED),
    "table_head": ParagraphStyle("table_head", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=colors.white),
    "table": ParagraphStyle("table", fontName="Helvetica", fontSize=9, leading=12, textColor=INK),
    "table_bold": ParagraphStyle("table_bold", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=INK),
}


def p(text, style="body"):
    return Paragraph(text, styles[style])


def box(label, value, detail=""):
    return [p(label.upper(), "label"), Spacer(1, 3), p(value, "value"),
            *([Spacer(1, 2), p(detail, "small")] if detail else [])]


def panel(rows, widths):
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), .7, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table


def data_table(headings, rows, widths):
    table = Table([[p(h.upper(), "table_head") for h in headings]] +
                  [[p(str(cell), "table_bold" if row_index == len(rows)-1 else "table") for cell in row]
                   for row_index, row in enumerate(rows)], colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BACKGROUND", (0, -1), (-1, -1), PALE),
        ("GRID", (0, 1), (-1, -1), .5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def header(title, identifier):
    left = [p("PAC", "brand"), p("PAGANI AIR CARGO", "brand_sub")]
    right = [p("ACADEMY / CARGO OPERATIONS", "eyebrow"), p(title, "title")]
    table = Table([[left, right]], colWidths=[90*mm, 90*mm])
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 3, RED),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    bar = Table([[p(identifier, "table_head"), p("SIMULATOR TRAINING EXAMPLE", "table_head")]],
                colWidths=[90*mm, 90*mm])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [table, Spacer(1, 16), bar, Spacer(1, 14)]


def note(title, body):
    t = Table([[[p(title, "table_bold"), Spacer(1, 5), p(body)]]], colWidths=[180*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, RED),
        ("LEFTPADDING", (0, 0), (-1, -1), 13),
        ("RIGHTPADDING", (0, 0), (-1, -1), 13),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(15*mm, 19*mm, 195*mm, 19*mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(15*mm, 14*mm, "PAC Academy / fictional cargo paperwork")
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(RED)
    canvas.drawRightString(195*mm, 14*mm, "NOT VALID FOR REAL SHIPMENT")
    canvas.restoreState()


def build(name, story):
    path = OUT / name
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15*mm,
                            rightMargin=15*mm, topMargin=15*mm, bottomMargin=24*mm)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {path} ({path.stat().st_size} bytes)")


def main():
    awb = header("Air waybill", "AWB 901-10000123")
    awb += [panel([[box("Shipper", "Riverbend Floral Co.", "Cincinnati, Ohio"),
                   box("Consignee", "South Coast Wholesale", "Miami, Florida")]], [90*mm, 90*mm]),
            Spacer(1, 10),
            panel([[box("Airport of departure to destination", "KCVG  >  KMIA",
                        "Cincinnati / Northern Kentucky to Miami"),
                    box("Flight", "PAC4821", "Training flight / 19 Nov 2026")]], [105*mm, 75*mm]),
            Spacer(1, 14),
            data_table(["Pieces", "Gross weight", "Chargeable weight", "Rate", "Freight charge"],
                       [["10 cartons", "1,200 kg", "1,440 kg", "$2.50 / kg", "$3,600.00"]],
                       [29*mm, 34*mm, 42*mm, 32*mm, 43*mm]),
            Spacer(1, 14),
            note("SPECIAL HANDLING / PER", "Fresh flowers. Keep chilled at 2-8 C. Confirm handling with dispatch and the simulated cargo desk before loading."),
            Spacer(1, 14),
            panel([[box("Weight used for aircraft loading", "1,200 kg gross"),
                    box("Weight used for billing", "1,440 kg chargeable")]], [90*mm, 90*mm])]
    build("pac-sample-awb.pdf", awb)

    manifest = header("Cargo manifest", "FLIGHT PAC4821 / 19 NOV 2026")
    manifest += [panel([[box("Origin to destination", "KCVG  >  KMIA"),
                        box("Shipment count", "1 shipment / 10 cartons", "1,200 kg total gross weight")]], [90*mm, 90*mm]),
                 Spacer(1, 14),
                 data_table(["Air waybill", "Goods", "Pieces", "Gross weight", "Position", "Handling"],
                            [["901-10000123", "Fresh flowers", "10 cartons", "1,200 kg", "M01", "PER / 2-8 C"],
                             ["TOTAL ON FLIGHT", "1 shipment", "10 cartons", "1,200 kg", "", ""]],
                            [36*mm, 31*mm, 27*mm, 31*mm, 25*mm, 30*mm]),
                 Spacer(1, 14),
                 note("DISPATCH CROSS-CHECK", "Match the air waybill number, KCVG to KMIA route, 10 cartons, 1,200 kg gross weight and PER handling to the waybill. The 1,440 kg chargeable weight is for billing, not aircraft loading."),
                 Spacer(1, 14),
                 panel([[box("Prepared for", "PAC Academy", "Cargo paperwork lesson"),
                         box("Load position", "M01", "Illustrative assignment only")]], [90*mm, 90*mm])]
    build("pac-sample-manifest.pdf", manifest)


if __name__ == "__main__":
    main()
