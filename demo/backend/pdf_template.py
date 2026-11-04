"""Generates the demo proposal PDF (version 0) with three empty signature fields."""

from io import BytesIO

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

# Signature slots on page 2 (the "Noting and Signatures" sheet).
# box = (x1, y1, x2, y2) in PDF points, origin bottom-left.
SLOTS = [
    {"no": 1, "role": "Recommender", "field": "SIG_1_RECOMMENDER",
     "default_action": "Recommended", "box": (MARGIN, 520, PAGE_W - MARGIN, 690)},
    {"no": 2, "role": "Sanctioning authority", "field": "SIG_2_SANCTION",
     "default_action": "Sanctioned", "box": (MARGIN, 300, PAGE_W - MARGIN, 470)},
    {"no": 3, "role": "Control", "field": "SIG_3_CONTROL",
     "default_action": "Controlled", "box": (MARGIN, 80, PAGE_W - MARGIN, 250)},
]

DOC_TITLE = "Demo proposal: purchase of 2 laptops for Branch 0101"


def _proposal_page(c: canvas.Canvas, ref: str) -> None:
    y = PAGE_H - MARGIN
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, y, "eOffice - Demo Proposal")
    y -= 22
    c.setFont("Helvetica", 10)
    c.drawString(MARGIN, y, f"Reference: {ref}")
    y -= 30

    rows = [
        ("Subject", "Purchase of 2 laptops for Branch 0101"),
        ("Initiated by", "Desk Officer, Branch 0101"),
        ("Expense head", "IT Hardware (Capital)"),
        ("Amount", "Rs. 1,40,000 (Rupees one lakh forty thousand only)"),
        ("Path", "Recommender -> Sanctioning authority -> Control"),
    ]
    for label, value in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN + 90, y, value)
        y -= 16

    y -= 14
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Proposal")
    y -= 16
    c.setFont("Helvetica", 10)
    body = [
        "The two desktop computers at the cash counter are more than seven years old and",
        "fail frequently. It is proposed to purchase two laptops through the approved vendor",
        "at the rate contract price of Rs. 70,000 each, inclusive of GST and three years",
        "on-site warranty.",
        "",
        "This document is a DEMO used only to test incremental digital signing with",
        "HYP2003 DSC tokens. Each signer's action and remarks are printed inside their",
        "signature box on page 2 and are covered by their digital signature.",
    ]
    for line in body:
        c.drawString(MARGIN, y, line)
        y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(MARGIN, MARGIN / 2, "eOffice demo - page 1 of 2")


def _noting_page(c: canvas.Canvas) -> None:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, PAGE_H - MARGIN, "Noting and Signatures")
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN, PAGE_H - MARGIN - 16,
                 "Each box is filled by the digital signature of the person acting at that stage.")
    for slot in SLOTS:
        x1, y1, x2, y2 = slot["box"]
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x1, y2 + 6, f"{slot['no']}. {slot['role']}")
        c.setDash(3, 3)
        c.rect(x1, y1, x2 - x1, y2 - y1)
        c.setDash()
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(MARGIN, MARGIN / 2, "eOffice demo - page 2 of 2")


def build_version0(ref: str) -> bytes:
    """Returns the unsigned version 0 PDF with three empty signature fields."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(DOC_TITLE)
    c.setAuthor("eOffice demo")
    _proposal_page(c, ref)
    c.showPage()
    _noting_page(c)
    c.showPage()
    c.save()

    # Add the empty signature fields before anyone signs, so later
    # signatures only fill existing fields (keeps earlier signatures valid).
    w = IncrementalPdfFileWriter(BytesIO(buf.getvalue()))
    for slot in SLOTS:
        x1, y1, x2, y2 = slot["box"]
        append_signature_field(
            w, SigFieldSpec(sig_field_name=slot["field"], on_page=1,
                            box=(int(x1) + 2, int(y1) + 2, int(x2) - 2, int(y2) - 2)))
    out = BytesIO()
    w.write(out)
    return out.getvalue()
