# -*- coding: utf-8 -*-
"""
GST_INVOICE_PRO — Santosh Diesel स्टाईल पूर्ण Tax Invoice (Part No/
Amount-in-Words/Bank Details/Declaration/Signature सकट)

👉 COMPACT LAYOUT UPDATE (Om च्या सूचनेप्रमाणे):
   - Company GSTIN/PAN आता Address च्या खालीच एका ओळीत
   - Invoice No/Date/Payment Mode/Place of Supply आता Buyer च्या *शेजारी*
     (उजवीकडे) — त्यामुळे एक अख्खी रो वाचते, वरची जागा मोकळी होते
   - Item Grid चे row-padding/font कमी केले -> एका A4 पानात 12-13 items
     सहज बसतात
   - Bank Details + QR शेजारी-शेजारी, नीट align
   - Declaration खाली एक स्वतंत्र, पूर्ण-रुंदीची (horizontal) ओळ
   - Customer Seal & Signature / Authorised Signatory सगळ्यात शेवटी

वापर:
    from gst_invoice_pro import generate_full_gst_invoice
    generate_full_gst_invoice(
        buyer={"name": "...", "mobile": "...", "address": "...",
               "gstin": "", "state": "Maharashtra"},
        line_items=[
            {"description": "Wiper Blade 14\"", "hsn_sac": "85129000",
             "part_no": "3397011643",
             "qty": 20, "rate": 141.53, "discount_percent": 32, "gst_rate": 18},
            ...
        ],
        filepath="invoice.pdf",
        invoice_no="SDPC/26-27/901", mode_of_payment="Cash",
    )
"""
from datetime import datetime
import os
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    Image as RLImage
)
from db_company import get_company_settings
from gst_invoice_calc_engine import calculate_row  # 👈 केंद्रीय calc engine

# ==========================================================================
# SHOP DETAILS — इथे बदल कर (fallback, company_settings रिकामं असेल तर)
# ==========================================================================
SHOP_NAME = "Bhagwati Auto Electricals"
SHOP_ADDRESS = "Near Hotel Swagat, Shivrai Phata - Waluj"
SHOP_PHONE = "8010999654 / 9860010083"
SHOP_EMAIL = ""
SHOP_GSTIN = ""
SHOP_PAN = ""
SHOP_STATE = "Maharashtra"
SHOP_STATE_CODE = "27"
PAGE_SIZES = {"A4": A4, "A5": A5}
BANK_HOLDER = "Bhagwati Auto Electricals"
BANK_NAME = ""
BANK_ACC_NO = ""
BANK_IFSC = ""


def _get_company_data():
    """db_company मधून live Company Settings आणतो; काही रिकामं/नसेल तर
    वरचे hardcoded SHOP_* constants fallback म्हणून वापरतो."""
    row = get_company_settings()
    if not row:
        return {
            "name": SHOP_NAME, "address": SHOP_ADDRESS, "phone": SHOP_PHONE,
            "gstin": SHOP_GSTIN, "pan": SHOP_PAN, "email": SHOP_EMAIL, "state": SHOP_STATE,
            "state_code": SHOP_STATE_CODE, "logo_path": None,
            "bank_name": BANK_NAME, "account_number": BANK_ACC_NO,
            "ifsc": BANK_IFSC, "upi_id": "", "terms": "", "declaration": "",
        }
    return {
        "name": row["company_name"] or SHOP_NAME,
        "address": row["address"] or SHOP_ADDRESS,
        "phone": row["mobile"] or SHOP_PHONE,
        "gstin": row["gstin"] or SHOP_GSTIN,
        "pan": row["pan"] if "pan" in row.keys() and row["pan"] else SHOP_PAN,
        "email": row["email"] if "email" in row.keys() and row["email"] else SHOP_EMAIL,
        "state": row["state"] or SHOP_STATE,
        "state_code": row["state_code"] or SHOP_STATE_CODE,
        "logo_path": row["logo_path"] if "logo_path" in row.keys() else None,
        "bank_name": row["bank_name"] or BANK_NAME,
        "account_number": row["account_number"] or BANK_ACC_NO,
        "ifsc": row["ifsc"] or BANK_IFSC,
        "upi_id": row["upi_id"] if "upi_id" in row.keys() and row["upi_id"] else "",
        "terms": row["terms_conditions"] if "terms_conditions" in row.keys() and row["terms_conditions"] else "",
        "declaration": row["declaration"] if "declaration" in row.keys() and row["declaration"] else "",
    }


