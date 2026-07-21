"""
============================================================================
DB WORK — रोजची कामं (Daily Work Log): कस्टमर, गाडी, काम काय झालं, चार्ज
============================================================================
"""
from datetime import datetime

from db_core import _get_connection, _touch_sync_fields, _queue_sync, _safe_sync, _GSHEET_AVAILABLE, get_current_owner_uid, get_current_owner_email, get_device_id

try:
    import gsheet_sync
except Exception:
    gsheet_sync = None

WORK_COLUMNS = [
    ("vehicle", "TEXT"),
    ("work_desc", "TEXT"),
    ("charge_amt", "REAL DEFAULT 0"),
    ("work_date", "TEXT"),
    ("status", "TEXT DEFAULT 'Pending'"),
    ("mobile", "TEXT"),
    ("vehicle_no", "TEXT"),
    ("labour_charge", "REAL DEFAULT 0"),
    ("parts_charge", "REAL DEFAULT 0"),
    ("parts_used", "TEXT"),
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
    """daily_work टेबल तयार/मायग्रेट करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS daily_work (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT NOT NULL
                 )''')
    conn.commit()
    c.execute("PRAGMA table_info(daily_work)")
    existing = {row[1] for row in c.fetchall()}
    for col_name, col_type in WORK_COLUMNS:
        if col_name not in existing:
            c.execute(f"ALTER TABLE daily_work ADD COLUMN {col_name} {col_type}")
    conn.commit()


def add_work(customer_name, vehicle, work_desc, charge_amt, work_date, status,
             mobile="", vehicle_no="", labour_charge=0, parts_charge=0, parts_used=""):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO daily_work
                 (customer_name, vehicle, work_desc, charge_amt, work_date, status,
                  mobile, vehicle_no, labour_charge, parts_charge, parts_used)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (customer_name, vehicle, work_desc, charge_amt, work_date, status,
               mobile, vehicle_no, labour_charge, parts_charge, parts_used))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "daily_work")
    _queue_sync("daily_work", new_id, "upsert")
    _safe_sync(gsheet_sync.sync_daily_work, get_daily_work()) if _GSHEET_AVAILABLE else None
    return new_id


def update_work(record_id, customer_name, vehicle, work_desc, charge_amt, work_date, status,
                 mobile="", vehicle_no="", labour_charge=0, parts_charge=0, parts_used=""):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE daily_work SET customer_name=?, vehicle=?, work_desc=?,
                    charge_amt=?, work_date=?, status=?, mobile=?, vehicle_no=?,
                    labour_charge=?, parts_charge=?, parts_used=?
                 WHERE id=?''',
              (customer_name, vehicle, work_desc, charge_amt, work_date, status,
               mobile, vehicle_no, labour_charge, parts_charge, parts_used, record_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(record_id, "daily_work")
    _queue_sync("daily_work", record_id, "upsert")
    _safe_sync(gsheet_sync.sync_daily_work, get_daily_work()) if _GSHEET_AVAILABLE else None


def delete_work(record_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE daily_work SET is_deleted=1 WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(record_id, "daily_work")
    _queue_sync("daily_work", record_id, "delete")
    _safe_sync(gsheet_sync.sync_daily_work, get_daily_work()) if _GSHEET_AVAILABLE else None


def get_daily_work():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM daily_work WHERE (is_deleted IS NULL OR is_deleted=0) ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data


def get_work_by_id(record_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM daily_work WHERE id=?", (record_id,))
    row = c.fetchone()
    conn.close()
    return row


def toggle_work_status(record_id):
    """Pending → In Progress → Done → Pending असं cycle करतो."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM daily_work WHERE id=?", (record_id,))
    row = c.fetchone()
    if row:
        cycle = {"Pending": "In Progress", "In Progress": "Done", "Done": "Pending"}
        new_status = cycle.get(row["status"] or "Pending", "Pending")
        c.execute("UPDATE daily_work SET status=? WHERE id=?", (new_status, record_id))
        conn.commit()
    conn.close()