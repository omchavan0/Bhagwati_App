"""
============================================================================
FINAL SALE TRANSFER & PDF GENERATOR
Bhagwati Auto Electricals — Inventory + Billing + Udhaari + Daily Work Automation
============================================================================
हे स्क्रिप्ट काय करतं (सोप्या भाषेत):

  1. Google Sheets शी (gspread वापरून) कनेक्ट होतं — Service Account
     credentials (JSON) वापरून, कोणताही login popup न दाखवता.
  2. एक Sale (विक्री) process करताना:
       a. वापरलेले Parts "Inventory" शीटमधून वजा (deduct) करतं.
       b. प्रत्येक sale ची नोंद "Billing_Log" शीटमध्ये होते (कायम).
       c. प्रत्येक sale ची नोंद "Daily_Work_Log" शीटमध्ये होते (कायम —
          स्टाफने कोणतं काम, कोणत्या गाडीवर केलं याचा रेकॉर्ड).
       d. Payment Mode "Credit" असेल *तरच* ती नोंद "Udhaari_Log" शीटमध्ये
          वेगळी अजून एकदा जाते (उधारी ट्रॅक करण्यासाठी).
       e. शेवटी एक सुबक PDF Invoice तयार होतो (reportlab वापरून).

--------------------------------------------------------------------------
SETUP (एकदाच):

1. लायब्ररी इन्स्टॉल करा:
      pip install gspread google-auth reportlab

2. Google Cloud Console (https://console.cloud.google.com) वर जा:
      -> नवीन प्रोजेक्ट बनवा (किंवा जुना निवडा)
      -> "APIs & Services" -> "Library" -> "Google Sheets API" Enable करा
      -> "Google Drive API" सुद्धा Enable करा (gspread ला शीट शोधण्यासाठी
         लागते)

3. Service Account बनवा:
      -> "APIs & Services" -> "Credentials" -> "Create Credentials"
         -> "Service Account"
      -> नाव द्या (उदा. "bhagwati-sheets-bot") -> Create -> Done
      -> त्या Service Account वर क्लिक करा -> "Keys" टॅब ->
         "Add Key" -> "Create new key" -> JSON निवडा -> Download होईल.
      -> ती फाईल याच फोल्डरमध्ये "service_account.json" या नावाने ठेवा.

4. **महत्त्वाचं:** Service Account चा एक ईमेल असतो (JSON फाईलमध्ये
   "client_email" म्हणून दिसतो, उदा. bhagwati-bot@xxxxx.iam.gserviceaccount.com).
   तुझी Google Sheet उघडून, त्या ईमेलला "Editor" access देऊन Share करा —
   हे केलं नाही तर स्क्रिप्ट शीटला touch करू शकणार नाही (Permission Denied
   एरर येईल).

5. खाली CONFIG सेक्शनमध्ये तुझ्या स्प्रेडशीटचं नाव (SPREADSHEET_NAME)
   बरोबर टाका — Google Drive मध्ये शीटला जे नाव दिलं आहे तेच.

6. शीट्सची नावं (टॅब्स) खाली दिलेल्या नावांशी जुळत असतील तर उत्तम
   (नसतील तर स्क्रिप्ट स्वतःच आपोआप त्या नावाने नवीन टॅब बनवेल):
      - Inventory
      - Billing_Log
      - Udhaari_Log
      - Daily_Work_Log
--------------------------------------------------------------------------
"""

import os
from datetime import datetime

# ==========================================================================
# WINDOWS SSL CERTIFICATE FIX — काही Windows/Python सेटअपवर Google Sheets शी
# कनेक्ट होताना "SSL: CERTIFICATE_VERIFY_FAILED" एरर येतो, कारण Python ला
# योग्य Root Certificates सापडत नाहीत. हे 3 ओळींनी तो प्रश्न आधीच सोडवतं —
# बाकी सगळ्या network कॉल्सच्या आधी हे असणं गरजेचं आहे.
# (जर तरीही एरर आली तर टर्मिनलमध्ये आधी: pip install --upgrade certifi)
# ==========================================================================
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass  # certifi install नसेल तर हा भाग skip होईल; वरची pip install कमांड चालवा

import gspread
from google.oauth2.service_account import Credentials

from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)


# ==========================================================================
# CONFIG — इथे तुझ्या सेटअपप्रमाणे बदल कर
# ==========================================================================
CREDENTIALS_FILE = "service_account.json"      # Service Account JSON फाईलचं नाव
SPREADSHEET_NAME = "Bhagwati_Auto_Electricals"  # Google Drive वरच्या शीटचं नाव

