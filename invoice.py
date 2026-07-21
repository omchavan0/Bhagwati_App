"""कस्टमरला देण्यासाठी सुबक PDF बिल/इनव्हॉइस बनवणारा मॉड्यूल.

आता 3 पर्याय एकत्र आहेत:
  1. Page Size    -> "A5" (झेरॉक्सचा अर्धा भाग, डिफॉल्ट) किंवा "A4" (फुल पेज)
  2. GST / Non-GST -> is_gst=True दिलं तर टॅक्स इनव्हॉइस (CGST+SGST किंवा IGST
     सह), नाहीतर साधं बिल (जुन्यासारखं, टॅक्स ब्रेकअप शिवाय)
  3. Multi-line items -> Parts Used मधले वेगवेगळे parts + Labour, प्रत्येक
     ओळ वेगळी दाखवली जाते (आधी फक्त एकच "Description" ओळ होती)

============================================================================
GST गणिताची पद्धत (महत्त्वाचं — तुझ्या पुरवठादाराच्या बिलाशी जुळवून घेतलंय):
============================================================================
  Taxable Value = Rate × Qty − Discount
  GST = Taxable Value × GST% (उदा. 18% = 9% CGST + 9% SGST जर ग्राहक
        त्याच राज्यात (Maharashtra) असेल; नाहीतर पूर्ण 18% IGST)

  किंमत आधीच "अंतिम/ग्राहकाला सांगितलेली" रक्कम धरली आहे (price_includes_gst=True
  डिफॉल्ट) — म्हणजे GST बिल दिलं काय, Non-GST दिलं काय, ग्राहकाला भरायची रक्कम
  (Total) सेम राहते; फक्त GST बिलात त्याच रकमेतून Taxable Value + CGST/SGST
  उलट (back-calculate) करून दाखवले जातात. जर उलट हवं (GST वेगळा वर लावून
  किंमत वाढवायची) तर generate_invoice() ला price_includes_gst=False द्यायचं.

टीप: PDF मध्ये फक्त इंग्रजी अक्षरं आणि 'Rs.' वापरलंय (₹ चिन्ह आणि देवनागरी अक्षरं
डिफॉल्ट PDF फॉन्टमध्ये नीट दिसत नाहीत).
"""

from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from datetime import datetime

# ==========================================================================
# SHOP DETAILS — इथे बदल केला की सगळ्या बिलांवर आपोआप दिसेल
# ==========================================================================
SHOP_NAME = "Bhagwati Auto Electricals - Waluj"
SHOP_ADDRESS = "Near Hotel Swagat, Shivrai Phata, Waluj - Chh. Sambhajinagar"
SHOP_PHONE1 = "8010999654"
SHOP_PHONE2 = "9860010083"
SHOP_VEHICLE_TAG = "BS4 & BS6"
SHOP_SERVICES = (
    "Wiring | Scanning | A/C Gas | Key Programming | ECM & Electronic Parts Repairing | "
    "Alternator & Starter | Rewinding | Wheel Alignment | Inverter & Battery | "
    "Car Accessories & Spare Parts"
)

SHOP_GSTIN = ""
SHOP_STATE = "Maharashtra"
SHOP_STATE_CODE = "27"
DEFAULT_SERVICE_HSN = "998714"

BANK_HOLDER = "Bhagwati Auto Electricals"
BANK_NAME = ""
BANK_ACC_NO = ""
BANK_IFSC = ""

PAGE_SIZES = {"A4": A4, "A5": A5}


