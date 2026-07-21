"""
============================================================================
DB CORE — शेअर होणारे पाया: connection, cloud-sync helpers, backup, PIN, session
============================================================================
हे सगळ्या db_*.py मॉड्यूल्सनी वापरायचं common टूलकिट आहे. इथे कुठलंच टेबल
(udhaari/expenses/daily_work/clients) directly हाताळलं जात नाही — फक्त
शेअर होणारे बिल्डिंग-ब्लॉक्स आहेत. यामुळे एका टेबलमध्ये बदल केला की दुसऱ्या
टेबलचा कोड कधीही तुटत नाही (isolation).
============================================================================
"""
import sqlite3
import shutil
import os
import glob
import uuid
from datetime import datetime, timedelta







# सर्व मुख्य टेबल्सना cloud-sync साठी लागणारे कॉमन कॉलम्स
SYNC_COLUMNS = [
    ("updated_at", "TEXT"),
    ("device_id", "TEXT"),
    ("is_deleted", "INTEGER DEFAULT 0"),
    ("owner_uid", "TEXT"),    # कोणत्या Firebase account ने ही नोंद केली (UID)
    ("owner_email", "TEXT"),  # 👈 नवीन — त्याच account चा Gmail/Email (माणसाला लगेच वाचता यावा म्हणून)
]

def get_current_owner_uid():
    """सध्या login असलेल्या account चा uid — auth_service कडून."""
    try:
        import auth_service
        session = auth_service.get_saved_session()
        return session["uid"] if session else None
    except Exception:
        return None


def get_current_owner_email():
    """सध्या login असलेल्या account चा email — auth_service कडून. यामुळे
    प्रत्येक रेकॉर्डवर 'कोणी (कोणत्या Gmail ने) ही एन्ट्री केली' हे uid
    सोबतच माणसाला लगेच वाचता येईल असं (email) स्वरूपातही दिसतं."""
    try:
        import auth_service
        session = auth_service.get_saved_session()
        return session["email"] if session else None
    except Exception:
        return None

# Cloud sync सह टेबल्सची यादी — outbox आणि pull-merge दोन्हीसाठी वापरतात
# Cloud sync सह टेबल्सची यादी — outbox आणि pull-merge दोन्हीसाठी वापरतात
SYNCED_TABLES = ["udhaari", "expenses", "daily_work", "clients", "accounts", "account_transactions",
                  "parts", "stock_ledger", "part_usage", "customers", "labour_master",
                  "suppliers", "purchase_bills", "purchase_items", "stock_in_entries"]
# Google Sheets sync — पूर्णपणे optional. import फेल झाला तरी (library
# install नसेल तर) बाकी app वर काहीही परिणाम होत नाही.
# Google Sheets sync — पूर्णपणे optional. import फेल झाला तरी (library
# install नसेल तर) बाकी app वर काहीही परिणाम होत नाही.
try:
    import gsheet_sync
    _GSHEET_AVAILABLE = True
except Exception:
    _GSHEET_AVAILABLE = False


def _safe_sync(sync_func, records):
    """Sync कॉल कधीही exception raise करणार नाही याची खात्री करणारा wrapper."""
    if not _GSHEET_AVAILABLE:
        return
    try:
        sync_func(records)
    except Exception:
        pass  # sync मध्ये काहीही चुकलं तरी मुख्य app वर परिणाम नको

DB_NAME = "bhagwati.db"
BACKUP_DIR = "backups"
BACKUP_KEEP_DAYS = 30  # यापेक्षा जुने बॅकअप्स आपोआप काढले जातील


def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # नाव वापरून column access करता येण्यासाठी
    return conn


