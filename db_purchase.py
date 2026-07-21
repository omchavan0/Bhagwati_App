"""
============================================================================
DB PURCHASE — Purchase Bill (Input GST) + Purchase Items + Stock-In + Register
============================================================================
DESIGN — Sales (billing) च्याच Ledger Pattern ने, फक्त उलट दिशेने:
  - प्रत्येक Purchase Bill "purchase_bills" मध्ये saved होतो (Grand Total,
    Paid, Due — supplier ला किती देणं बाकी आहे, त्याचा हिशोब).
  - प्रत्येक line-item "purchase_items" मध्ये (rate/gst स्नॅपशॉट — जुनं बिल
    कधीही बदलणार नाही, part चा rate उद्या बदलला तरी).
  - प्रत्येक item साठी db_inventory.record_stock_in() आपोआप कॉल होतो —
    त्यामुळे स्टॉक ledger (db_inventory.py) आणि Purchase Register नेहमी
    जुळलेले राहतात (counter sync नाही, event sync).
  - Purchase Return झाला की तेवढी stock_out एन्ट्री टाकून उलटवतो.
============================================================================
"""
from datetime import datetime

from db_core import _get_connection, _touch_sync_fields, _queue_sync, get_current_owner_uid, get_current_owner_email, get_device_id
from db_inventory import record_stock_in, record_stock_out

# PURCHASE_BILL_COLUMNS मध्ये या 4 ओळी existing list च्या शेवटी ADD कर:
PURCHASE_BILL_COLUMNS = [
    ("supplier_id", "INTEGER"),
    ("bill_no", "TEXT"),
    ("bill_date", "TEXT"),
    ("sub_total", "REAL DEFAULT 0"),
    ("discount", "REAL DEFAULT 0"),
    ("transport", "REAL DEFAULT 0"),
    ("other_charges", "REAL DEFAULT 0"),
    ("taxable_value", "REAL DEFAULT 0"),
    ("cgst", "REAL DEFAULT 0"),
    ("sgst", "REAL DEFAULT 0"),
    ("igst", "REAL DEFAULT 0"),
    ("round_off", "REAL DEFAULT 0"),
    ("grand_total", "REAL DEFAULT 0"),
    ("paid_amt", "REAL DEFAULT 0"),
    ("due_amt", "REAL DEFAULT 0"),
    ("payment_mode", "TEXT DEFAULT 'Cash'"),
    ("notes", "TEXT"),
    ("is_return", "INTEGER DEFAULT 0"),
    ("created_at", "TEXT"),
    # 👇 नवीन — ITC / GSTR-2B / GSTR-3B ट्रॅकिंगसाठी
    ("supplier_gstin", "TEXT"),
    ("itc_eligible", "INTEGER DEFAULT 1"),   # 0 = Blocked credit (Sec 17(5) इ.)
    ("reverse_charge", "INTEGER DEFAULT 0"), # RCM लागू आहे का
    ("itc_claimed", "INTEGER DEFAULT 0"),    # GSTR-3B मध्ये आधीच क्लेम केला का
    ("itc_claim_period", "TEXT"),            # उदा. "2026-07" (कोणत्या महिन्याच्या 3B मध्ये क्लेम)
]


def _touch_purchase_sync(record_id, table):
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=?, owner_uid=?, owner_email=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), get_current_owner_uid(),
               get_current_owner_email(), record_id))
    conn.commit()
    conn.close()


def init_table(conn, c):
    """purchase_bills + purchase_items टेबल्स तयार/मायग्रेट करतं —
    db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS purchase_bills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supplier_name TEXT NOT NULL
                 )''')
    conn.commit()

    c.execute("PRAGMA table_info(purchase_bills)")
    existing = {row[1] for row in c.fetchall()}
    for col_name, col_type in PURCHASE_BILL_COLUMNS:
        if col_name not in existing:
            c.execute(f"ALTER TABLE purchase_bills ADD COLUMN {col_name} {col_type}")
    conn.commit()

    c.execute('''CREATE TABLE IF NOT EXISTS purchase_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_id INTEGER NOT NULL,
                    part_id INTEGER,
                    product_name TEXT,
                    part_number TEXT,
                    hsn_sac TEXT,
                    qty REAL DEFAULT 0,
                    purchase_rate REAL DEFAULT 0,
                    gst_rate REAL DEFAULT 18,
                    discount_percent REAL DEFAULT 0,
                    net_amount REAL DEFAULT 0,
                    created_at TEXT
                 )''')
    conn.commit()


# ======================================================================
# PURCHASE BILL — Save/Update/Delete
# ======================================================================

def add_purchase_bill(supplier_name, supplier_id, bill_no, bill_date,
                       sub_total, discount, transport, other_charges,
                       taxable_value, cgst, sgst, igst, round_off, grand_total,
                       paid_amt, due_amt, payment_mode="Cash", notes="",
                       supplier_gstin="", itc_eligible=True, reverse_charge=False,
                       itc_claimed=False, itc_claim_period=""):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO purchase_bills
                 (supplier_name, supplier_id, bill_no, bill_date, sub_total, discount,
                  transport, other_charges, taxable_value, cgst, sgst, igst, round_off,
                  grand_total, paid_amt, due_amt, payment_mode, notes, is_return, created_at,
                  supplier_gstin, itc_eligible, reverse_charge, itc_claimed, itc_claim_period)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)''',
              (supplier_name, supplier_id, bill_no, bill_date, sub_total, discount,
               transport, other_charges, taxable_value, cgst, sgst, igst, round_off,
               grand_total, paid_amt, due_amt, payment_mode, notes,
               datetime.now().isoformat(),
               supplier_gstin, 1 if itc_eligible else 0, 1 if reverse_charge else 0,
               1 if itc_claimed else 0, itc_claim_period))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_purchase_sync(new_id, "purchase_bills")
    _queue_sync("purchase_bills", new_id, "upsert")
    return new_id


def add_purchase_item(purchase_id, part_id, product_name, part_number, hsn_sac,
                       qty, purchase_rate, gst_rate, discount_percent, net_amount,
                       tx_date=""):
    """एक line-item साठवतो + आपोआप स्टॉक-इन करतो (part_id असेल तरच —
    Labour/Service इथे नसतं, फक्त Parts खरेदी होतात)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO purchase_items
                 (purchase_id, part_id, product_name, part_number, hsn_sac, qty,
                  purchase_rate, gst_rate, discount_percent, net_amount, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (purchase_id, part_id, product_name, part_number, hsn_sac, qty,
               purchase_rate, gst_rate, discount_percent, net_amount,
               datetime.now().isoformat()))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_purchase_sync(new_id, "purchase_items")
    _queue_sync("purchase_items", new_id, "upsert")

    if part_id:
        record_stock_in(part_id, qty, reference_table="purchase_bills",
                         reference_id=purchase_id, tx_date=tx_date,
                         notes=f"Purchase: {product_name}")

    return new_id


