"""
============================================================================
UDHAARI PAYMENT MANAGER — final_sale_transfer_and_pdf.py साठी नवीन Feature
============================================================================
समस्या (जुन्या स्क्रिप्टमध्ये काय गहाळ होतं):
  process_sale() मध्ये "Credit" sale झाली की Udhaari_Log मध्ये एक नोंद जाते
  (Total/Paid/Due सह) — पण नंतर तोच customer हप्त्या-हप्त्याने पैसे भरत गेला
  तर ते नोंदवायला कुठलंही function नव्हतं. त्यामुळे Due Amount कायम "जुनाच"
  दिसत राहायचा, आणि कोणी किती वेळा, कधी पैसे भरले याचा काहीही इतिहास
  (audit trail) राहत नव्हता.

हे नवीन Feature काय करतं:
  1. record_udhaari_payment() — Invoice No वरून तो customer/sale ओळखतो,
     Udhaari_Log मधली Paid/Due रक्कम आपोआप अपडेट करतो.
  2. प्रत्येक repayment ही एक स्वतंत्र, कायमची नोंद म्हणून एका नवीन शीटमध्ये
     ("Udhaari_Payments_Log") जाते — म्हणजे "कोणी, कधी, किती वेळा पैसे भरले"
     याचा पूर्ण इतिहास (audit trail) कायम सुरक्षित राहतो.
  3. Due पूर्ण भरला (Due == 0) की आपोआप ओळखलं जातं (fully_paid=True) —
     UI/WhatsApp मध्ये "✅ Fully Paid" असा मेसेज दाखवायला उपयोगी.
  4. get_due_customers() — अजून ज्यांच्याकडे Due > 0 आहे अशा सगळ्यांची यादी
     (WhatsApp reminder पाठवण्यासाठी) — customer नुसार ग्रुप करून.

--------------------------------------------------------------------------
AUTHENTICATION — Google Service Account (तुझ्याकडे आधीच JSON रेडी आहे):
  1. pip install gspread google-auth --break-system-packages
  2. Google Cloud Console -> "Google Sheets API" + "Google Drive API" Enable.
  3. Service Account JSON डाउनलोड करून याच फोल्डरमध्ये "service_account.json"
     नावाने ठेव (हेच final_sale_transfer_and_pdf.py सुद्धा वापरतं).
  4. त्या Service Account च्या ईमेलला (JSON मधला "client_email") तुझी
     Google Sheet "Editor" access देऊन Share कर — हे केलं नाही तर
     "PERMISSION_DENIED" एरर येईल.
  5. खालचा SPREADSHEET_NAME तुझ्या शीटच्या नावाशी जुळत असल्याची खात्री कर.
     (हे final_sale_transfer_and_pdf.py सारखंच spreadsheet वापरतं, त्यामुळे
     Udhaari_Log आधीच तिथे असलेली शीट वापरली जाईल — वेगळी बनवायची गरज नाही.)
--------------------------------------------------------------------------
"""

import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

# ==========================================================================
# CONFIG — final_sale_transfer_and_pdf.py शी सुसंगत ठेवलंय
# ==========================================================================
CREDENTIALS_FILE = "service_account.json"
SPREADSHEET_NAME = "Bhagwati_Auto_Electricals"

SHEET_UDHAARI = "Udhaari_Log"
SHEET_UDHAARI_PAYMENTS = "Udhaari_Payments_Log"   # 👈 नवीन शीट (Audit Trail)

# Udhaari_Log चे कॉलम्स (final_sale_transfer_and_pdf.py मधल्याच क्रमाने)
UDHAARI_HEADERS = [
    "Date", "Customer Name", "Mobile", "Vehicle", "Vehicle No",
    "Work Description", "Total Amount", "Paid Amount", "Due Amount",
    "Invoice No", "Status",
]
COL_TOTAL = 7
COL_PAID = 8
COL_DUE = 9
COL_INVOICE_NO = 10
COL_STATUS = 11

PAYMENTS_HEADERS = [
    "Payment Date", "Invoice No", "Customer Name", "Mobile",
    "Amount Paid", "Payment Mode", "Balance Due After",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_spreadsheet = None


# ==========================================================================
# AUTHENTICATION
# ==========================================================================
def get_gspread_client():
    """Service Account credentials वापरून gspread client तयार करतो/परत देतो."""
    global _client
    if _client is None:
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"❌ '{CREDENTIALS_FILE}' सापडली नाही. Service Account JSON "
                "डाउनलोड करून याच फोल्डरमध्ये ठेव."
            )
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet():
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = get_gspread_client().open(SPREADSHEET_NAME)
    return _spreadsheet


def get_or_create_worksheet(sheet_name, headers):
    ss = get_spreadsheet()
    try:
        return ss.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(headers), 10))
        ws.append_row(headers)
        return ws


# ==========================================================================
# CORE — Sale summary extract करणारा helper (Modular, process_sale() मधून
# आणि इथूनही reuse होऊ शकतो)
# ==========================================================================
def extract_sale_summary(sale):
    """एका sale dict मधून महत्त्वाची माहिती वेगळी काढतो — Customer, Date,
    Total Amount, Work Description. (process_sale() ला logging च्या आधी
    कॉल करण्यासाठी वापरता येतं — कोड modular आणि readable राहतो.)"""
    return {
        "customer_name": sale.get("customer_name", "").strip(),
        "date": sale.get("date") or datetime.now().strftime("%d-%m-%Y"),
        "total_amount": float(sale.get("total_amount", 0) or 0),
        "work_description": (sale.get("work_description") or "Service / Work").strip(),
        "mobile": sale.get("mobile", ""),
        "invoice_no": sale.get("invoice_no", ""),
    }