def init_db():
    """ॲप सुरू होताना एकदाच कॉल करायचं. प्रत्येक db_*.py मॉड्यूलला त्याचं
    स्वतःचं टेबल तयार/मायग्रेट करायला सांगतो (isolation raखण्यासाठी लेझी
    import — यामुळे circular-import चा प्रश्न येत नाही)."""
    import db_udhaari, db_expenses, db_work, db_clients, db_finance, db_inventory, db_company, db_customers, db_labour, db_suppliers, db_purchase, db_stock_in
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # ------ Settings टेबल (PIN, session, sync-metadata साठी key-value) ------
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                 )''')
    conn.commit()

    # ------ Login History — कोणी, कधी, कोणत्या डिव्हाइसवरून Login केलं/
    #        प्रयत्न केला (Fail झाला तर कारणासकट) याचा कायमचा रेकॉर्ड ------
    c.execute('''CREATE TABLE IF NOT EXISTS login_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT,
                    uid TEXT,
                    status TEXT,
                    reason TEXT,
                    device_id TEXT,
                    created_at TEXT
                 )''')
    conn.commit()

    # ------ प्रत्येक मॉड्यूल स्वतःचं टेबल तयार/मायग्रेट करतो ------
    db_udhaari.init_table(conn, c)
    db_expenses.init_table(conn, c)
    db_work.init_table(conn, c)
    db_clients.init_table(conn, c)
    db_finance.init_table(conn, c)
    db_inventory.init_table(conn, c)
    db_company.init_table(conn, c) 
    db_customers.init_table(conn, c)  # 👈 नवीन ओळ
    db_labour.init_table(conn, c)  # 👈 नवीन ओळ
    db_suppliers.init_table(conn, c)   # 👈 नवीन
    db_purchase.init_table(conn, c)
    db_stock_in.init_table(conn, c)
    db_inventory.init_categories_table(conn, c)     # 👈 नवीन
    conn.commit()
    

    # ------ Cloud-sync columns (updated_at, device_id, is_deleted) प्रत्येक
    #        मुख्य टेबलमध्ये मिसिंग असतील तर ॲड करणे ------
    for table in SYNCED_TABLES:
        c.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in c.fetchall()}
        for col_name, col_type in SYNC_COLUMNS:
            if col_name not in existing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    conn.commit()

    # ------ Sync Outbox — इंटरनेट नसताना झालेले बदल तात्पुरते साठवण्यासाठी ------
    c.execute('''CREATE TABLE IF NOT EXISTS sync_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    record_id INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    created_at TEXT
                 )''')
    conn.commit()
    conn.close()

    auto_backup()  # ॲप सुरू होताना आजचा बॅकअप अजून नसेल तर घे


# ======================================================================
# CLOUD SYNC HELPERS — device_id, outbox queue, remote merge (last-write-wins)
# ======================================================================

def get_device_id():
    """या डिव्हाइसचा कायमचा युनिक ID (पहिल्यांदाच तयार होतो, नंतर settings मध्ये साठतो)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='device_id'")
    row = c.fetchone()
    if row:
        conn.close()
        return row["value"]
    new_id = str(uuid.uuid4())[:8]
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('device_id', ?)", (new_id,))
    conn.commit()
    conn.close()
    return new_id


def _queue_sync(table_name, record_id, operation="upsert"):
    """एक बदल (add/update/delete) outbox मध्ये नोंदतो — sync_engine नंतर हे
    Firestore वर पाठवतो. इंटरनेट नसलं तरी हे लगेच होतं (Offline-first)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO sync_outbox (table_name, record_id, operation, created_at)
                 VALUES (?, ?, ?, ?)''',
              (table_name, record_id, operation, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def _touch_sync_fields(record_id, table):
    """updated_at आणि device_id सेट करतं — प्रत्येक write च्या वेळी कॉल होतं,
    जेणेकरून दुसऱ्या डिव्हाइसवर last-write-wins तपासता येईल."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), record_id))
    conn.commit()
    conn.close()


def get_pending_outbox(limit=100):
    """अजून cloud वर न पाठवलेले बदल परत देतं (sync_engine वापरतं)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM sync_outbox ORDER BY id ASC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def clear_outbox_entry(outbox_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sync_outbox WHERE id=?", (outbox_id,))
    conn.commit()
    conn.close()


def get_row_as_dict(table, record_id):
    """एका रेकॉर्डचं संपूर्ण row Python dict म्हणून परत देतं (Firestore ला पाठवण्यासाठी)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def apply_remote_change(table, data):
    """दुसऱ्या डिव्हाइसवरून आलेला बदल local SQLite मध्ये merge करतं.
    Conflict असेल (दोन्हीकडे तोच रेकॉर्ड बदलला असेल) तर ज्याचा updated_at
    सगळ्यात नवीन आहे तोच जिंकतो (Last-Write-Wins) — यामुळे Udhaari/Stock/
    Account बॅलन्स कधीही विसंगत (corrupt) होत नाहीत."""
    if not data or "id" not in data:
        return

    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"SELECT updated_at FROM {table} WHERE id=?", (data["id"],))
    local = c.fetchone()

    remote_time = data.get("updated_at") or ""
    if local is not None:
        local_time = local["updated_at"] or ""
        if local_time >= remote_time:
            conn.close()
            return  # लोकल डेटा आधीच नवीन/सारखा आहे — काही करायची गरज नाही

    cols = [k for k in data.keys() if k != "id"]
    placeholders = ", ".join(f"{col}=?" for col in cols)
    values = [data[col] for col in cols]

    if local is not None:
        c.execute(f"UPDATE {table} SET {placeholders} WHERE id=?", values + [data["id"]])
    else:
        all_cols = ["id"] + cols
        q_marks = ", ".join(["?"] * len(all_cols))
        c.execute(f"INSERT INTO {table} ({', '.join(all_cols)}) VALUES ({q_marks})",
                  [data["id"]] + values)

    conn.commit()
    conn.close()


def get_last_sync_time():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='last_sync_time'")
    row = c.fetchone()
    conn.close()
    return row["value"] if row else None


def set_last_sync_time(iso_time):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync_time', ?)", (iso_time,))
    conn.commit()
    conn.close()



def _parse_date(date_str):
    """DD.MM.YYYY किंवा DD-MM-YYYY किंवा YYYY-MM-DD फॉरमॅट ओळखून parse करतं."""
    date_str = (date_str or "").strip()
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None



# ======================================================================
# AUTO-BACKUP — रोजचा पहिला backup आपोआप, + जुने backups साफ करणे
# ======================================================================

def _backup_filename_for_today():
    today_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(BACKUP_DIR, f"bhagwati_backup_{today_str}.db")


def auto_backup():
    """आजचा backup अजून घेतलेला नसेल तरच घेतो (दिवसातून एकदाच).
    DB फाईल नसेल (अजून काही सेव्ह झालं नसेल) तर काही करत नाही."""
    if not os.path.exists(DB_NAME):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    today_backup = _backup_filename_for_today()

    if not os.path.exists(today_backup):
        try:
            shutil.copy2(DB_NAME, today_backup)
        except Exception:
            return None  # बॅकअप फेल झाला तरी ॲप सुरू व्हायला अडथळा नको

    _cleanup_old_backups()
    return today_backup


def manual_backup():
    """यूजरने स्वतः "Backup Now" दाबल्यावर लगेच एक नवीन backup (टाईमस्टॅम्पसह) घेतो."""
    if not os.path.exists(DB_NAME):
        raise FileNotFoundError("अजून डेटाबेस फाईलच तयार झालेली नाही.")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"bhagwati_backup_{stamp}.db")
    shutil.copy2(DB_NAME, backup_path)
    _cleanup_old_backups()
    return backup_path


def _cleanup_old_backups():
    """ठरवलेल्या दिवसांपेक्षा जुने backups आपोआप काढतो, जेणेकरून जागा वाचेल."""
    if not os.path.isdir(BACKUP_DIR):
        return

    cutoff = datetime.now() - timedelta(days=BACKUP_KEEP_DAYS)
    for filepath in glob.glob(os.path.join(BACKUP_DIR, "bhagwati_backup_*.db")):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if mtime < cutoff:
                os.remove(filepath)
        except Exception:
            pass  # एका फाईलमध्ये अडचण आली तरी बाकीच्या साफ करत राहायचं


def list_backups():
    """सर्व उपलब्ध backups (नवीन आधी) यांची यादी परत देतं, तारीख आणि साईज सोबत."""
    if not os.path.isdir(BACKUP_DIR):
        return []

    files = glob.glob(os.path.join(BACKUP_DIR, "bhagwati_backup_*.db"))
    files.sort(key=os.path.getmtime, reverse=True)

    result = []
    for f in files:
        result.append({
            "path": f,
            "name": os.path.basename(f),
            "modified": datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d-%m-%Y %H:%M"),
            "size_kb": round(os.path.getsize(f) / 1024, 1),
        })
    return result


def restore_backup(backup_path):
    """निवडलेल्या backup मधून सध्याचा डेटाबेस परत आणतो.
    सुरक्षेसाठी, restore करण्यापूर्वी सध्याच्या डेटाबेसचाही एक backup घेतो."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError("ती backup फाईल सापडली नाही.")

    if os.path.exists(DB_NAME):
        manual_backup()  # restore च्या आधी सध्याची स्थिती सुरक्षित ठेव

    shutil.copy2(backup_path, DB_NAME)


# ======================================================================
# LOCAL SESSION — Login झाल्यावर पुन्हा पुन्हा लॉगिन करावं लागू नये म्हणून
# ======================================================================
import json as _json



def save_local_session(uid, email, display_name="", mobile=""):
    conn = _get_connection()
    c = conn.cursor()
    session = _json.dumps({"uid": uid, "email": email, "display_name": display_name, "mobile": mobile})
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_session', ?)", (session,))
    conn.commit()
    conn.close()


def get_local_session():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='user_session'")
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    try:
        return _json.loads(row["value"])
    except Exception:
        return None


def clear_local_session():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM settings WHERE key='user_session'")
    conn.commit()
    conn.close()


# ======================================================================
# LOGIN HISTORY — कोण Login झालं, कधी, आणि Fail झालं तर का ते ट्रॅक करणे
# ======================================================================
def log_login_event(email, status, reason="", uid=None):
    """प्रत्येक Login/Signup प्रयत्नाची नोंद — status: 'success' किंवा 'failed'.
    auth_service.py च्या login()/sign_up() मधून कॉल होतं. यामुळे Om ला नंतर
    कधीही बघता येईल — कोण Login झालं, आणि कुणाला Password चुकीचा/काही
    प्रॉब्लेम आला तर तो नेमका कधी आणि कशामुळे आला."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO login_history (email, uid, status, reason, device_id, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              ((email or "").strip(), uid, status, reason, get_device_id(), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_login_history(limit=200):
    """अलीकडचे Login attempts (नवीन आधी) — यशस्वी आणि अयशस्वी दोन्ही."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM login_history ORDER BY id DESC LIMIT ?", (limit,))
    data = c.fetchall()
    conn.close()
    return data


# ======================================================================
# PIN LOCK — settings टेबलमध्ये hashed PIN साठवणं
# ======================================================================
import hashlib


def _hash_pin(pin):
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def set_pin(pin):
    """नवीन PIN सेट करतो किंवा बदलतो (hash करून साठवतो, plain text नाही)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('app_pin', ?)", (_hash_pin(pin),))
    conn.commit()
    conn.close()


def verify_pin(pin):
    """दिलेला PIN बरोबर आहे का ते तपासतो."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='app_pin'")
    row = c.fetchone()
    conn.close()
    if row is None:
        return False
    return row["value"] == _hash_pin(pin)


def is_pin_set():
    """PIN आधीच सेट केलेला आहे का ते सांगतो."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='app_pin'")
    row = c.fetchone()
    conn.close()
    return row is not None


def remove_pin():
    """PIN लॉक पूर्णपणे बंद करतो."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM settings WHERE key='app_pin'")
    conn.commit()
    conn.close()


# ======================================================================
# EXPENSES — दुकानाचा रोजचा खर्च (भाडे, वायरिंग सामान, चहा-पाणी, इ.)
# ======================================================================