def _rs(amount):
    return f"Rs. {amount:,.2f}"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
         "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
         "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digit(n):
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digit(n):
    if n >= 100:
        return (_ONES[n // 100] + " Hundred" + (" " + _two_digit(n % 100) if n % 100 else "")).strip()
    return _two_digit(n)


def _number_to_words(n):
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
    if paise:
        return f"INR {_number_to_words(rupees)} and {_number_to_words(paise)} Paise Only"
    return f"INR {_number_to_words(rupees)} Only"



def _default_line_items(record):
    """line_items दिले नसतील तर जुन्या पद्धतीनुसार (record.notes + record.total_amt)
    एकच ओळ बनवतो — जुने सगळे calls (फक्त record, filepath देणारे) आधीसारखेच चालतील."""
    return [{
        "description": record["notes"] or "Service / Work",
        "hsn_sac": DEFAULT_SERVICE_HSN,
        "qty": 1,
        "rate": record["total_amt"] or 0,
        "discount_percent": 0,
        "gst_rate": 18,
    }]


def generate_invoice(record, filepath, page_size="A5", is_gst=False,
                      customer_gstin="", customer_state=None,
                      line_items=None, price_includes_gst=True):
    """एका उधारी/बिल रेकॉर्डवरून (sqlite3.Row) सुबक PDF बिल बनवतं.

    record मध्ये असायला हवं: name, mobile, vehicle, vehicle_no, address,
    tx_date, due_date, total_amt, paid_amt, due_amt, notes, type, id.

    page_size          : "A5" (डिफॉल्ट) किंवा "A4"
    is_gst             : True -> GST Tax Invoice, False -> साधं बिल
    customer_gstin     : ग्राहकाचा GSTIN असल्यास (B2B बिलासाठी, ऐच्छिक)
    customer_state     : ग्राहकाचं राज्य (डिफॉल्ट शॉपच्याच राज्याप्रमाणे, म्हणजे
                          CGST+SGST लागेल; वेगळं राज्य दिलं तर आपोआप IGST)
    line_items          : [{"description","hsn_sac","qty","rate",
                            "discount_percent","gst_rate"}, ...] — नसेल तर
                          record वरून एकच ओळ आपोआप बनते (जुनी पद्धत, सुसंगत)
    price_includes_gst : True (डिफॉल्ट) -> दिलेली rate आधीच अंतिम रक्कम आहे,
                          GST त्यातूनच मागच्या बाजूने काढला जातो (Total बदलत
                          नाही). False -> rate ही GST आधीची (taxable) रक्कम
                          समजून त्यावर GST वर लावला जातो (Total वाढतो).
    """
    page_size = (page_size or "A5").upper()
    size = PAGE_SIZES.get(page_size, A5)
    is_a4 = page_size == "A4"
    customer_state = (customer_state or SHOP_STATE).strip()
    is_intra_state = customer_state.strip().lower() == SHOP_STATE.strip().lower()

    items = line_items if line_items else _default_line_items(record)

    margin = 16 * mm if is_a4 else 12 * mm
    doc = SimpleDocTemplate(
        filepath, pagesize=size,
        topMargin=margin, bottomMargin=margin,
        leftMargin=margin, rightMargin=margin,
    )
    styles = getSampleStyleSheet()

    title_size = 20 if is_a4 else 16
    tagline_size = 10 if is_a4 else 8.5
    services_size = 9 if is_a4 else 7.5
    label_size = 11 if is_a4 else 9.5
    small_size = 9 if is_a4 else 7.5
    cell_size = 9 if is_a4 else 7.5

    title_style = ParagraphStyle(
        "ShopTitle", parent=styles["Title"], fontSize=title_size,
        textColor=colors.HexColor("#0b6e4f"), spaceAfter=2, alignment=1,
    )
    address_style = ParagraphStyle(
        "Address", parent=styles["Normal"], fontSize=tagline_size,
        textColor=colors.HexColor("#333333"), alignment=1, spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "Contact", parent=styles["Normal"], fontSize=tagline_size,
        textColor=colors.HexColor("#333333"), alignment=1, spaceAfter=5,
    )
    services_style = ParagraphStyle(
        "Services", parent=styles["Normal"], fontSize=services_size,
        textColor=colors.HexColor("#0b6e4f"), alignment=1, spaceAfter=6,
        leading=services_size + 3,
    )
    label_style = ParagraphStyle("Label", parent=styles["Normal"], fontSize=label_size)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=small_size, textColor=colors.grey)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=cell_size)

    story = []

    # ---------------- SHOP HEADER ----------------
    story.append(Paragraph(SHOP_NAME, title_style))
    story.append(Paragraph(SHOP_ADDRESS, address_style))
    contact_line = f"Contact: {SHOP_PHONE1}  /  {SHOP_PHONE2}"
    if is_gst and SHOP_GSTIN:
        contact_line += f"   |   GSTIN: {SHOP_GSTIN}"
    story.append(Paragraph(contact_line, contact_style))
    story.append(
        Paragraph(f"<b>{SHOP_VEHICLE_TAG}</b>  &nbsp;|&nbsp;  {SHOP_SERVICES}", services_style)
    )
    story.append(HRFlowable(width="100%", color=colors.HexColor("#00aa77"), thickness=1.2))
    story.append(Spacer(1, 8 if is_a4 else 6))

    invoice_no = f"INV-{record['id']:04d}"
    printed_on = datetime.now().strftime("%d-%m-%Y")
    type_label = "Given (Udhar Dile)" if record["type"] == "Given" else "Taken (Udhar Ghetle)"
    doc_title = "TAX INVOICE" if is_gst else "INVOICE / BILL"

    story.append(Paragraph(f"<b>{doc_title}</b>", ParagraphStyle(
        "DocTitle", parent=styles["Normal"], fontSize=label_size + 1,
        textColor=colors.HexColor("#0b6e4f"), spaceAfter=6, alignment=1,
    )))

    header_rows = [
        [Paragraph(f"<b>Invoice No:</b> {invoice_no}", label_style),
         Paragraph(f"<b>Date:</b> {record['tx_date'] or printed_on}", label_style)],
        [Paragraph(f"<b>Type:</b> {type_label}", label_style),
         Paragraph(f"<b>Due Date:</b> {record['due_date'] or '-'}", label_style)],
    ]
    if is_gst:
        header_rows.append([
            Paragraph(f"<b>Place of Supply:</b> {customer_state}", label_style),
            Paragraph(f"<b>GSTIN (Buyer):</b> {customer_gstin or '-'}", label_style),
        ])
    header_table = Table(header_rows, colWidths=["50%", "50%"])
    story.append(header_table)
    story.append(Spacer(1, 10))

    # ---------------- CUSTOMER DETAILS (auto-fill) ----------------
    story.append(Paragraph("<b>Customer Details</b>", styles["Heading4"]))
    cust_lines = [f"<b>Name:</b> {record['name']}"]
    if record["mobile"]:
        cust_lines.append(f"<b>Mobile:</b> {record['mobile']}")
    if record["address"]:
        cust_lines.append(f"<b>Address:</b> {record['address']}")
    if record["vehicle"]:
        veh = record["vehicle"]
        if record["vehicle_no"]:
            veh += f" ({record['vehicle_no']})"
        cust_lines.append(f"<b>Vehicle:</b> {veh}")

    for line in cust_lines:
        story.append(Paragraph(line, label_style))
    story.append(Spacer(1, 10))

    # ---------------- LINE ITEMS + GST गणित ----------------
    tax_groups = {}  # gst_rate -> {"taxable": x, "tax": y}
    items_total = 0.0
    taxable_total = 0.0

    has_part_info = any(it.get("part_no") or it.get("rack") for it in items)

    if is_gst and has_part_info:
        bill_header = ["SI", "Description", "HSN/SAC", "Part No", "Rack", "Qty", "Rate", "Disc%", "Amount"]
        col_widths = ["4%", "22%", "12%", "13%", "8%", "7%", "12%", "8%", "14%"]
    elif is_gst:
        bill_header = ["SI", "Description", "HSN/SAC", "Qty", "Rate", "Disc%", "Amount"]
        col_widths = ["5%", "33%", "14%", "8%", "14%", "10%", "16%"]
    else:
        bill_header = ["SI", "Description", "Qty", "Rate", "Disc%", "Amount"]
        col_widths = ["6%", "44%", "10%", "16%", "10%", "14%"]

    bill_rows = [bill_header]

    for idx, item in enumerate(items, start=1):
        qty = float(item.get("qty", 1) or 1)
        rate = float(item.get("rate", 0) or 0)
        disc = float(item.get("discount_percent", 0) or 0)
        gst_rate = float(item.get("gst_rate", 18) or 0)

        gross = qty * rate
        line_amount = gross - (gross * disc / 100)  # ग्राहकाला दिसणारी अंतिम रक्कम (त्या ओळीची)

        if is_gst:
            if price_includes_gst:
                taxable = line_amount / (1 + gst_rate / 100) if gst_rate else line_amount
            else:
                taxable = line_amount
                line_amount = taxable * (1 + gst_rate / 100)  # GST वर लावल्याने रक्कम वाढते
            tax_amt = line_amount - taxable
            taxable_total += taxable
            grp = tax_groups.setdefault(gst_rate, {"taxable": 0.0, "tax": 0.0})
            grp["taxable"] += taxable
            grp["tax"] += tax_amt
        else:
            taxable = line_amount

        items_total += line_amount

        if is_gst and has_part_info:
            bill_rows.append([
                str(idx), Paragraph(item.get("description", ""), cell_style),
                item.get("hsn_sac", "") or "-", item.get("part_no", "") or "-",
                item.get("rack", "") or "-", f"{qty:.0f}", f"{rate:,.2f}",
                f"{disc:.0f}%", f"{line_amount:,.2f}",
            ])
        elif is_gst:
            bill_rows.append([
                str(idx), Paragraph(item.get("description", ""), cell_style),
                item.get("hsn_sac", "") or "-", f"{qty:.0f}", f"{rate:,.2f}",
                f"{disc:.0f}%", f"{line_amount:,.2f}",
            ])
        else:
            bill_rows.append([
                str(idx), Paragraph(item.get("description", ""), cell_style),
                f"{qty:.0f}", f"{rate:,.2f}", f"{disc:.0f}%", f"{line_amount:,.2f}",
            ])

    bill_table = Table(bill_rows, colWidths=col_widths)
    bill_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00ffaa")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), cell_size),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT") if not is_gst else
        (("ALIGN", (5, 0), (-1, -1), "RIGHT") if has_part_info else ("ALIGN", (3, 0), (-1, -1), "RIGHT")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6 if is_a4 else 4),
        ("TOPPADDING", (0, 0), (-1, -1), 6 if is_a4 else 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 10))

    # ---------------- TOTALS / TAX SUMMARY ----------------
    if is_gst:
        summary_rows = [["Taxable Value", _rs(taxable_total)]]
        cgst_total = sgst_total = igst_total = 0.0
        for gst_rate in sorted(tax_groups.keys()):
            grp = tax_groups[gst_rate]
            if is_intra_state:
                half = grp["tax"] / 2
                cgst_total += half
                sgst_total += half
                summary_rows.append([f"CGST @ {gst_rate/2:.1f}%", _rs(half)])
                summary_rows.append([f"SGST @ {gst_rate/2:.1f}%", _rs(half)])
            else:
                igst_total += grp["tax"]
                summary_rows.append([f"IGST @ {gst_rate:.0f}%", _rs(grp["tax"])])

        raw_total = taxable_total + cgst_total + sgst_total + igst_total
        rounded_total = round(raw_total)
        round_off = rounded_total - raw_total
        summary_rows.append(["Round Off", _rs(round_off)])
        summary_rows.append(["Grand Total", _rs(rounded_total)])

        summary_table = Table(summary_rows, colWidths=["70%", "30%"])
        summary_table.setStyle(TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), label_size - 1),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 8))

    # ग्राहकाच्या Udhaari रेकॉर्डमधली खरी Total/Paid/Due रक्कम (ही ledger-truth
    # आहे — वरचा GST ब्रेकअप फक्त त्याच रकमेचं presentation आहे, वेगळी नाही)
    totals_data = [
        ["Total Amount", _rs(record["total_amt"])],
        ["Paid Amount", _rs(record["paid_amt"])],
        ["Due Amount", _rs(record["due_amt"])],
    ]
    totals_table = Table(totals_data, colWidths=["70%", "30%"])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 2), (-1, 2),
         colors.HexColor("#cc4400") if record["due_amt"] > 0 else colors.HexColor("#0b6e4f")),
        ("LINEABOVE", (0, 2), (-1, 2), 0.8, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 5 if is_a4 else 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if is_a4 else 4),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 8))

    # ---------------- Amount in Words ----------------
    story.append(Paragraph(
        f"<b>Amount Chargeable (in words):</b> {amount_in_words(record['total_amt'])}",
        small_style))
    story.append(Spacer(1, 10 if is_a4 else 6))

    # ---------------- Bank Details + Declaration ----------------
    if is_gst and (BANK_NAME or BANK_ACC_NO):
        footer_table = Table([[
            Paragraph(
                "<b>Declaration</b><br/>We declare that this invoice shows the "
                "actual price of the goods described and that all particulars "
                "are true and correct.", small_style),
            Paragraph(
                f"<b>Bank Details</b><br/>A/c Holder: {BANK_HOLDER}<br/>"
                f"Bank: {BANK_NAME or '-'}<br/>A/c No: {BANK_ACC_NO or '-'}<br/>"
                f"IFSC: {BANK_IFSC or '-'}", small_style),
        ]], colWidths=["50%", "50%"])
        story.append(footer_table)
        story.append(Spacer(1, 14 if is_a4 else 8))

    # ---------------- Signature ----------------
    story.append(Table(
        [["Customer's Seal and Signature", f"for {SHOP_NAME}\n\n\nAuthorised Signatory"]],
        colWidths=["50%", "50%"],
        style=TableStyle([("FONTSIZE", (0, 0), (-1, -1), small_size),
                          ("ALIGN", (1, 0), (1, 0), "RIGHT")]),
    ))
    story.append(Spacer(1, 10 if is_a4 else 6))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=0.6))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Thank you! Visit Again.", label_style))
    if is_gst:
        story.append(Paragraph("This is a computer-generated tax invoice.", small_style))
    story.append(Paragraph(f"Printed on {printed_on}", small_style))

    doc.build(story)
    return filepath
