"""
============================================================================
DB FINANCE — Accounts (Cash/Bank/UPI) + Ledger-based Balance Tracking
============================================================================
DESIGN — का Balance हा साठवलेला नंबर नाहीये:

चुकीचा मार्ग: accounts.balance नावाचा कॉलम ठेवून, प्रत्येक transaction च्या
वेळी तो +/- करत राहणे. Multi-device sync मध्ये हे प्रचंड धोकादायक आहे —
दोन डिव्हाइसेसवर वेगवेगळे transactions एकाच वेळी झाले, तर "last-write-wins"
मुळे एक बदल पूर्णपणे हरवून जातो आणि बॅलन्स कायमचा चुकतो.

बरोबर मार्ग (हेच वापरलंय): "Ledger Pattern" — प्रत्येक transaction हा एक
स्वतंत्र, अपरिवर्तनीय (immutable) रेकॉर्ड म्हणून साठवला जातो. Balance
कधीही आधीपासून साठवला जात नाही — तो नेहमी "सगळ्या credit वजा सगळ्या debit"
अशी बेरीज करून, त्या क्षणी लाइव्ह काढला जातो. यामुळे कितीही डिव्हाइसेसवरून
कितीही transactions sync झाले तरी बॅलन्स गणिती दृष्ट्या नेहमी बरोबर राहतो
(counter sync करणं चुकीचं, event/ledger sync करणं बरोबर — हे standard
accounting/banking सिस्टीम्स सुद्धा असंच करतात).
============================================================================
"""
import uuid
from datetime import datetime

from db_core import _get_connection, _touch_sync_fields, _queue_sync, get_current_owner_uid, get_current_owner_email, get_device_id

ACCOUNT_TYPES = ["Cash", "Bank", "UPI", "Cheque", "Other"]


def init_table(conn, c):
    """accounts + account_transactions टेबल्स तयार/मायग्रेट करतं —
    db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    account_type TEXT DEFAULT 'Cash',
                    notes TEXT,
                    created_at TEXT
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS account_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    entry_type TEXT NOT NULL,
                    amount REAL DEFAULT 0,
                    category TEXT,
                    reference_table TEXT,
                    reference_id INTEGER,
                    transfer_pair_id TEXT,
                    notes TEXT,
                    tx_date TEXT,
                    created_at TEXT
                 )''')
    conn.commit()


# ======================================================================
# ACCOUNTS — CRUD
# ======================================================================

def add_account(name, account_type="Cash", opening_balance=0.0, notes=""):
    """नवीन खातं (Cash/Bank/UPI) बनवतं. Opening balance स्वतंत्र कॉलम म्हणून
    साठवत नाही — त्याऐवजी एक 'Opening Balance' नावाची पहिली ledger एन्ट्री
    टाकतो, जेणेकरून बॅलन्स कायम एकाच जागेवरून (ledger) मोजला जाईल."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO accounts (name, account_type, notes, created_at)
                 VALUES (?, ?, ?, ?)''',
              (name, account_type, notes, datetime.now().strftime("%d-%m-%Y")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "accounts")
    _queue_sync("accounts", new_id, "upsert")

    opening_balance = float(opening_balance or 0)
    if opening_balance != 0:
        entry_type = "credit" if opening_balance > 0 else "debit"
        add_transaction(new_id, entry_type, abs(opening_balance), category="Opening Balance",
                         tx_date=datetime.now().strftime("%d-%m-%Y"), notes="सुरुवातीची शिल्लक")

    return new_id


def update_account(account_id, name, account_type="Cash", notes=""):
    """नाव/प्रकार/नोट्स एडिट करतं. (Opening balance परत बदलता येत नाही —
    बॅलन्स बदलायचा असेल तर Deposit/Withdraw एन्ट्री टाक, म्हणजे इतिहास
    (audit trail) सुरक्षित राहतो.)"""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET name=?, account_type=?, notes=? WHERE id=?",
              (name, account_type, notes, account_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(account_id, "accounts")
    _queue_sync("accounts", account_id, "upsert")


def archive_account(account_id):
    """खातं आर्काइव्ह (सॉफ्ट-डिलीट) करतं — जुने transactions/history सुरक्षित
    राहतात, फक्त नवीन व्यवहारांसाठी dropdown मधून गायब होतं."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET is_deleted=1 WHERE id=?", (account_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(account_id, "accounts")
    _queue_sync("accounts", account_id, "delete")


def get_accounts():
    """सर्व सक्रिय (आर्काइव्ह न केलेली) खाती नावानुसार क्रमाने परत देतं."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE (is_deleted IS NULL OR is_deleted=0) ORDER BY name COLLATE NOCASE")
    data = c.fetchall()
    conn.close()
    return data


def get_account_by_id(account_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE id=?", (account_id,))
    row = c.fetchone()
    conn.close()
    return row


# ======================================================================
# LEDGER — Balance नेहमी इथूनच लाइव्ह मोजला जातो
# ======================================================================

def get_account_balance(account_id):
    """एका खात्याचा सध्याचा बॅलन्स — सगळ्या credit वजा सगळ्या debit (लाइव्ह गणित,
    कुठलाही साठवलेला counter वापरत नाही)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT COALESCE(SUM(CASE WHEN entry_type='credit' THEN amount ELSE -amount END), 0)
                 FROM account_transactions
                 WHERE account_id=? AND (is_deleted IS NULL OR is_deleted=0)''', (account_id,))
    balance = c.fetchone()[0]
    conn.close()
    return balance