# ==========================================================================
# NEW FEATURE — Udhaari Repayment Tracking
# ==========================================================================
def record_udhaari_payment(invoice_no, amount_paid, payment_mode="Cash", payment_date=None):
    """
    एका Credit sale वर ग्राहकाने आत्ता किती पैसे भरले याची नोंद घेतो —
    Udhaari_Log मधला Paid/Due आपोआप अपडेट करतो आणि Udhaari_Payments_Log
    मध्ये कायमची (audit-trail) नोंद जोडतो.

    Params:
        invoice_no (str)     : ज्या Sale/Invoice वर पैसे भरले (उदा. "INV-0007")
        amount_paid (float)  : आत्ता भरलेली रक्कम
        payment_mode (str)   : "Cash" / "UPI" / "Bank Transfer" इ.
        payment_date (str)   : नसेल तर आजची तारीख वापरतो

    Returns:
        dict: {"invoice_no", "new_paid_amount", "new_due_amount", "fully_paid"}

    Raises:
        ValueError    : चुकीची रक्कम दिली तर
        LookupError   : तो Invoice No Udhaari_Log मध्ये सापडला नाही तर
    """
    if amount_paid is None or float(amount_paid) <= 0:
        raise ValueError("⚠️ Amount Paid शून्यापेक्षा जास्त असावी.")
    amount_paid = float(amount_paid)
    payment_date = payment_date or datetime.now().strftime("%d-%m-%Y")

    ws = get_or_create_worksheet(SHEET_UDHAARI, UDHAARI_HEADERS)

    try:
        cell = ws.find(str(invoice_no), in_column=COL_INVOICE_NO)
    except gspread.exceptions.CellNotFound:
        cell = None

    if cell is None:
        raise LookupError(f"❌ Invoice No '{invoice_no}' Udhaari_Log मध्ये सापडला नाही.")

    row = cell.row
    row_values = ws.row_values(row)

    def _safe_float(idx):
        try:
            return float(row_values[idx - 1]) if len(row_values) >= idx and row_values[idx - 1] else 0.0
        except ValueError:
            return 0.0

    total_amount = _safe_float(COL_TOTAL)
    old_paid = _safe_float(COL_PAID)
    customer_name = row_values[1] if len(row_values) > 1 else ""
    mobile = row_values[2] if len(row_values) > 2 else ""

    new_paid = old_paid + amount_paid
    new_due = max(total_amount - new_paid, 0)
    fully_paid = new_due <= 0
    status = "✅ Paid Full" if fully_paid else "⏳ Partial Due"

    # --- Udhaari_Log मधली Paid/Due/Status अपडेट ---
    ws.update_cell(row, COL_PAID, new_paid)
    ws.update_cell(row, COL_DUE, new_due)
    ws.update_cell(row, COL_STATUS, status)

    # --- Payments Log मध्ये कायमची नोंद (Audit Trail) ---
    payments_ws = get_or_create_worksheet(SHEET_UDHAARI_PAYMENTS, PAYMENTS_HEADERS)
    payments_ws.append_row([
        payment_date, invoice_no, customer_name, mobile,
        amount_paid, payment_mode, new_due,
    ])

    return {
        "invoice_no": invoice_no,
        "customer_name": customer_name,
        "new_paid_amount": new_paid,
        "new_due_amount": new_due,
        "fully_paid": fully_paid,
    }


def get_payment_history(invoice_no):
    """एका Invoice वर आजवर झालेले सगळे repayments (हप्ते) परत देतो —
    Customer ला 'तुम्ही कधी-कधी किती भरलं' दाखवायला उपयोगी."""
    ws = get_or_create_worksheet(SHEET_UDHAARI_PAYMENTS, PAYMENTS_HEADERS)
    records = ws.get_all_records()
    return [r for r in records if str(r.get("Invoice No", "")) == str(invoice_no)]


def get_due_customers():
    """अजून Due Amount > 0 आहे अशा सगळ्या ग्राहकांची यादी — नाव, मोबाईल,
    एकूण थकीत रक्कम (एकाच customer च्या अनेक invoices एकत्र बेरीज करून) —
    WhatsApp reminder पाठवण्यासाठी थेट वापरता येतं."""
    ws = get_or_create_worksheet(SHEET_UDHAARI, UDHAARI_HEADERS)
    records = ws.get_all_records()

    due_map = {}
    for r in records:
        due = float(r.get("Due Amount") or 0)
        if due <= 0:
            continue
        name = r.get("Customer Name", "").strip()
        mobile = r.get("Mobile", "").strip()
        key = (name, mobile)
        due_map[key] = due_map.get(key, 0) + due

    return [
        {"customer_name": name, "mobile": mobile, "total_due": total}
        for (name, mobile), total in sorted(due_map.items(), key=lambda x: -x[1])
    ]


# ==========================================================================
# EXAMPLE USAGE
# ==========================================================================
if __name__ == "__main__":
    # उदा: "INV-0007" वर ग्राहकाने आज ₹500 रोख भरले
    result = record_udhaari_payment("INV-0007", amount_paid=500, payment_mode="Cash")
    print("✅ Payment Recorded:", result)

    if result["fully_paid"]:
        print(f"🎉 {result['customer_name']} चं संपूर्ण Udhaari फिटलं!")
    else:
        print(f"⏳ अजून ₹{result['new_due_amount']:.0f} बाकी आहे.")

    print("\n📋 सध्या Due असलेले ग्राहक:")
    for cust in get_due_customers():
        print(f"  {cust['customer_name']} ({cust['mobile']}) — ₹{cust['total_due']:.0f}")
