"""
============================================================================
DB CUSTOMERS — GST Customer Master (Billing साठी वेगळा, प्रोफेशनल Customer डेटा)
============================================================================
टीप: हा "clients" (Garage Groups, db_clients.py) पेक्षा वेगळा आहे —
clients म्हणजे एक Garage/Business group जिथे अनेक udhaari नोंदी लिंक होतात.
"customers" इथे GST Billing साठी लागणारा प्रत्येक ग्राहकाचा स्वतंत्र, पूर्ण
GST प्रोफाइल (GSTIN/State/PIN सकट) ठेवतो — Registered/Unregistered आपोआप
gstin वरून ठरतो (gst_utils.is_registered_customer).
============================================================================
"""
from datetime import datetime

from db_core import _get_connection, _queue_sync, get_current_owner_uid, get_current_owner_email, get_device_id
from gst_utils import is_registered_customer, get_state_code_from_name

CUSTOMER_COLUMNS = [
    ("mobile", "TEXT"),
    ("email", "TEXT"),
    ("gstin", "TEXT"),
    ("address", "TEXT"),
    ("city", "TEXT"),
    ("state", "TEXT DEFAULT 'Maharashtra'"),
    ("state_code", "TEXT DEFAULT '27'"),
    ("pin_code", "TEXT"),
    ("vehicle", "TEXT"),
    ("vehicle_no", "TEXT"),
    ("business_type", "TEXT"),
    ("customer_type", "TEXT DEFAULT 'Retail'"),
    ("registration_status", "TEXT DEFAULT 'Unregistered'"),
    ("notes", "TEXT"),
    ("created_at", "TEXT"),
]


def _touch_sync_fields(record_id, table):
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=?, owner_uid=?, owner_email=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), get_current_owner_uid(),
               get_current_owner_email(), record_id))
    conn.commit()
    conn.close()


def init_table(conn, c):
    """customers टेबल तयार/मायग्रेट करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL
                 )''')
    conn.commit()

    c.execute("PRAGMA table_info(customers)")
    existing = {row[1] for row in c.fetchall()}
    for col_name, col_type in CUSTOMER_COLUMNS:
        if col_name not in existing:
            c.execute(f"ALTER TABLE customers ADD COLUMN {col_name} {col_type}")
    conn.commit()


# ======================================================================
# CRUD
# ======================================================================

def add_customer(name, mobile="", email="", gstin="", address="", city="",
                  state="Maharashtra", state_code=None, pin_code="", vehicle="",
                  vehicle_no="", business_type="", customer_type="Retail", notes=""):
    gstin = (gstin or "").strip().upper()
    state_code = state_code or get_state_code_from_name(state) or "27"
    reg_status = "Registered" if is_registered_customer(gstin) else "Unregistered"

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO customers
                 (name, mobile, email, gstin, address, city, state, state_code, pin_code,
                  vehicle, vehicle_no, business_type, customer_type, registration_status,
                  notes, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (name, mobile, email, gstin, address, city, state, state_code, pin_code,
               vehicle, vehicle_no, business_type, customer_type, reg_status,
               notes, datetime.now().strftime("%d-%m-%Y")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "customers")
    _queue_sync("customers", new_id, "upsert")
    return new_id


def update_customer(customer_id, name, mobile="", email="", gstin="", address="", city="",
                     state="Maharashtra", state_code=None, pin_code="", vehicle="",
                     vehicle_no="", business_type="", customer_type="Retail", notes=""):
    gstin = (gstin or "").strip().upper()
    state_code = state_code or get_state_code_from_name(state) or "27"
    reg_status = "Registered" if is_registered_customer(gstin) else "Unregistered"

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE customers SET
                    name=?, mobile=?, email=?, gstin=?, address=?, city=?, state=?,
                    state_code=?, pin_code=?, vehicle=?, vehicle_no=?, business_type=?,
                    customer_type=?, registration_status=?, notes=?
                 WHERE id=?''',
              (name, mobile, email, gstin, address, city, state, state_code, pin_code,
               vehicle, vehicle_no, business_type, customer_type, reg_status, notes,
               customer_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(customer_id, "customers")
    _queue_sync("customers", customer_id, "upsert")


def archive_customer(customer_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE customers SET is_deleted=1 WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(customer_id, "customers")
    _queue_sync("customers", customer_id, "delete")


def get_customers():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE (is_deleted IS NULL OR is_deleted=0) ORDER BY name COLLATE NOCASE")
    data = c.fetchall()
    conn.close()
    return data


def get_customer_by_id(customer_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE id=?", (customer_id,))
    row = c.fetchone()
    conn.close()
    return row


def search_customers(query):
    if not query or not query.strip():
        return get_customers()
    conn = _get_connection()
    c = conn.cursor()
    like = f"%{query.strip()}%"
    c.execute('''SELECT * FROM customers
                 WHERE (name LIKE ? OR mobile LIKE ? OR gstin LIKE ? OR vehicle_no LIKE ?)
                 AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY name COLLATE NOCASE''', (like, like, like, like))
    data = c.fetchall()
    conn.close()
    return data


def find_customer_by_mobile(mobile):
    digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
    if len(digits) < 4:
        return None
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE (is_deleted IS NULL OR is_deleted=0)")
    rows = c.fetchall()
    conn.close()
    matches = [r for r in rows if r["mobile"] and digits in "".join(ch for ch in r["mobile"] if ch.isdigit())]
    return matches[0] if matches else None


def find_customer_by_gstin(gstin):
    gstin = (gstin or "").strip().upper()
    if not gstin:
        return None
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM customers WHERE gstin=? COLLATE NOCASE
                 AND (is_deleted IS NULL OR is_deleted=0)''', (gstin,))
    row = c.fetchone()
    conn.close()
    return row