SHEET_INVENTORY = "Inventory"
SHEET_BILLING = "Billing_Log"
SHEET_UDHAARI = "Udhaari_Log"
SHEET_DAILY_WORK = "Daily_Work_Log"

SHOP_NAME = "Bhagwati Auto Electricals"
SHOP_TAGLINE = "Auto Electricals | Service & Repair | Rewinding"

PDF_OUTPUT_DIR = "invoices"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# प्रत्येक शीटला हवे असलेले कॉलम हेडर्स (नवीन शीट बनवायची वेळ आली तर वापरतो)
HEADERS = {
    SHEET_INVENTORY: ["Part Name", "Stock Qty", "Unit Price", "Min Alert Qty"],
    SHEET_BILLING: [
        "Invoice No", "Date", "Customer Name", "Mobile", "Vehicle",
        "Vehicle No", "Work Description", "Total Amount", "Paid Amount",
        "Due Amount", "Payment Mode", "Staff Name",
    ],
    SHEET_UDHAARI: [
        "Date", "Customer Name", "Mobile", "Vehicle", "Vehicle No",
        "Work Description", "Total Amount", "Paid Amount", "Due Amount",
        "Invoice No",
    ],
    SHEET_DAILY_WORK: [
        "Date", "Staff Name", "Customer Name", "Vehicle", "Vehicle No",
        "Work Description", "Charge Amount", "Payment Mode",
    ],
}


# ==========================================================================
# AUTHENTICATION — एकदाच कनेक्ट होऊन client/spreadsheet cache करतो
# ==========================================================================
_client = None
_spreadsheet = None


def get_gspread_client():
    """Service Account credentials वापरून gspread client तयार करतो/परत देतो."""
    global _client
    if _client is None:
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"❌ '{CREDENTIALS_FILE}' सापडली नाही. वरच्या SETUP सूचनांप्रमाणे "
                "Service Account JSON डाउनलोड करून याच फोल्डरमध्ये ठेव."
            )
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet():
    """मुख्य स्प्रेडशीट (सगळे टॅब्स असलेली फाईल) उघडतो/परत देतो."""
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = get_gspread_client().open(SPREADSHEET_NAME)
    return _spreadsheet


def get_or_create_worksheet(sheet_name):
    """दिलेल्या नावाची worksheet (टॅब) परत देतो; नसेल तर हेडर्ससह नवीन बनवतो."""
    ss = get_spreadsheet()
    try:
        return ss.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        headers = HEADERS.get(sheet_name, [])
        ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(headers), 10))
        if headers:
            ws.append_row(headers)
        return ws


# ==========================================================================
# INVENTORY — विकलेले Parts स्टॉकमधून वजा करणे
# ==========================================================================
def deduct_stock(part_name, qty_used):
    """Inventory शीटमध्ये part_name शोधून त्याचा stock qty_used ने कमी करतो.
    Part सापडला नाही तर शांतपणे skip करतो (बाकी sale process अडकू नये).
    टीप: gspread च्या वेगवेगळ्या version मध्ये न सापडलेल्या cell साठी वेगवेगळं
    वर्तन असतं — काही version CellNotFound raise करतात, तर काही None परत
    देतात. दोन्ही केसेस इथे हाताळल्या आहेत."""
    if not part_name or not qty_used:
        return

    ws = get_or_create_worksheet(SHEET_INVENTORY)
    try:
        cell = ws.find(part_name, in_column=1)
    except gspread.exceptions.CellNotFound:
        cell = None

    if cell is None:
        # हा Part अजून Inventory शीटमध्ये टाकलेला नाहीये — शांतपणे skip.
        # (नवीन Part असेल तर आधी Inventory शीटमध्ये मॅन्युअली एंट्री टाक.)
        return

    row = cell.row
    current_qty_raw = ws.cell(row, 2).value
    try:
        current_qty = float(current_qty_raw) if current_qty_raw else 0
    except ValueError:
        current_qty = 0

    new_qty = max(current_qty - float(qty_used), 0)
    ws.update_cell(row, 2, new_qty)


# ==========================================================================
# LOGGING — तीन वेगवेगळ्या शीट्समध्ये नोंद टाकणे
# ==========================================================================
def log_to_billing(sale):
    """प्रत्येक sale ची कायमची नोंद — payment mode कुठलाही असो."""
    ws = get_or_create_worksheet(SHEET_BILLING)
    ws.append_row([
        sale["invoice_no"], sale["date"], sale["customer_name"], sale["mobile"],
        sale["vehicle"], sale["vehicle_no"], sale["work_description"],
        sale["total_amount"], sale["paid_amount"], sale["due_amount"],
        sale["payment_mode"], sale["staff_name"],
    ])