def get_all_account_balances():
    """सर्व खाती + प्रत्येकाचा live बॅलन्स + सगळ्यांची एकूण बेरीज."""
    accounts = get_accounts()
    result = []
    grand_total = 0.0
    for acc in accounts:
        bal = get_account_balance(acc["id"])
        grand_total += bal
        result.append({
            "id": acc["id"],
            "name": acc["name"],
            "account_type": acc["account_type"],
            "notes": acc["notes"],
            "balance": bal,
        })
    return {"accounts": result, "grand_total": grand_total}


def add_transaction(account_id, entry_type, amount, category="Manual", tx_date="", notes="",
                     reference_table=None, reference_id=None):
    """एक साधी Deposit ('credit') किंवा Withdraw ('debit') एन्ट्री टाकतो.
    reference_table/reference_id दिलं तर ही एन्ट्री दुसऱ्या रेकॉर्डशी (उदा.
    Udhaari पेमेंट, Expense) जोडलेली आहे हे कळतं."""
    if entry_type not in ("credit", "debit"):
        raise ValueError("entry_type फक्त 'credit' किंवा 'debit' असू शकतो")
    if amount is None or float(amount) <= 0:
        raise ValueError("Amount शून्यापेक्षा जास्त असावी")

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO account_transactions
                 (account_id, entry_type, amount, category, reference_table,
                  reference_id, transfer_pair_id, notes, tx_date, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (account_id, entry_type, float(amount), category, reference_table,
               reference_id, None, notes, tx_date, datetime.now().isoformat()))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "account_transactions")
    _queue_sync("account_transactions", new_id, "upsert")
    return new_id