def get_purchase_bills():
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM purchase_bills WHERE (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY id DESC''')
    data = c.fetchall()
    conn.close()
    return data


def get_purchase_bill_by_id(purchase_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM purchase_bills WHERE id=?", (purchase_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_purchase_items(purchase_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM purchase_items WHERE purchase_id=?
                 AND (is_deleted IS NULL OR is_deleted=0) ORDER BY id ASC''', (purchase_id,))
    data = c.fetchall()
    conn.close()
    return data


def search_purchase_bills(query):
    if not query or not query.strip():
        return get_purchase_bills()
    conn = _get_connection()
    c = conn.cursor()
    like = f"%{query.strip()}%"
    c.execute('''SELECT * FROM purchase_bills
                 WHERE (supplier_name LIKE ? OR bill_no LIKE ?)
                 AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY id DESC''', (like, like))
    data = c.fetchall()
    conn.close()
    return data


# ======================================================================
# PURCHASE RETURN — स्टॉक + Payable दोन्ही उलटवतो (Reverse)
# ======================================================================

def record_purchase_return(purchase_id, return_items, return_date="", notes="Purchase Return"):
    """return_items = [{"part_id","product_name","qty","purchase_rate"}, ...]
    प्रत्येक item साठी स्टॉक-आउट करतो (परत पाठवलेला माल), आणि एक negative
    purchase_bills एन्ट्री (is_return=1) टाकतो जेणेकरून Purchase Register
    मध्ये हा return वेगळा (वजा म्हणून) दिसेल."""
    original = get_purchase_bill_by_id(purchase_id)
    if not original:
        raise ValueError("⚠️ मूळ Purchase Bill सापडला नाही.")

    return_total = sum((item["qty"] * item["purchase_rate"]) for item in return_items)

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO purchase_bills
                 (supplier_name, supplier_id, bill_no, bill_date, sub_total, discount,
                  transport, other_charges, taxable_value, cgst, sgst, igst, round_off,
                  grand_total, paid_amt, due_amt, payment_mode, notes, is_return, created_at)
                 VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, 0, 0, 0, 0, ?, 0, 0, ?, ?, 1, ?)''',
              (original["supplier_name"], original["supplier_id"],
               f"RET-{original['bill_no'] or original['id']}", return_date,
               return_total, return_total, "Return", notes,
               datetime.now().isoformat()))
    conn.commit()
    return_id = c.lastrowid
    conn.close()
    _touch_purchase_sync(return_id, "purchase_bills")
    _queue_sync("purchase_bills", return_id, "upsert")

    for item in return_items:
        if item.get("part_id"):
            record_stock_out(item["part_id"], item["qty"], reference_table="purchase_bills",
                              reference_id=return_id, tx_date=return_date,
                              notes=f"Purchase Return: {item['product_name']}")

    return return_id


# ======================================================================
# PURCHASE REGISTER — Reports साठी
# ======================================================================

def get_purchase_summary(days=None):
    """एकूण खरेदी, GST Input, Payable — Purchase Register/GSTR-2 साठी."""
    from db_core import _parse_date
    bills = [b for b in get_purchase_bills() if not b["is_return"]]

    if days:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        bills = [b for b in bills if _parse_date(b["bill_date"]) and _parse_date(b["bill_date"]) >= cutoff]

    total_purchase = sum((b["grand_total"] or 0) for b in bills)
    total_taxable = sum((b["taxable_value"] or 0) for b in bills)
    total_cgst = sum((b["cgst"] or 0) for b in bills)
    total_sgst = sum((b["sgst"] or 0) for b in bills)
    total_igst = sum((b["igst"] or 0) for b in bills)
    total_due = sum((b["due_amt"] or 0) for b in bills)

    return {
        "total_purchase": total_purchase, "total_taxable": total_taxable,
        "total_cgst": total_cgst, "total_sgst": total_sgst, "total_igst": total_igst,
        "total_input_gst": total_cgst + total_sgst + total_igst,
        "total_due": total_due, "bill_count": len(bills),
    }