def log_to_udhaari(sale):
    """Payment Mode 'Credit' असेल तेव्हाच कॉल होतं — उधारी वेगळी ट्रॅक होते."""
    ws = get_or_create_worksheet(SHEET_UDHAARI)
    ws.append_row([
        sale["date"], sale["customer_name"], sale["mobile"], sale["vehicle"],
        sale["vehicle_no"], sale["work_description"], sale["total_amount"],
        sale["paid_amount"], sale["due_amount"], sale["invoice_no"],
    ])


def log_to_daily_work(sale):
    """कोणत्या स्टाफने, कोणत्या गाडीवर, काय काम केलं याची रोजची नोंद."""
    ws = get_or_create_worksheet(SHEET_DAILY_WORK)
    ws.append_row([
        sale["date"], sale["staff_name"], sale["customer_name"], sale["vehicle"],
        sale["vehicle_no"], sale["work_description"], sale["total_amount"],
        sale["payment_mode"],
    ])


# ==========================================================================
# PDF INVOICE — कस्टमरला देण्यासाठी बिल
# ==========================================================================
def _rs(amount):
    return f"Rs. {amount:,.2f}"


def generate_invoice_pdf(sale, filepath):
    """sale dict वरून सुबक PDF बिल बनवतं."""
    doc = SimpleDocTemplate(
        filepath, pagesize=A5,
        topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ShopTitle", parent=styles["Title"], fontSize=18,
        textColor=colors.HexColor("#0b6e4f"), spaceAfter=2,
    )
    tagline_style = ParagraphStyle(
        "Tagline", parent=styles["Normal"], fontSize=9,
        textColor=colors.grey, spaceAfter=10,
    )
    label_style = ParagraphStyle("Label", parent=styles["Normal"], fontSize=10)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

    story = [
        Paragraph(SHOP_NAME, title_style),
        Paragraph(SHOP_TAGLINE, tagline_style),
        HRFlowable(width="100%", color=colors.HexColor("#00aa77"), thickness=1.2),
        Spacer(1, 8),
    ]

    header_table = Table(
        [
            [Paragraph(f"<b>Invoice No:</b> {sale['invoice_no']}", label_style),
             Paragraph(f"<b>Date:</b> {sale['date']}", label_style)],
            [Paragraph(f"<b>Payment Mode:</b> {sale['payment_mode']}", label_style),
             Paragraph(f"<b>Staff:</b> {sale['staff_name'] or '-'}", label_style)],
        ],
        colWidths=["50%", "50%"],
    )
    story.append(header_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Customer Details</b>", styles["Heading4"]))
    cust_lines = [f"<b>Name:</b> {sale['customer_name']}"]
    if sale["mobile"]:
        cust_lines.append(f"<b>Mobile:</b> {sale['mobile']}")
    veh = sale["vehicle"] or ""
    if sale["vehicle_no"]:
        veh += f" ({sale['vehicle_no']})"
    if veh.strip():
        cust_lines.append(f"<b>Vehicle:</b> {veh}")
    for line in cust_lines:
        story.append(Paragraph(line, label_style))
    story.append(Spacer(1, 10))

    bill_data = [
        ["Description", "Amount"],
        [sale["work_description"] or "Service / Work", _rs(sale["total_amount"])],
    ]
    bill_table = Table(bill_data, colWidths=["70%", "30%"])
    bill_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00ffaa")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 10))

    totals_data = [
        ["Total Amount", _rs(sale["total_amount"])],
        ["Paid Amount", _rs(sale["paid_amount"])],
        ["Due Amount", _rs(sale["due_amount"])],
    ]
    totals_table = Table(totals_data, colWidths=["70%", "30%"])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 2), (-1, 2),
         colors.HexColor("#cc4400") if sale["due_amount"] > 0 else colors.HexColor("#0b6e4f")),
        ("LINEABOVE", (0, 2), (-1, 2), 0.8, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 16))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=0.6))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Thank you! Visit Again.", label_style))
    story.append(Paragraph(f"Printed on {datetime.now().strftime('%d-%m-%Y %H:%M')}", small_style))

    doc.build(story)
    return filepath


def _next_invoice_no():
    """Billing_Log मधल्या रेकॉर्ड्सच्या संख्येवरून पुढचा Invoice No ठरवतो."""
    ws = get_or_create_worksheet(SHEET_BILLING)
    count = len(ws.get_all_values()) - 1  # header row वजा करून
    count = max(count, 0)
    return f"INV-{count + 1:04d}"


