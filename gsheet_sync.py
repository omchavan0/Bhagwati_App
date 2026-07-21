"""
============================================================================
GSHEET_SYNC — Google Sheets कडे Live Mirror (Optional, Best-Effort)
============================================================================
हे मॉड्यूल db_udhaari.py / db_expenses.py / db_work.py कडून कॉल होतं —
प्रत्येक add/update/delete नंतर, त्या टेबलचा *सध्याचा पूर्ण स्नॅपशॉट*
(सगळे active रेकॉर्ड्स) संबंधित Google Sheet टॅबवर mirror करतं.

का "sync_*(records)" पॅटर्न वापरलाय:
  Local SQLite हाच "source of truth" आहे. Google Sheet फक्त वाचण्यासाठी/
  शेअर करण्यासाठी एक आरसा (mirror) आहे — म्हणून प्रत्येक वेळी शीट पूर्ण
  Clear करून, ताज्या डेटाने पुन्हा भरतो (Overwrite), append करत नाही.
  यामुळे डिलीट/एडिट झालेले जुने रेकॉर्ड्स शीटवर कधीही अनाथ (stale) राहत
  नाहीत — SQLite आणि Sheet नेहमी 100% जुळलेले राहतात.

महत्त्वाचं — हे पूर्णपणे optional/best-effort आहे:
  - इंटरनेट नसेल, "service_account.json" नसेल, किंवा gspread install
    नसेल — तरी db_core.py मधला _safe_sync() wrapper प्रत्येक कॉल आधीच
    try/except मध्ये गुंडाळतो. त्यामुळे इथे काहीही चुकलं तरी मुख्य ॲप
    (SQLite) कधीही अडकत/क्रॅश होत नाही — ते Google Sheets sync सारखंच
    "fail-safe" पॅटर्न आहे जे final_sale_transfer_and_pdf.py मध्येही वापरलंय.

--------------------------------------------------------------------------
SETUP (एकदाच):
1. pip install gspread google-auth --break-system-packages

2. Google Cloud Console (https://console.cloud.google.com):
   -> "APIs & Services" -> "Library" -> "Google Sheets API" Enable करा
   -> "Google Drive API" सुद्धा Enable करा

3. Service Account (नसेल तर):
   -> "Credentials" -> "Create Credentials" -> "Service Account"
   -> Keys टॅब -> "Add Key" -> JSON -> डाउनलोड करून याच फोल्डरमध्ये
      "service_account.json" नावाने ठेवा (तुझ्याकडे आधीच आहे ✅)

4. **महत्त्वाचं:** त्या Service Account च्या ईमेलला (JSON मधला
   "client_email") तुझी Google Sheet "Editor" access देऊन Share करा.

5. खाली SPREADSHEET_NAME बरोबर टाका — Google Drive वरच्या फाईलचं नाव
   (final_sale_transfer_and_pdf.py मध्ये वापरलेल्या शीटशी जुळवलंय).
--------------------------------------------------------------------------
"""

import os

CREDENTIALS_FILE = "service_account.json"
SPREADSHEET_NAME = "Bhagwati_Auto_Electricals"

SHEET_UDHAARI = "Udhaari_Log"
SHEET_EXPENSES = "Expenses_Log"
SHEET_DAILY_WORK = "Daily_Work_Log"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_spreadsheet = None


# ==========================================================================
# AUTHENTICATION — Service Account वापरून, कुठलाही login popup न दाखवता
# ==========================================================================
def _get_client():
    """gspread क्लायंट एकदाच तयार करून cache करतो."""
    global _client
    if _client is None:
        import gspread
        from google.oauth2.service_account import Credentials

        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(f"'{CREDENTIALS_FILE}' सापडली नाही.")

        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
    return _client


def _get_spreadsheet():
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = _get_client().open(SPREADSHEET_NAME)
    return _spreadsheet


def _get_or_create_worksheet(sheet_name, headers):
    import gspread
    ss = _get_spreadsheet()
    try:
        return ss.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(headers), 10))
        ws.append_row(headers)
        return ws


def _mirror_table(sheet_name, headers, rows):
    """शीट पूर्ण Clear करून, दिलेल्या rows ने पुन्हा भरतो (headers सहित)."""
    ws = _get_or_create_worksheet(sheet_name, headers)
    ws.clear()
    ws.update([headers] + rows, value_input_option="USER_ENTERED")


# ==========================================================================
# प्रत्येक टेबलसाठी एक sync फंक्शन — db_*.py मधले _safe_sync() कॉल्स यांनाच
# बोलावतात (उदा. _safe_sync(gsheet_sync.sync_udhaari, get_udhaari()))
# ==========================================================================

def sync_udhaari(records):
    """records = db_udhaari.get_udhaari() चा संपूर्ण निकाल (sqlite3.Row list)."""
    headers = ["ID", "Name", "Mobile", "Vehicle", "Vehicle No", "Address",
               "Trans. Date", "Due Date", "Total Amt", "Paid Amt", "Due Amt",
               "Notes", "Type", "Client ID"]
    rows = [
        [r["id"], r["name"], r["mobile"], r["vehicle"], r["vehicle_no"], r["address"],
         r["tx_date"], r["due_date"], r["total_amt"], r["paid_amt"], r["due_amt"],
         r["notes"], r["type"], r["client_id"]]
        for r in records
    ]
    _mirror_table(SHEET_UDHAARI, headers, rows)


def sync_expenses(records):
    """records = db_expenses.get_expenses() चा संपूर्ण निकाल."""
    headers = ["ID", "Title", "Category", "Amount", "Date", "Notes",
               "Payment Mode", "Paid To", "Receipt No"]
    rows = [
        [r["id"], r["title"], r["category"], r["amount"], r["exp_date"], r["notes"],
         r["payment_mode"], r["paid_to"], r["receipt_no"]]
        for r in records
    ]
    _mirror_table(SHEET_EXPENSES, headers, rows)


def sync_daily_work(records):
    """records = db_work.get_daily_work() चा संपूर्ण निकाल."""
    headers = ["ID", "Customer", "Vehicle", "Vehicle No", "Mobile", "Work Description",
               "Labour Charge", "Parts Charge", "Total Charge", "Parts Used",
               "Date", "Status"]
    rows = [
        [r["id"], r["customer_name"], r["vehicle"], r["vehicle_no"], r["mobile"],
         r["work_desc"], r["labour_charge"], r["parts_charge"], r["charge_amt"],
         r["parts_used"], r["work_date"], r["status"]]
        for r in records
    ]
    _mirror_table(SHEET_DAILY_WORK, headers, rows)
