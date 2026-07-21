"""
============================================================================
DB SUPPLIERS — Supplier / Vendor Master (Purchase साठी)
============================================================================
db_customers.py च्याच पॅटर्नवर — पण इथे "आपण कुणाकडून खरेदी करतो" अशी माहिती
असते. Registered/Unregistered आपोआप GSTIN वरून ठरतो (gst_utils वापरून).
============================================================================
"""
from datetime import datetime

from db_core import _get_connection, _queue_sync, get_current_owner_uid, get_current_owner_email, get_device_id
from gst_utils import is_registered_customer, get_state_code_from_name

SUPPLIER_COLUMNS = [
    ("mobile", "TEXT"),
    ("email", "TEXT"),
    ("gstin", "TEXT"),
    ("address", "TEXT"),
    ("city", "TEXT"),
    ("state", "TEXT DEFAULT 'Maharashtra'"),
    ("state_code", "TEXT DEFAULT '27'"),
    ("pin_code", "TEXT"),
    ("business_type", "TEXT"),
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
    """suppliers टेबल तयार/मायग्रेट करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL
                 )''')
    conn.commit()

    c.execute("PRAGMA table_info(suppliers)")
    existing = {row[1] for row in c.fetchall()}
    for col_name, col_type in SUPPLIER_COLUMNS:
        if col_name not in existing:
            c.execute(f"ALTER TABLE suppliers ADD COLUMN {col_name} {col_type}")
    conn.commit()


def add_supplier(name, mobile="", email="", gstin="", address="", city="",
                  state="Maharashtra", state_code=None, pin_code="",
                  business_type="", notes=""):
    gstin = (gstin or "").strip().upper()
    state_code = state_code or get_state_code_from_name(state) or "27"
    reg_status = "Registered" if is_registered_customer(gstin) else "Unregistered"

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO suppliers
                 (name, mobile, email, gstin, address, city, state, state_code,
                  pin_code, business_type, registration_status, notes, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (name, mobile, email, gstin, address, city, state, state_code,
               pin_code, business_type, reg_status, notes, datetime.now().strftime("%d-%m-%Y")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "suppliers")
    _queue_sync("suppliers", new_id, "upsert")
    return new_id


def update_supplier(supplier_id, name, mobile="", email="", gstin="", address="", city="",
                     state="Maharashtra", state_code=None, pin_code="",
                     business_type="", notes=""):
    gstin = (gstin or "").strip().upper()
    state_code = state_code or get_state_code_from_name(state) or "27"
    reg_status = "Registered" if is_registered_customer(gstin) else "Unregistered"

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE suppliers SET
                    name=?, mobile=?, email=?, gstin=?, address=?, city=?, state=?,
                    state_code=?, pin_code=?, business_type=?, registration_status=?, notes=?
                 WHERE id=?''',
              (name, mobile, email, gstin, address, city, state, state_code,
               pin_code, business_type, reg_status, notes, supplier_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(supplier_id, "suppliers")
    _queue_sync("suppliers", supplier_id, "upsert")


def archive_supplier(supplier_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE suppliers SET is_deleted=1 WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(supplier_id, "suppliers")
    _queue_sync("suppliers", supplier_id, "delete")


def get_suppliers():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM suppliers WHERE (is_deleted IS NULL OR is_deleted=0) ORDER BY name COLLATE NOCASE")
    data = c.fetchall()
    conn.close()
    return data


def get_supplier_by_id(supplier_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,))
    row = c.fetchone()
    conn.close()
    return row


def search_suppliers(query):
    if not query or not query.strip():
        return get_suppliers()
    conn = _get_connection()
    c = conn.cursor()
    like = f"%{query.strip()}%"
    c.execute('''SELECT * FROM suppliers
                 WHERE (name LIKE ? OR mobile LIKE ? OR gstin LIKE ?)
                 AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY name COLLATE NOCASE''', (like, like, like))
    data = c.fetchall()
    conn.close()
    return data