# ==========================================================================
# MAIN ENTRY POINT — FinalSaleTransferAndPDF
# ==========================================================================
def process_sale(customer_name, total_amount, payment_mode, work_description,
                  mobile="", vehicle="", vehicle_no="", paid_amount=None,
                  staff_name="", parts_used=None, make_pdf=True):
    """
    एक पूर्ण Sale process करतो — Inventory deduct, Billing_Log,
    Daily_Work_Log, (गरज असेल तर) Udhaari_Log, आणि PDF Invoice.

    Params:
        customer_name (str)      : कस्टमरचं नाव                       *
        total_amount (float)     : एकूण बिल रक्कम                     *
        payment_mode (str)       : "Cash" / "UPI" / "Credit" इ.        *
        work_description (str)   : काय काम/सर्विस झाली                *
        mobile (str)             : कस्टमरचा मोबाईल नंबर
        vehicle (str)            : गाडीचं नाव/मॉडेल
        vehicle_no (str)         : गाडी नंबर
        paid_amount (float)      : आत्ता किती पैसे मिळाले (None -> Credit
                                    असेल तर 0, नाहीतर पूर्ण total_amount)
        staff_name (str)         : काम कोणत्या स्टाफने केलं
        parts_used (list[dict])  : [{"part_name": "Battery", "qty": 1}, ...]
        make_pdf (bool)          : PDF इनव्हॉइस बनवायचा का

    Returns:
        (sale_data dict, pdf_path किंवा None)
    """
    if not customer_name or not customer_name.strip():
        raise ValueError("⚠️ Customer Name आवश्यक आहे.")
    if not total_amount or float(total_amount) <= 0:
        raise ValueError("⚠️ Total Amount शून्यापेक्षा जास्त असावी.")

    payment_mode = (payment_mode or "Cash").strip()
    is_credit = payment_mode.lower() == "credit"

    if paid_amount is None:
        paid_amount = 0.0 if is_credit else float(total_amount)

    due_amount = max(float(total_amount) - float(paid_amount), 0)

    sale = {
        "invoice_no": _next_invoice_no(),
        "date": datetime.now().strftime("%d-%m-%Y"),
        "customer_name": customer_name.strip(),
        "mobile": (mobile or "").strip(),
        "vehicle": (vehicle or "").strip(),
        "vehicle_no": (vehicle_no or "").strip(),
        "work_description": (work_description or "").strip(),
        "total_amount": float(total_amount),
        "paid_amount": float(paid_amount),
        "due_amount": due_amount,
        "payment_mode": payment_mode,
        "staff_name": (staff_name or "").strip(),
    }

    # 1) Inventory मधून वापरलेले parts वजा करा
    if parts_used:
        for p in parts_used:
            deduct_stock(p.get("part_name"), p.get("qty", 0))

    # 2) Billing_Log — प्रत्येक sale इथे जातेच
    log_to_billing(sale)

    # 3) Daily_Work_Log — प्रत्येक sale इथेही जातेच
    log_to_daily_work(sale)

    # 4) Udhaari_Log — फक्त Credit असेल तरच
    if is_credit:
        log_to_udhaari(sale)

    # 5) PDF Invoice
    pdf_path = None
    if make_pdf:
        os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in sale["customer_name"])
        pdf_path = os.path.join(PDF_OUTPUT_DIR, f"Bill_{safe_name}_{sale['invoice_no']}.pdf")
        generate_invoice_pdf(sale, pdf_path)

    return sale, pdf_path


# ==========================================================================
# EXAMPLE USAGE — स्वतःच्या UI/फॉर्ममधून हेच process_sale() कॉल करायचं
# ==========================================================================
if __name__ == "__main__":
    sale_data, pdf = process_sale(
        customer_name="Ramesh Patil",
        mobile="9876543210",
        vehicle="TVS Jupiter",
        vehicle_no="MH20AB1234",
        work_description="Self starter rewinding + wiring check",
        total_amount=1800,
        payment_mode="Credit",       # 'Credit' दिलं की आपोआप Udhaari_Log मध्ये जाईल
        paid_amount=500,             # बाकी 1300 उधारी म्हणून राहील
        staff_name="Om",
        parts_used=[{"part_name": "Starter Coil", "qty": 1}],
    )
    print("✅ Sale Processed:", sale_data)
    print("📄 PDF Invoice:", pdf)