def _make_qr_image(data_text, size_mm=20):
    """UPI/Invoice माहितीचा QR कोड — qrcode लायब्ररी नसेल/चुकलं तरी None
    (PDF कधीही क्रॅश होणार नाही)."""
    try:
        import qrcode
        import io
        qr_img = qrcode.make(data_text)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        return RLImage(buf, width=size_mm * mm, height=size_mm * mm)
    except Exception:
        return None


# ==========================================================================
# AMOUNT IN WORDS — भारतीय पद्धत (Lakh/Crore) Rupees + Paise
# ==========================================================================
_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
         "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
         "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
         "Eighty", "Ninety"]


def _two_digit(n):
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digit(n):
    if n >= 100:
        return (_ONES[n // 100] + " Hundred" +
                (" " + _two_digit(n % 100) if n % 100 else "")).strip()
    return _two_digit(n)


def number_to_words(n):
    n = int(n)
    if n == 0:
        return "Zero"
    parts = []
    crore, n = divmod(n, 10000000)
    lakh, n = divmod(n, 100000)
    thousand, n = divmod(n, 1000)
    hundred = n
    if crore:
        parts.append(_three_digit(crore) + " Crore")
    if lakh:
        parts.append(_three_digit(lakh) + " Lakh")
    if thousand:
        parts.append(_three_digit(thousand) + " Thousand")
    if hundred:
        parts.append(_three_digit(hundred))
    return " ".join(parts)


def amount_in_words(amount):
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    words = f"INR {number_to_words(rupees)} Only"
    if paise:
        words = f"INR {number_to_words(rupees)} and {number_to_words(paise)} Paise Only"
    return words


def _rs(v):
    return f"{v:,.2f}"


# ==========================================================================
# MAIN — पूर्ण Tax Invoice PDF (COMPACT LAYOUT)
# ==========================================================================
def generate_full_gst_invoice(buyer, line_items, filepath, invoice_no=None,
                               invoice_date=None, mode_of_payment="Cash",
                               is_intra_state=True, notes="", page_size="A4",
                               paid_amt=None, due_amt=None):
    company = _get_company_data()
    """
    buyer      : {"name","mobile","address","gstin","state"}
    line_items : [{"description","hsn_sac","part_no","qty","rate",
                   "discount_percent","gst_rate", "mrp" (optional)}]
    paid_amt/due_amt : दिले तरच "Received / Previous Bal / Current Bal" रो
                        बिलावर दिसते (उधारी/Partial payment बिलांसाठी) —
                        नाही दिले तर जुनी बिलं आधीसारखीच दिसतील.

    टीप: "rate" हा प्रत्येक ओळीचा GST-सकट (MRP-style) युनिट-प्राईस मानला
    जातो. Rate/Amount कॉलम gst_invoice_calc_engine.calculate_row() याच
    केंद्रीय सूत्राने काढले जातात.
    """
    invoice_no = invoice_no or f"INV-{datetime.now().strftime('%y%m%d%H%M')}"
    invoice_date = invoice_date or datetime.now().strftime("%d-%b-%y")

    size = PAGE_SIZES.get((page_size or "A4").upper(), A4)
    margin = 6 * mm if size is A4 else 5 * mm
    doc = SimpleDocTemplate(filepath, pagesize=size, topMargin=margin,
                             bottomMargin=margin, leftMargin=margin, rightMargin=margin)
    styles = getSampleStyleSheet()

    # ---------------- Compact Styles ----------------
    title_s = ParagraphStyle("t", parent=styles["Title"], fontSize=14, leading=16,
                              textColor=colors.HexColor("#0b6e4f"), alignment=1,
                              spaceBefore=0, spaceAfter=0)
    lbl = ParagraphStyle("l", parent=styles["Normal"], fontSize=8, leading=10)
    lbl_c = ParagraphStyle("lc", parent=lbl, alignment=1)
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.grey)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7, leading=9)

    title_row = Table(
        [[Paragraph("", small),
          Paragraph("Tax Invoice", ParagraphStyle("h", parent=styles["Normal"], fontSize=12, alignment=1)),
          Paragraph("ORIGINAL FOR RECIPIENT", ParagraphStyle(
              "orig", parent=small, fontSize=6, alignment=2, textColor=colors.HexColor("#555555")))]],
        colWidths=["25%", "50%", "25%"],
    )
    title_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story = [
        title_row,
        HRFlowable(width="100%", color=colors.HexColor("#00aa77"), thickness=1.2),
        Spacer(1, 1),
    ]

    # ---------------- Company Header (Logo + Name + Address + GSTIN/PAN one line) ----------------
    if company["logo_path"] and os.path.exists(company["logo_path"]):
        try:
            story.append(RLImage(company["logo_path"], width=16 * mm, height=16 * mm))
        except Exception:
            pass

    gstin_pan_line = ""
    if company["gstin"]:
        gstin_pan_line += f"GSTIN: {company['gstin']}"
    if company.get("pan"):
        gstin_pan_line += (" | " if gstin_pan_line else "") + f"PAN: {company['pan']}"
    if company.get("email"):
        gstin_pan_line += (" | " if gstin_pan_line else "") + f"Email: {company['email']}"

    story += [
        Paragraph(company["name"], title_s),
        Paragraph(company["address"] + f"  |  Ph: {company['phone']}",
                   ParagraphStyle("addr", parent=lbl_c, spaceBefore=1)),
    ]
    if gstin_pan_line:
        # 👈 आता Regular (bold नाही), address एवढाच font size
        story.append(Paragraph(gstin_pan_line, ParagraphStyle(
            "gp", parent=lbl_c, fontSize=7, spaceAfter=1)))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#00aa77"), thickness=1))
    story.append(Spacer(1, 2))

    # ---------------- Buyer (left) + Invoice Meta (right) — एकाच रांगेत ----------------
    # 👈 सूट-सुटीत (जास्त leading) + नाव वेगळ्या ओळीत + सगळी माहिती
    buyer_lbl = ParagraphStyle("bl", parent=styles["Normal"], fontSize=8, leading=13)
    b_lines = ["<b>Buyer (Bill to):</b>", f"<b>{buyer.get('name','') or '-'}</b>"]
    if buyer.get("mobile"):
        b_lines.append(f"Mo: {buyer['mobile']}")
    if buyer.get("gstin"):
        b_lines.append(f"GSTIN: {buyer['gstin']}")
    if buyer.get("address"):
        b_lines.append(buyer["address"])
    if buyer.get("pan"):
        b_lines.append(f"PAN: {buyer['pan']}")
    if buyer.get("email"):
        b_lines.append(f"Email: {buyer['email']}")
    buyer_para = Paragraph("<br/>".join(b_lines), buyer_lbl)

    meta_lbl = ParagraphStyle("ml", parent=styles["Normal"], fontSize=8, leading=13, alignment=2)
    meta_lines = [
        f"Invoice No: {invoice_no}",
        f"Date: {invoice_date}",
        f"Mode of Payment: {mode_of_payment}",
        f"Place of Supply: {buyer.get('state', company['state'])}",
    ]
    meta_para = Paragraph("<br/>".join(meta_lines), meta_lbl)

    top_tbl = Table([[buyer_para, meta_para]], colWidths=["58%", "42%"])
    top_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(top_tbl)
    if notes:
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"<b>{notes}</b>", small))
    story.append(Spacer(1, 5))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=0.8))
    story.append(Spacer(1, 5))

    # ---------------- Items table — कॉम्पॅक्ट (12-13 items/page साठी) ----------------
    header = ["Sr", "Part No", "Description", "HSN", "GST%", "Rate", "Qty", "Dis%", "Amount"]
    col_w = ["5%", "11%", "27%", "10%", "8%", "10%", "7%", "7%", "15%"]
    rows = [header]

    tax_groups = {}
    taxable_total = 0.0

    for idx, it in enumerate(line_items, start=1):
        qty = float(it.get("qty", 1) or 1)
        rate = float(it.get("rate", 0) or 0)
        disc = float(it.get("discount_percent", 0) or 0)
        gst_rate = float(it.get("gst_rate", 18) or 0)
        unit_mrp = float(it.get("mrp") or rate)

        calc = calculate_row(
            description=it.get("description", ""), mrp=unit_mrp, qty=qty,
            disc_percent=disc, gst_rate=gst_rate,
            hsn_sac=it.get("hsn_sac", ""), part_no=it.get("part_no", "-"),
        )
        ex_gst_rate = calc["rate"]
        taxable = calc["amount"]
        tax = taxable * gst_rate / 100

        taxable_total += taxable
        grp = tax_groups.setdefault(gst_rate, {"taxable": 0.0, "tax": 0.0})
        grp["taxable"] += taxable
        grp["tax"] += tax

        rows.append([
            str(idx), it.get("part_no", "") or "-",
            Paragraph(it.get("description", ""), cell),
            it.get("hsn_sac", "") or "-", f"{gst_rate:.0f}%",
            f"{ex_gst_rate:,.2f}", f"{qty:.0f}", f"{disc:.0f}%",
            f"{taxable:,.2f}",
        ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00ffaa")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6))

    # ---------------- Totals ----------------
    cgst_total = sgst_total = igst_total = 0.0
    for gr in sorted(tax_groups):
        g = tax_groups[gr]
        if is_intra_state:
            half = g["tax"] / 2
            cgst_total += half
            sgst_total += half
        else:
            igst_total += g["tax"]

    tax_amount = cgst_total + sgst_total + igst_total
    raw_total = taxable_total + tax_amount
    rounded_total = round(raw_total)

    story.append(HRFlowable(width="32%", color=colors.HexColor("#999999"), thickness=0.8, hAlign="RIGHT"))
    story.append(Spacer(1, 3))

    totals_rows = [["Sub Total", f"{taxable_total:,.2f}"]]
    if is_intra_state:
        totals_rows.append(["C GST", f"{cgst_total:,.2f}"])
        totals_rows.append(["S GST", f"{sgst_total:,.2f}"])
    else:
        totals_rows.append(["IGST", f"{igst_total:,.2f}"])
    totals_rows.append(["Total Amount (Incl. GST)", f"{rounded_total:,.2f}"])

    totals_tbl = Table(totals_rows, colWidths=["70%", "30%"])
    totals_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),   # 👈 Label आता value च्या शेजारी (उजवीकडे)
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 9),
        ("FONTSIZE", (0, 0), (-1, -2), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (0, -1), 4),
    ]))
    # 👈 आणखी उजवीकडे — value शी अगदी जवळ
    totals_wrapper = Table([[Paragraph("", small), totals_tbl]], colWidths=["60%", "40%"])
    totals_wrapper.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_wrapper)

    # 👈 Received/Previous/Current Balance — फक्त paid_amt दिलं असेल तरच
    # (Vyapar-style उधारी/Partial-payment ट्रॅकिंग; जुने calls अबाधित)
    if paid_amt is not None:
        due = due_amt if due_amt is not None else max(rounded_total - paid_amt, 0)
        bal_rows = [
            ["Received Amount", f"{paid_amt:,.2f}"],
            ["Current Balance (Due)", f"{due:,.2f}"],
        ]
        bal_tbl = Table(bal_rows, colWidths=["70%", "30%"])
        bal_tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#cc4400") if due > 0 else colors.HexColor("#0b6e4f")),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (0, -1), 4),
        ]))
        bal_wrapper = Table([[Paragraph("", small), bal_tbl]], colWidths=["60%", "40%"])
        bal_wrapper.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(bal_wrapper)

    story.append(Paragraph("E. & O.E", ParagraphStyle(
        "eoe", parent=small, fontSize=6, alignment=2)))
    story.append(Spacer(1, 3))

    story.append(Table(
        [[Paragraph(
            f"<b>Amount Chargeable (in words):</b> <b>{amount_in_words(rounded_total)}</b>",
            ParagraphStyle("aiw", parent=small, fontSize=8, textColor=colors.black))]],
        colWidths=["100%"],
        style=TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#999999")),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]),
    ))
    story.append(Spacer(1, 4))

    # ---------------- Bank Details + QR — दोन्ही पूर्ण उजवीकडे ----------------
    bank_para = Paragraph(
        f"<b>Bank Details</b><br/>A/c Holder: {company['name']}<br/>"
        f"Bank: {company['bank_name'] or '-'}<br/>A/c No: {company['account_number'] or '-'}<br/>"
        f"IFSC: {company['ifsc'] or '-'}" + (f"<br/>UPI: {company['upi_id']}" if company["upi_id"] else ""),
        small)

    qr_data = (f"upi://pay?pa={company['upi_id']}&pn={company['name']}&am={rounded_total}&cu=INR"
               if company["upi_id"] else invoice_no)
    qr_img = _make_qr_image(qr_data)
    qr_cell = qr_img if qr_img else Paragraph("", small)

    bank_qr_tbl = Table([[Paragraph("", small), bank_para, qr_cell]], colWidths=["55%", "22%", "23%"])
    bank_qr_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (2, 0), (2, 0), 2),
        ("RIGHTPADDING", (1, 0), (1, 0), 2),
    ]))
    story.append(bank_qr_tbl)
    story.append(Spacer(1, 4))

    # 👈 Bank Details च्या खाली एक horizontal line, त्याखाली Declaration+Signature
    story.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=0.8))
    story.append(Spacer(1, 4))

    declaration_text = company["declaration"] or (
        "We declare that this invoice shows the actual price of the goods described "
        "and that all particulars are true and correct."
    )
    story.append(Paragraph(f"<b>Declaration:</b> {declaration_text}", small))
    story.append(Spacer(1, 6))

    # ---------------- Signature — सगळ्यात शेवटी ----------------
    story.append(Table(
        [["Customer's Seal and Signature", f"for {company['name']}\n\n\nAuthorised Signatory"]],
        colWidths=["50%", "50%"],
        style=TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ]),
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph("This is a computer-generated invoice.", small))

    def _draw_page_border(canvas, doc_obj):
        """संपूर्ण पानाला एक सुबक बॉर्डर काढतो (मार्जिनच्या अगदी आतून)."""
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#999999"))
        canvas.setLineWidth(0.8)
        border_margin = margin - 3 * mm if margin > 3 * mm else margin
        canvas.rect(
            border_margin, border_margin,
            doc_obj.pagesize[0] - 2 * border_margin,
            doc_obj.pagesize[1] - 2 * border_margin,
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_draw_page_border, onLaterPages=_draw_page_border)
    return filepath


if __name__ == "__main__":
    demo_items = [
        {"description": 'Wiper Blade 14"', "hsn_sac": "85129000", "part_no": "3397011643",
         "qty": 20, "rate": 141.53, "discount_percent": 32, "gst_rate": 18},
        {"description": 'Wiper Blade 16"', "hsn_sac": "85129000", "part_no": "3397011644",
         "qty": 20, "rate": 154.24, "discount_percent": 32, "gst_rate": 18},
    ]
    generate_full_gst_invoice(
        buyer={"name": "Bhagwati Auto Electrical Waluj", "mobile": "8010999654",
               "address": "Waluj", "gstin": "", "state": "Maharashtra"},
        line_items=demo_items, filepath="/tmp/demo_invoice.pdf",
        invoice_no="SDPC/26-27/901", mode_of_payment="Cash",
    )
    print("done")