def record_transfer(from_account_id, to_account_id, amount, tx_date="", notes=""):
    """एका खात्यातून दुसऱ्या खात्यात पैसे ट्रान्सफर — Double-entry पद्धतीने:
    एक 'debit' (from) + एक 'credit' (to), दोन्ही एकाच transfer_pair_id ने
    जोडलेल्या (एकत्र दिसण्यासाठी/एकत्र डिलीट होण्यासाठी). दोन्ही एन्ट्री एकाच
    वेळी, एकाच local commit मध्ये होतात — त्यामुळे अर्धवट transfer कधीच होत नाही."""
    if from_account_id == to_account_id:
        raise ValueError("⚠️ एकाच खात्यात ट्रान्सफर करता येत नाही.")
    if amount is None or float(amount) <= 0:
        raise ValueError("⚠️ Amount शून्यापेक्षा जास्त असावी.")

    amount = float(amount)
    pair_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO account_transactions
                 (account_id, entry_type, amount, category, reference_table,
                  reference_id, transfer_pair_id, notes, tx_date, created_at)
                 VALUES (?, 'debit', ?, 'Transfer Out', NULL, NULL, ?, ?, ?, ?)''',
              (from_account_id, amount, pair_id, notes, tx_date, now))
    out_id = c.lastrowid

    c.execute('''INSERT INTO account_transactions
                 (account_id, entry_type, amount, category, reference_table,
                  reference_id, transfer_pair_id, notes, tx_date, created_at)
                 VALUES (?, 'credit', ?, 'Transfer In', NULL, NULL, ?, ?, ?, ?)''',
              (to_account_id, amount, pair_id, notes, tx_date, now))
    in_id = c.lastrowid

    conn.commit()
    conn.close()

    _touch_sync_fields(out_id, "account_transactions")
    _queue_sync("account_transactions", out_id, "upsert")
    _touch_sync_fields(in_id, "account_transactions")
    _queue_sync("account_transactions", in_id, "upsert")

    return out_id, in_id


def get_transaction_by_id(tx_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM account_transactions WHERE id=?", (tx_id,))
    row = c.fetchone()
    conn.close()
    return row

def _touch_sync_fields(record_id, table):
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=?, owner_uid=?, owner_email=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), get_current_owner_uid(),
               get_current_owner_email(), record_id))
    conn.commit()
    conn.close()
    
def update_transaction(tx_id, amount=None, category=None, tx_date=None, notes=None):
    """फक्त मॅन्युअली टाकलेली Deposit/Withdraw एन्ट्री सुरक्षितपणे एडिट करतं.

    जाणूनबुजून खालच्या दोन प्रकारच्या एन्ट्रीजना ब्लॉक करतं (इथून एडिट केलं
    तर दुसरीकडे (Sale/Expense/Transfer) चा हिशोब आणि हे Account चुकीचं
    जुळेल — त्यामुळे एडिट नेहमी 'मूळ' स्क्रीनवरूनच व्हायला हवं):
      - reference_table असलेली (उदा. Sale/Expense कडून आपोआप आलेली एन्ट्री)
      - transfer_pair_id असलेली (Transfer ची एक बाजू — दोन्ही बाजू सोबतच बदलाव्या लागतील)

    Raises:
        ValueError: एन्ट्री सापडली नाही, किंवा ती auto-generated/transfer असेल तर
    """
    row = get_transaction_by_id(tx_id)
    if not row:
        raise ValueError("⚠️ ही एन्ट्री सापडली नाही.")
    if row["reference_table"]:
        raise ValueError(
            f"⚠️ ही एन्ट्री '{row['reference_table']}' मधून आपोआप आलेली आहे — "
            "ती तिथूनच (Sale/Expense एडिट करून) बदलावी लागेल."
        )
    if row["transfer_pair_id"]:
        raise ValueError("⚠️ ही Transfer ची एक बाजू आहे — Transfer एडिट करता येत नाही, नवीन करा.")

    new_amount = float(amount) if amount is not None else row["amount"]
    if new_amount <= 0:
        raise ValueError("⚠️ Amount शून्यापेक्षा जास्त असावी.")

    new_category = category if category is not None else row["category"]
    new_tx_date = tx_date if tx_date is not None else row["tx_date"]
    new_notes = notes if notes is not None else row["notes"]

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE account_transactions SET amount=?, category=?, tx_date=?, notes=?
                 WHERE id=?''', (new_amount, new_category, new_tx_date, new_notes, tx_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(tx_id, "account_transactions")
    _queue_sync("account_transactions", tx_id, "upsert")


def delete_transaction(tx_id):
    """एक transaction सॉफ्ट-डिलीट करतं. जर ती Transfer ची एक बाजू असेल, तर
    दोन्ही बाजू (from + to) एकत्रच डिलीट होतात — नाहीतर एका खात्यातून पैसे
    गायब पण दुसऱ्या खात्यात परत आले, असं विसंगत चित्र तयार होईल."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT transfer_pair_id FROM account_transactions WHERE id=?", (tx_id,))
    row = c.fetchone()
    pair_id = row["transfer_pair_id"] if row else None

    if pair_id:
        c.execute("SELECT id FROM account_transactions WHERE transfer_pair_id=?", (pair_id,))
        ids = [r["id"] for r in c.fetchall()]
    else:
        ids = [tx_id]

    for i in ids:
        c.execute("UPDATE account_transactions SET is_deleted=1 WHERE id=?", (i,))
    conn.commit()
    conn.close()

    for i in ids:
        _touch_sync_fields(i, "account_transactions")
        _queue_sync("account_transactions", i, "delete")


def get_transactions_by_reference(reference_table, reference_id):
    """दुसऱ्या मॉड्यूलने (उदा. Expenses) पोस्ट केलेली ledger एन्ट्री शोधण्यासाठी —
    एडिट/डिलीट झाल्यावर ती एन्ट्री उलटवायला (reverse) उपयोगी."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM account_transactions
                 WHERE reference_table=? AND reference_id=?
                 AND (is_deleted IS NULL OR is_deleted=0)''', (reference_table, reference_id))
    data = c.fetchall()
    conn.close()
    return data


def get_account_transactions(account_id, limit=200):
    """एका खात्याचे सर्व transactions (नवीन आधी)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM account_transactions
                 WHERE account_id=? AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY id DESC LIMIT ?''', (account_id, limit))
    data = c.fetchall()
    conn.close()
    return data


def has_any_transactions(account_id):
    """खात्याला काही history आहे का — आर्काइव्ह करण्याआधी UI मध्ये इशारा
    द्यायला उपयोगी."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT COUNT(*) FROM account_transactions
                 WHERE account_id=? AND (is_deleted IS NULL OR is_deleted=0)''', (account_id,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0