"""
============================================================================
DB LABOUR — Labour/Service Master (SAC Code + GST सह)
============================================================================
Parts प्रमाणेच पण Labour/Service साठी — यांना stock नसतो, त्यामुळे वेगळं आणि
हलकं टेबल. GST ऑन/ऑफ करता येतो (उदा. काही जुनी/सूट असलेली सर्विस GST शिवाय
बिल करायची असेल तर).
============================================================================
"""
from datetime import datetime

from db_core import _get_connection, get_current_owner_uid, get_current_owner_email, get_device_id, _queue_sync

LABOUR_COLUMNS = [
    ("sac_code", "TEXT DEFAULT '998714'"),
    ("gst_rate", "REAL DEFAULT 18"),
    ("gst_enabled", "INTEGER DEFAULT 1"),
    ("labour_charge", "REAL DEFAULT 0"),
    ("technician", "TEXT"),
    ("description", "TEXT"),
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
    """labour_master टेबल तयार/मायग्रेट करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS labour_master (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    labour_name TEXT NOT NULL
                 )''')
    conn.commit()

    c.execute("PRAGMA table_info(labour_master)")
    existing = {row[1] for row in c.fetchall()}
    for col_name, col_type in LABOUR_COLUMNS:
        if col_name not in existing:
            c.execute(f"ALTER TABLE labour_master ADD COLUMN {col_name} {col_type}")
    conn.commit()


def add_labour(labour_name, sac_code="998714", gst_rate=18, gst_enabled=True,
               labour_charge=0, technician="", description=""):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO labour_master
                 (labour_name, sac_code, gst_rate, gst_enabled, labour_charge,
                  technician, description, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (labour_name, sac_code, gst_rate, 1 if gst_enabled else 0,
               labour_charge, technician, description, datetime.now().strftime("%d-%m-%Y")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "labour_master")
    _queue_sync("labour_master", new_id, "upsert")
    return new_id


def update_labour(labour_id, labour_name, sac_code="998714", gst_rate=18, gst_enabled=True,
                   labour_charge=0, technician="", description=""):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE labour_master SET labour_name=?, sac_code=?, gst_rate=?,
                    gst_enabled=?, labour_charge=?, technician=?, description=?
                 WHERE id=?''',
              (labour_name, sac_code, gst_rate, 1 if gst_enabled else 0,
               labour_charge, technician, description, labour_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(labour_id, "labour_master")
    _queue_sync("labour_master", labour_id, "upsert")


def archive_labour(labour_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE labour_master SET is_deleted=1 WHERE id=?", (labour_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(labour_id, "labour_master")
    _queue_sync("labour_master", labour_id, "delete")


def get_labour_list():
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM labour_master WHERE (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY labour_name COLLATE NOCASE''')
    data = c.fetchall()
    conn.close()
    return data


def get_labour_by_id(labour_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM labour_master WHERE id=?", (labour_id,))
    row = c.fetchone()
    conn.close()
    return row


def search_labour(query):
    if not query or not query.strip():
        return get_labour_list()
    conn = _get_connection()
    c = conn.cursor()
    like = f"%{query.strip()}%"
    c.execute('''SELECT * FROM labour_master
                 WHERE (labour_name LIKE ? OR technician LIKE ?)
                 AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY labour_name COLLATE NOCASE''', (like, like))
    data = c.fetchall()
    conn.close()
    return data