"""
============================================================================
DB CLIENTS — Garage Groups / Clients (एका garage शी अनेक udhaari नोंदी लिंक)
============================================================================
"""
from datetime import datetime, timedelta

from db_core import _get_connection, _touch_sync_fields, _queue_sync, _parse_date, get_current_owner_uid, get_current_owner_email, get_device_id


def init_table(conn, c):
    """clients टेबल तयार करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    garage_name TEXT NOT NULL,
                    owner_name TEXT,
                    mobile TEXT,
                    location TEXT,
                    created_at TEXT
                 )''')
    conn.commit()


def add_client(garage_name, owner_name="", mobile="", location=""):
    """नवीन Garage/Client group बनवतं."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO clients (garage_name, owner_name, mobile, location, created_at)
                 VALUES (?, ?, ?, ?, ?)''',
              (garage_name, owner_name, mobile, location, datetime.now().strftime("%d-%m-%Y")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "clients")
    _queue_sync("clients", new_id, "upsert")
    return new_id


def update_client(client_id, garage_name, owner_name="", mobile="", location=""):
    """आधीचा Client एडिट करतं."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE clients SET garage_name=?, owner_name=?, mobile=?, location=?
                 WHERE id=?''', (garage_name, owner_name, mobile, location, client_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(client_id, "clients")
    _queue_sync("clients", client_id, "upsert")

def _touch_sync_fields(record_id, table):
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=?, owner_uid=?, owner_email=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), get_current_owner_uid(),
               get_current_owner_email(), record_id))
    conn.commit()
    conn.close()
     
def delete_client(client_id):
    """Client सॉफ्ट-डिलीट करतं. त्या client शी लिंक असलेल्या udhaari नोंदी
    डिलीट होत नाहीत — फक्त त्यांचा client_id रिकामा होतो."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE udhaari SET client_id=NULL WHERE client_id=?", (client_id,))
    c.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (client_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(client_id, "clients")
    _queue_sync("clients", client_id, "delete")


def get_clients():
    """सर्व Clients (Garage नावानुसार क्रमाने) परत देतं."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM clients WHERE (is_deleted IS NULL OR is_deleted=0) ORDER BY garage_name COLLATE NOCASE")
    data = c.fetchall()
    conn.close()
    return data


def get_client_by_id(client_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM clients WHERE id=?", (client_id,))
    row = c.fetchone()
    conn.close()
    return row


def search_clients(query):
    """Garage नाव, Owner नाव किंवा मोबाईलमध्ये query शोधतं."""
    if not query or not query.strip():
        return get_clients()
    conn = _get_connection()
    c = conn.cursor()
    like = f"%{query.strip()}%"
    c.execute('''SELECT * FROM clients
                 WHERE (garage_name LIKE ? OR owner_name LIKE ? OR mobile LIKE ?)
                 AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY garage_name COLLATE NOCASE''', (like, like, like))
    data = c.fetchall()
    conn.close()
    return data


def get_client_profile(client_id, days=30):
    """एका Client (Garage) चा संपूर्ण हिसाब: सगळ्या नोंदी (all-time totals),
    गेल्या N दिवसांतलं काम वेगळं, आणि सगळ्या वेगळ्या गाड्या."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM clients WHERE id=?", (client_id,))
    client = c.fetchone()
    if not client:
        conn.close()
        return None

    c.execute("SELECT * FROM udhaari WHERE client_id=? AND (is_deleted IS NULL OR is_deleted=0) ORDER BY id DESC", (client_id,))
    all_records = c.fetchall()
    conn.close()

    cutoff = datetime.now() - timedelta(days=days)
    recent_records = []
    for r in all_records:
        parsed = _parse_date(r["tx_date"])
        if parsed is not None and parsed >= cutoff:
            recent_records.append(r)

    total_amt = sum((r["total_amt"] or 0) for r in all_records)
    total_paid = sum((r["paid_amt"] or 0) for r in all_records)
    total_due = sum((r["due_amt"] or 0) for r in all_records)

    vehicles = sorted({
        f"{r['vehicle']} ({r['vehicle_no']})" if r["vehicle_no"] else r["vehicle"]
        for r in all_records if r["vehicle"]
    })

    return {
        "id": client["id"],
        "garage_name": client["garage_name"],
        "owner_name": client["owner_name"],
        "mobile": client["mobile"],
        "location": client["location"],
        "vehicles": vehicles,
        "total_amt": total_amt,
        "total_paid": total_paid,
        "total_due": total_due,
        "record_count": len(all_records),
        "recent_records": recent_records,
        "recent_days": days,
        "all_records": all_records,
    }