# -*- coding: utf-8 -*-
"""
SALE_PROCESSOR — Bhagwati Auto Electricals
Credit Sale झाली की आपोआप Udhaari_Log + Daily_Work_Log मध्ये नोंद.
Auth: Google Service Account (service_account.json) + gspread.
"""

import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

# ============================== CONFIG ==============================
CREDENTIALS_FILE = "service_account.json"
SPREADSHEET_NAME = "Bhagwati_Auto_Electricals"

SHEET_BILLING = "Billing_Log"
SHEET_UDHAARI = "Udhaari_Log"
SHEET_DAILY_WORK = "Daily_Work_Log"

HEADERS = {
    SHEET_BILLING: ["Invoice No", "Date", "Customer Name", "Mobile", "Vehicle",
                     "Vehicle No", "Work Description", "Total Amount",
                     "Paid Amount", "Due Amount", "Payment Mode", "Staff Name"],
    SHEET_UDHAARI: ["Date", "Customer Name", "Mobile", "Vehicle", "Vehicle No",
                     "Work Description", "Total Amount", "Paid Amount",
                     "Due Amount", "Invoice No"],
    SHEET_DAILY_WORK: ["Date", "Staff Name", "Customer Name", "Vehicle",
                        "Vehicle No", "Work Description", "Charge Amount",
                        "Payment Mode"],
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_spreadsheet = None


# ============================== AUTH ==============================
def get_client():
    """Service Account JSON वापरून gspread client तयार करतो (एकदाच, cached)."""
    global _client
    if _client is None:
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(f"'{CREDENTIALS_FILE}' सापडली नाही.")
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet():
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = get_client().open(SPREADSHEET_NAME)
    return _spreadsheet


def get_or_create_worksheet(sheet_name):
    """दिलेली worksheet परत देतो; नसेल तर headers सह नवीन बनवतो."""
    ss = get_spreadsheet()
    try:
        return ss.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        headers = HEADERS.get(sheet_name, [])
        ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(headers), 10))
        if headers:
            ws.append_row(headers)
        return ws


# ============================== EXTRACT ==============================
def extract_sale_summary(customer_name, total_amount, work_description,
                          mobile="", vehicle="", vehicle_no="",
                          paid_amount=None, payment_mode="Cash",
                          staff_name="", invoice_no=None, date=None):
    """Sale च्या raw इनपुट मधून एक स्वच्छ dict बनवतो — पुढच्या सगळ्या
    log_* फंक्शन्सना हाच dict पास होतो."""
    payment_mode = (payment_mode or "Cash").strip()
    is_credit = payment_mode.lower() == "credit"

    if paid_amount is None:
        paid_amount = 0.0 if is_credit else float(total_amount)

    due_amount = max(float(total_amount) - float(paid_amount), 0)

    return {
        "invoice_no": invoice_no or f"INV-{datetime.now().strftime('%y%m%d%H%M%S')}",
        "date": date or datetime.now().strftime("%d-%m-%Y"),
        "customer_name": (customer_name or "").strip(),
        "mobile": (mobile or "").strip(),
        "vehicle": (vehicle or "").strip(),
        "vehicle_no": (vehicle_no or "").strip(),
        "work_description": (work_description or "Service / Work").strip(),
        "total_amount": float(total_amount),
        "paid_amount": float(paid_amount),
        "due_amount": due_amount,
        "payment_mode": payment_mode,
        "staff_name": (staff_name or "").strip(),
        "is_credit": is_credit,
    }


# ============================== LOGGING ==============================
def log_to_billing(sale):
    """प्रत्येक sale ची कायमची नोंद (payment mode कुठलाही असो)."""
    ws = get_or_create_worksheet(SHEET_BILLING)
    ws.append_row([
        sale["invoice_no"], sale["date"], sale["customer_name"], sale["mobile"],
        sale["vehicle"], sale["vehicle_no"], sale["work_description"],
        sale["total_amount"], sale["paid_amount"], sale["due_amount"],
        sale["payment_mode"], sale["staff_name"],
    ])


def log_to_udhaari(sale):
    """फक्त payment_mode == 'Credit' असेल तेव्हाच कॉल होतं — उधारी वेगळी ट्रॅक होते."""
    ws = get_or_create_worksheet(SHEET_UDHAARI)
    ws.append_row([
        sale["date"], sale["customer_name"], sale["mobile"], sale["vehicle"],
        sale["vehicle_no"], sale["work_description"], sale["total_amount"],
        sale["paid_amount"], sale["due_amount"], sale["invoice_no"],
    ])


def log_to_daily_work(sale):
    """स्टाफने कोणतं काम, कोणत्या गाडीवर केलं याची रोजची नोंद (Credit असो वा नसो)."""
    ws = get_or_create_worksheet(SHEET_DAILY_WORK)
    ws.append_row([
        sale["date"], sale["staff_name"], sale["customer_name"], sale["vehicle"],
        sale["vehicle_no"], sale["work_description"], sale["total_amount"],
        sale["payment_mode"],
    ])


# ============================== MAIN ENTRY ==============================
def process_sale(customer_name, total_amount, work_description, payment_mode="Cash",
                  mobile="", vehicle="", vehicle_no="", paid_amount=None,
                  staff_name="", invoice_no=None, date=None):
    """
    एक Sale process करतो:
      1. नेहमी Billing_Log मध्ये नोंद जाते.
      2. नेहमी Daily_Work_Log मध्ये नोंद जाते (staff/vehicle/work track).
      3. payment_mode == 'Credit' असेल तरच Udhaari_Log मध्ये अतिरिक्त नोंद जाते.

    Returns: sale (dict) — पुढे PDF/WhatsApp साठी वापरता येतो.
    """
    if not customer_name or not customer_name.strip():
        raise ValueError("⚠️ Customer Name आवश्यक आहे.")
    if not total_amount or float(total_amount) <= 0:
        raise ValueError("⚠️ Total Amount शून्यापेक्षा जास्त असावी.")

    sale = extract_sale_summary(
        customer_name=customer_name, total_amount=total_amount,
        work_description=work_description, mobile=mobile, vehicle=vehicle,
        vehicle_no=vehicle_no, paid_amount=paid_amount, payment_mode=payment_mode,
        staff_name=staff_name, invoice_no=invoice_no, date=date,
    )

    log_to_billing(sale)
    log_to_daily_work(sale)

    if sale["is_credit"]:
        log_to_udhaari(sale)

    return sale


# ============================== EXAMPLE ==============================
if __name__ == "__main__":
    result = process_sale(
        customer_name="Ramesh Patil", mobile="9876543210",
        vehicle="TVS Jupiter", vehicle_no="MH20AB1234",
        work_description="Self starter rewinding + wiring check",
        total_amount=1800, payment_mode="Credit", paid_amount=500,
        staff_name="Om",
    )
    print("✅ Sale Processed:", result)
    if result["is_credit"]:
        print(f"📒 Udhaari_Log मध्ये नोंद झाली — Due ₹{result['due_amount']:.0f}")
