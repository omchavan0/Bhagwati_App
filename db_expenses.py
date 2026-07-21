"""
============================================================================
DB EXPENSES — फक्त दुकानाच्या खर्चाशी (Expenses) संबंधित सर्व कोड इथे.
============================================================================
"""
from datetime import datetime

from db_core import _get_connection, _touch_sync_fields, _queue_sync, _safe_sync, _GSHEET_AVAILABLE, get_current_owner_uid, get_current_owner_email, get_device_id
from db_finance import add_transaction, get_transactions_by_reference, delete_transaction

try:
    import gsheet_sync
except Exception:
    gsheet_sync = None

# Expenses टेबलसाठी नवीन कॉलम्स (auto-migration साठी)
EXPENSE_COLUMNS = [
    ("category", "TEXT"),
    ("amount", "REAL DEFAULT 0"),
    ("exp_date", "TEXT"),
    ("notes", "TEXT"),
    ("payment_mode", "TEXT DEFAULT 'Cash'"),
    ("paid_to", "TEXT"),
    ("receipt_no", "TEXT"),
    ("account_id", "INTEGER"),
]


def init_table(conn, c):
    """expenses टेबल तयार/मायग्रेट करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL
                 )''')
    conn.commit()

    c.execute("PRAGMA table_info(expenses)")
    existing_expense_cols = {row[1] for row in c.fetchall()}
    for col_name, col_type in EXPENSE_COLUMNS:
        if col_name not in existing_expense_cols:
            c.execute(f"ALTER TABLE expenses ADD COLUMN {col_name} {col_type}")
    conn.commit()


def add_expense(title, category, amount, exp_date, notes, payment_mode="Cash",
                 paid_to="", receipt_no="", account_id=None):
    """नवीन खर्च सेव्ह करतं. account_id दिला तर त्या खात्यातून आपोआप तेवढी रक्कम
    वजा (debit ledger एन्ट्री) होते — Expense आणि Finance कायम जुळलेले राहतात."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO expenses
                 (title, category, amount, exp_date, notes, payment_mode, paid_to, receipt_no, account_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (title, category, amount, exp_date, notes, payment_mode, paid_to, receipt_no, account_id))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "expenses")
    _queue_sync("expenses", new_id, "upsert")

    if account_id:
        add_transaction(account_id, "debit", amount, category=f"Expense: {title}",
                         tx_date=exp_date, notes=notes,
                         reference_table="expenses", reference_id=new_id)

    _safe_sync(gsheet_sync.sync_expenses, get_expenses()) if _GSHEET_AVAILABLE else None
    return new_id


def _reverse_expense_ledger(record_id):
    """त्या expense शी आधी जोडलेली ledger एन्ट्री (असल्यास) उलटवतो — एडिट/डिलीट
    दोन्ही वेळी वापरतो, जेणेकरून जुनी रक्कम खात्यात 'अडकून' राहणार नाही."""
    for tx in get_transactions_by_reference("expenses", record_id):
        delete_transaction(tx["id"])


def update_expense(record_id, title, category, amount, exp_date, notes,
                    payment_mode="Cash", paid_to="", receipt_no="", account_id=None):
    """आधीचा खर्च एडिट करतं. जुनी ledger एन्ट्री आधी पूर्णपणे उलटवली जाते,
    मग (account निवडला असेल तर) नवीन रकमेसह नवीन एन्ट्री टाकली जाते — यामुळे
    रक्कम/खातं कितीही वेळा बदललं तरी बॅलन्स कधीही दुप्पट किंवा चुकीचा राहत नाही."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE expenses SET title=?, category=?, amount=?, exp_date=?, notes=?,
                    payment_mode=?, paid_to=?, receipt_no=?, account_id=?
                 WHERE id=?''',
              (title, category, amount, exp_date, notes, payment_mode, paid_to,
               receipt_no, account_id, record_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(record_id, "expenses")
    _queue_sync("expenses", record_id, "upsert")

    _reverse_expense_ledger(record_id)
    if account_id:
        add_transaction(account_id, "debit", amount, category=f"Expense: {title}",
                         tx_date=exp_date, notes=notes,
                         reference_table="expenses", reference_id=record_id)

    _safe_sync(gsheet_sync.sync_expenses, get_expenses()) if _GSHEET_AVAILABLE else None


def delete_expense(record_id):
    """खर्च सॉफ्ट-डिलीट करतं आणि त्याच्याशी जोडलेली ledger एन्ट्रीसुद्धा उलटवतो
    (म्हणजे खर्च डिलीट केला की ती रक्कम खात्यात परत जमा दिसेल)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE expenses SET is_deleted=1 WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(record_id, "expenses")
    _queue_sync("expenses", record_id, "delete")

    _reverse_expense_ledger(record_id)

    _safe_sync(gsheet_sync.sync_expenses, get_expenses()) if _GSHEET_AVAILABLE else None

def _touch_sync_fields(record_id, table):
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=?, owner_uid=?, owner_email=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), get_current_owner_uid(),
               get_current_owner_email(), record_id))
    conn.commit()
    conn.close()

def get_expenses():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM expenses WHERE (is_deleted IS NULL OR is_deleted=0) ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data



def get_expense_by_id(record_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM expenses WHERE id=?", (record_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_total_expenses():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE (is_deleted IS NULL OR is_deleted=0)")
    total = c.fetchone()[0]
    conn.close()
    return total


def get_expense_payment_breakdown():
    """Cash / UPI / Bank नुसार खर्चाची बेरीज — Expenses डॅशबोर्डसाठी."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT COALESCE(payment_mode, 'Cash') as mode, COALESCE(SUM(amount), 0) as total
                 FROM expenses WHERE (is_deleted IS NULL OR is_deleted=0) GROUP BY mode''')
    rows = c.fetchall()
    conn.close()
    return {row["mode"]: row["total"] for row in rows}


# ======================================================================
# DAILY WORK — रोजची कामं (कस्टमर, गाडी, काम काय झालं, किती चार्ज, स्टेटस)
# ======================================================================