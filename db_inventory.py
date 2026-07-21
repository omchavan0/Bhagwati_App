"""
============================================================================
DB INVENTORY — Parts Catalog + Stock Ledger + Part-Usage (Profit tracking)
============================================================================
DESIGN — Stock सुद्धा Finance सारखाच "Ledger Pattern" वापरतो:

चुकीचा मार्ग: parts.qty_in_stock नावाचा कॉलम ठेवून, प्रत्येक sale/purchase च्या
वेळी तो +/- करत राहणे — Finance मध्ये जसं सांगितलं तसाच धोका इथेही आहे:
Multi-device वर counter sync कधीही corrupt होऊ शकतो.

बरोबर मार्ग (हेच वापरलंय): प्रत्येक स्टॉक हालचाल ('in' खरेदी/जमा किंवा 'out'
वापर/विक्री) ही एक स्वतंत्र, अपरिवर्तनीय (immutable) ledger एन्ट्री असते.
सध्याचा स्टॉक कधीही "सगळे IN वजा सगळे OUT" असा लाइव्ह मोजला जातो.

तीन टेबल्स:
  parts        -> फक्त Product/Part ची माहिती (नाव, नंबर, rates, low-stock सीमा)
  stock_ledger -> प्रत्येक स्टॉक हालचालीची नोंद (खरेदी/वापर/adjustment)
  part_usage   -> एका transaction (Udhaari/DailyWork) मध्ये कोणते parts किती
                  दराने वापरले — यावरूनच "Profit" काढला जातो. Rates इथे
                  "स्नॅपशॉट" म्हणून साठवले जातात, जेणेकरून उद्या Part चा rate
                  बदलला तरी जुन्या बिलांचा profit कधीही बदलणार नाही.
============================================================================
"""
from datetime import datetime

from db_core import _get_connection, _touch_sync_fields, _queue_sync, get_current_owner_uid, get_current_owner_email, get_device_id

# Part Master ला Tally/Vyapar स्टाईल प्रोफेशनल फील्ड्ससाठी नवीन कॉलम्स
PART_EXTRA_COLUMNS = [
    ("mrp", "REAL DEFAULT 0"),
    ("discount_percent", "REAL DEFAULT 0"),
    ("barcode", "TEXT"),
    ("brand", "TEXT"),
    ("category", "TEXT"),
    ("unit", "TEXT DEFAULT 'Nos'"),
    ("location", "TEXT"),
    ("reorder_level", "REAL DEFAULT 5"),   # 👈 नवीन — डिफॉल्ट 5, पण UI मधून एडिट करता येतो
]

def init_table(conn, c):
    """parts + stock_ledger + part_usage टेबल्स तयार/मायग्रेट करतं —
    db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS parts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL,
                    part_number TEXT,
                    buying_rate REAL DEFAULT 0,
                    sell_rate REAL DEFAULT 0,
                    low_stock_alert_qty REAL DEFAULT 0,
                    notes TEXT,
                    created_at TEXT
                 )''')
    conn.commit()

    # GST Invoice साठी लागणारे कॉलम्स — जुन्या Parts टेबलमध्ये आपोआप मायग्रेट होतील
    c.execute("PRAGMA table_info(parts)")
    existing_part_cols = {row[1] for row in c.fetchall()}
    for col_name, col_type in (("hsn_sac", "TEXT"), ("gst_rate", "REAL DEFAULT 18")):
        if col_name not in existing_part_cols:
            c.execute(f"ALTER TABLE parts ADD COLUMN {col_name} {col_type}")
    conn.commit()


     # 👇 नवीन — Brand/Category/Unit/MRP/Barcode/Location मायग्रेशन
    c.execute("PRAGMA table_info(parts)")
    existing_part_cols = {row[1] for row in c.fetchall()}
    for col_name, col_type in PART_EXTRA_COLUMNS:
        if col_name not in existing_part_cols:
            c.execute(f"ALTER TABLE parts ADD COLUMN {col_name} {col_type}")
    conn.commit()

    c.execute('''CREATE TABLE IF NOT EXISTS stock_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    part_id INTEGER NOT NULL,
                    movement_type TEXT NOT NULL,
                    qty REAL DEFAULT 0,
                    reference_table TEXT,
                    reference_id INTEGER,
                    notes TEXT,
                    tx_date TEXT,
                    created_at TEXT
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS part_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reference_table TEXT NOT NULL,
                    reference_id INTEGER NOT NULL,
                    part_id INTEGER,
                    product_name TEXT,
                    part_number TEXT,
                    qty REAL DEFAULT 0,
                    buying_rate REAL DEFAULT 0,
                    sell_rate REAL DEFAULT 0,
                    discount_percent REAL DEFAULT 0,
                    net_amount REAL DEFAULT 0,
                    profit REAL DEFAULT 0,
                    tx_date TEXT,
                    created_at TEXT
                 )''')
    conn.commit()

    # GST Summary/HSN Report साठी — विक्रीच्या क्षणीचा HSN/GST% इथेच "स्नॅपशॉट"
    # म्हणून साठवतो (buying_rate/sell_rate सारखंच) — जेणेकरून उद्या एखाद्या Part
    # चा GST% बदलला तरी जुन्या बिलांचा GST रिपोर्ट कधीही चुकीचा होणार नाही.
    c.execute("PRAGMA table_info(part_usage)")
    existing_usage_cols = {row[1] for row in c.fetchall()}
    for col_name, col_type in (("hsn_sac", "TEXT"), ("gst_rate", "REAL DEFAULT 18")):
        if col_name not in existing_usage_cols:
            c.execute(f"ALTER TABLE part_usage ADD COLUMN {col_name} {col_type}")
    conn.commit()


# ======================================================================
# PARTS CATALOG — CRUD
# ======================================================================
# टीप (बग-फिक्स): आधी add_part() इथे दोनदा defined होतं — पहिलं
# (reorder_level शिवाय) पूर्णपणे dead code होतं, कारण खालचं (दुसरं)
# definition वरच्यालाच override करतं. आता फक्त एकच, पूर्ण व्हर्जन (reorder_level
# सकट) ठेवलंय.

def add_part(product_name, part_number="", buying_rate=0, sell_rate=0,
             low_stock_alert_qty=0, notes="", hsn_sac="", gst_rate=18,
             mrp=0, discount_percent=0, barcode="", brand="", category="",
             unit="Nos", location="", reorder_level=5):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO parts (product_name, part_number, buying_rate, sell_rate,
                    low_stock_alert_qty, notes, hsn_sac, gst_rate, mrp, discount_percent,
                    barcode, brand, category, unit, location, reorder_level, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (product_name, part_number, buying_rate, sell_rate,
               low_stock_alert_qty, notes, hsn_sac, gst_rate, mrp, discount_percent,
               barcode, brand, category, unit, location, reorder_level,
               datetime.now().strftime("%d-%m-%Y")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "parts")
    _queue_sync("parts", new_id, "upsert")
    return new_id


def update_part(part_id, product_name, part_number="", buying_rate=0, sell_rate=0,
                 low_stock_alert_qty=0, notes="", hsn_sac="", gst_rate=18,
                 mrp=0, discount_percent=0, barcode="", brand="", category="",
                 unit="Nos", location="", reorder_level=5):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''UPDATE parts SET product_name=?, part_number=?, buying_rate=?, sell_rate=?,
                    low_stock_alert_qty=?, notes=?, hsn_sac=?, gst_rate=?, mrp=?,
                    discount_percent=?, barcode=?, brand=?, category=?, unit=?, location=?,
                    reorder_level=?
                 WHERE id=?''',
              (product_name, part_number, buying_rate, sell_rate,
               low_stock_alert_qty, notes, hsn_sac, gst_rate, mrp, discount_percent,
               barcode, brand, category, unit, location, reorder_level, part_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(part_id, "parts")
    _queue_sync("parts", part_id, "upsert")

def update_part_mrp_and_rate(part_id, new_mrp, new_buying_rate):
    """Stock-In save झाल्यावर, त्या Part चा MRP आणि buying_rate दोन्ही
    ताज्या खरेदी दराने अपडेट करतो — GST Billing मध्ये MRP आणि पुढच्या
    sales चा Profit गणित अचूक राहावं म्हणून (जुन्या बिलांचा profit मात्र
    स्नॅपशॉटमुळे कधीही बदलत नाही)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE parts SET mrp=?, buying_rate=? WHERE id=?",
              (new_mrp, new_buying_rate, part_id))
    conn.commit()
    conn.close()
    _touch_sync_fields(part_id, "parts")
    _queue_sync("parts", part_id, "upsert")   
    
def archive_part(part_id):
    """Part सॉफ्ट-डिलीट करतं — जुन्या बिलांमधली नोंद (part_usage) सुरक्षित राहते,
    फक्त नवीन विक्रीसाठी dropdown मधून गायब होतं."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE parts SET is_deleted=1 WHERE id=?", (part_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(part_id, "parts")
    _queue_sync("parts", part_id, "delete")


def get_parts():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM parts WHERE (is_deleted IS NULL OR is_deleted=0) ORDER BY product_name COLLATE NOCASE")
    data = c.fetchall()
    conn.close()
    return data


def get_part_by_id(part_id):
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM parts WHERE id=?", (part_id,))
    row = c.fetchone()
    conn.close()
    return row


def search_parts(query):
    if not query or not query.strip():
        return get_parts()
    conn = _get_connection()
    c = conn.cursor()
    like = f"%{query.strip()}%"
    c.execute('''SELECT * FROM parts
                 WHERE (product_name LIKE ? OR part_number LIKE ?)
                 AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY product_name COLLATE NOCASE''', (like, like))
    data = c.fetchall()
    conn.close()
    return data


# ======================================================================
# STOCK LEDGER — सध्याचा स्टॉक नेहमी इथूनच लाइव्ह मोजला जातो
# ======================================================================

def find_part_by_number(part_number, exclude_id=None):
    """Part Number आधीच वापरात आहे का तपासतो (Unique Key validation साठी).
    exclude_id दिला तर तोच Part (सध्या एडिट होतोय तो) वगळून तपासतो."""
    part_number = (part_number or "").strip()
    if not part_number:
        return None
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM parts WHERE part_number=? COLLATE NOCASE
                 AND (is_deleted IS NULL OR is_deleted=0)''', (part_number,))
    rows = c.fetchall()
    conn.close()
    matches = [r for r in rows if not exclude_id or r["id"] != exclude_id]
    return matches[0] if matches else None

def get_part_stock(part_id):
    """सध्याचा स्टॉक — सगळे 'in' वजा सगळे 'out' (लाइव्ह गणित)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT COALESCE(SUM(CASE WHEN movement_type='in' THEN qty ELSE -qty END), 0)
                 FROM stock_ledger
                 WHERE part_id=? AND (is_deleted IS NULL OR is_deleted=0)''', (part_id,))
    stock = c.fetchone()[0]
    conn.close()
    return stock


def _record_stock_movement(part_id, movement_type, qty, reference_table=None,
                            reference_id=None, notes="", tx_date=""):
    if movement_type not in ("in", "out"):
        raise ValueError("movement_type फक्त 'in' किंवा 'out' असू शकतो")
    if qty is None or float(qty) <= 0:
        raise ValueError("Qty शून्यापेक्षा जास्त असावी")

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO stock_ledger
                 (part_id, movement_type, qty, reference_table, reference_id, notes, tx_date, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (part_id, movement_type, float(qty), reference_table, reference_id,
               notes, tx_date, datetime.now().isoformat()))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "stock_ledger")
    _queue_sync("stock_ledger", new_id, "upsert")
    return new_id


def record_stock_in(part_id, qty, reference_table=None, reference_id=None, notes="", tx_date=""):
    """नवीन खरेदी/जमा — स्टॉक वाढवतो."""
    return _record_stock_movement(part_id, "in", qty, reference_table, reference_id, notes, tx_date)


def record_stock_out(part_id, qty, reference_table=None, reference_id=None, notes="", tx_date=""):
    """वापर/विक्री — स्टॉक कमी करतो."""
    return _record_stock_movement(part_id, "out", qty, reference_table, reference_id, notes, tx_date)


def get_low_stock_parts():
    """ज्यांचा live स्टॉक low_stock_alert_qty पेक्षा कमी/बरोबर आहे अशा parts ची यादी."""
    parts = get_parts()
    result = []
    for p in parts:
        stock = get_part_stock(p["id"])
        alert_qty = p["low_stock_alert_qty"] or 0
        if alert_qty > 0 and stock <= alert_qty:
            result.append({"part": p, "stock": stock})
    return result


def get_all_parts_with_stock():
    """Inventory डॅशबोर्डसाठी — प्रत्येक part + त्याचा live stock एकत्र."""
    parts = get_parts()
    result = []
    for p in parts:
        result.append({
            "id": p["id"], "product_name": p["product_name"], "part_number": p["part_number"],
            "buying_rate": p["buying_rate"], "sell_rate": p["sell_rate"],
            "low_stock_alert_qty": p["low_stock_alert_qty"], "notes": p["notes"],
            "stock": get_part_stock(p["id"]),
        })
    return result


# ======================================================================
# PART USAGE — एका Transaction मध्ये वापरलेले Parts + Profit calculation
# ======================================================================

def add_part_usage(reference_table, reference_id, part_id, product_name, part_number,
                    qty, buying_rate, sell_rate, discount_percent=0, tx_date="", notes="",
                    hsn_sac=None, gst_rate=None):
    """एका transaction (उदा. Udhaari किंवा DailyWork रेकॉर्ड) मध्ये एक Part
    वापरला गेला याची नोंद — Net Amount + Profit आपोआप काढतो, आणि स्टॉकमधून
    तेवढी qty आपोआप वजा (stock-out) करतो.

    hsn_sac/gst_rate दिले नाहीत तर (जुने calls आधीसारखेच चालावेत म्हणून)
    part_id वरून त्या Part चा सध्याचा HSN/GST% आपोआप उचलतो — पुढे तो Part
    बदलला तरी ही जुनी नोंद (आणि तिच्यावर आधारित GST रिपोर्ट) कधीही बदलणार नाही."""
    qty = float(qty or 0)
    buying_rate = float(buying_rate or 0)
    sell_rate = float(sell_rate or 0)
    discount_percent = float(discount_percent or 0)

    if qty <= 0:
        raise ValueError("⚠️ Qty शून्यापेक्षा जास्त असावी.")

    if (hsn_sac is None or gst_rate is None) and part_id:
        part = get_part_by_id(part_id)
        if part:
            if hsn_sac is None:
                hsn_sac = part["hsn_sac"] if "hsn_sac" in part.keys() and part["hsn_sac"] else ""
            if gst_rate is None:
                gst_rate = part["gst_rate"] if "gst_rate" in part.keys() and part["gst_rate"] is not None else 18
    hsn_sac = hsn_sac or ""
    gst_rate = float(gst_rate) if gst_rate is not None else 18.0

    gross = qty * sell_rate
    net_amount = gross - (gross * discount_percent / 100)
    profit = net_amount - (qty * buying_rate)

    conn = _get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO part_usage
                 (reference_table, reference_id, part_id, product_name, part_number,
                  qty, buying_rate, sell_rate, discount_percent, net_amount, profit,
                  tx_date, created_at, hsn_sac, gst_rate)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (reference_table, reference_id, part_id, product_name, part_number,
               qty, buying_rate, sell_rate, discount_percent, net_amount, profit,
               tx_date, datetime.now().isoformat(), hsn_sac, gst_rate))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    _touch_sync_fields(new_id, "part_usage")
    _queue_sync("part_usage", new_id, "upsert")

    if part_id:
        record_stock_out(part_id, qty, reference_table=reference_table,
                          reference_id=reference_id, tx_date=tx_date,
                          notes=f"वापरलं: {product_name}")

    return new_id, net_amount, profit


def get_part_usage_by_reference(reference_table, reference_id):
    """एका transaction मध्ये वापरलेले सगळे parts (line items) परत देतं."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM part_usage
                 WHERE reference_table=? AND reference_id=?
                 AND (is_deleted IS NULL OR is_deleted=0)
                 ORDER BY id ASC''', (reference_table, reference_id))
    data = c.fetchall()
    conn.close()
    return data


def delete_part_usage(usage_id):
    """एक line-item काढून टाकतं — आणि तेवढी qty स्टॉकमध्ये आपोआप परत (stock-in
    reversal) जमा करतं, जेणेकरून स्टॉक चुकीचा राहणार नाही."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM part_usage WHERE id=?", (usage_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return

    c.execute("UPDATE part_usage SET is_deleted=1 WHERE id=?", (usage_id,))
    conn.commit()
    conn.close()
    _touch_sync_fields(usage_id, "part_usage")
    _queue_sync("part_usage", usage_id, "delete")

    if row["part_id"]:
        record_stock_in(row["part_id"], row["qty"], reference_table=row["reference_table"],
                         reference_id=row["reference_id"], notes="Line-item डिलीट -> स्टॉक परत जमा")


def clear_part_usage_for_reference(reference_table, reference_id):
    """एका transaction चे सगळे जुने parts-line-items काढून, स्टॉक परत जमा करतो
    (transaction एडिट करताना 'आधी सगळं मागे घे, मग नवीन टाक' या पद्धतीसाठी उपयोगी)."""
    for row in get_part_usage_by_reference(reference_table, reference_id):
        delete_part_usage(row["id"])


def get_gst_summary_report(days=None):
    """GST Summary / HSN Summary — GSTR-1, GSTR-3B भरताना लागणारी माहिती.

    net_amount (part_usage मध्ये आधीच साठवलेला) हा नेहमी 'ग्राहकाकडून घेतलेली
    अंतिम रक्कम' (GST-सकट) असतो — त्यामुळे invoice.py मध्ये वापरलेल्याच
    price_includes_gst=True सूत्राने Taxable Value मागच्या बाजूने काढतो:
        Taxable = Amount ÷ (1 + GST%/100)
        Tax     = Amount − Taxable  ->  CGST = Tax/2, SGST = Tax/2

    टीप: हे गृहीत धरतं की सगळ्या विक्री Maharashtra मधल्याच ग्राहकांना
    (Intra-state, CGST+SGST) झाल्या आहेत — कारण दुकानाचे बहुतांश ग्राहक
    स्थानिक असतात. एखादी विक्री दुसऱ्या राज्यात (IGST) झाली असेल तर ती इथे
    वेगळी ओळखली जात नाही — गरज पडल्यास पुढे जोडता येईल.

    Returns: {"total_taxable", "total_cgst", "total_sgst", "total_tax",
              "total_amount", "hsn_rows": [{"hsn_sac","gst_rate","taxable",
              "cgst","sgst","tax","amount"}, ...]}
    """
    from db_core import _parse_date
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM part_usage WHERE (is_deleted IS NULL OR is_deleted=0)")
    rows = c.fetchall()
    conn.close()

    if days:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        rows = [r for r in rows if _parse_date(r["tx_date"]) and _parse_date(r["tx_date"]) >= cutoff]

    groups = {}  # (hsn_sac, gst_rate) -> {"taxable","tax","amount"}
    for r in rows:
        hsn = r["hsn_sac"] if "hsn_sac" in r.keys() and r["hsn_sac"] else "-"
        gst_rate = r["gst_rate"] if "gst_rate" in r.keys() and r["gst_rate"] is not None else 18.0
        amount = r["net_amount"] or 0
        taxable = amount / (1 + gst_rate / 100) if gst_rate else amount
        tax = amount - taxable

        key = (hsn, gst_rate)
        grp = groups.setdefault(key, {"taxable": 0.0, "tax": 0.0, "amount": 0.0})
        grp["taxable"] += taxable
        grp["tax"] += tax
        grp["amount"] += amount

    hsn_rows = []
    total_taxable = total_tax = total_amount = 0.0
    for (hsn, gst_rate), grp in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        cgst = grp["tax"] / 2
        sgst = grp["tax"] / 2
        hsn_rows.append({
            "hsn_sac": hsn, "gst_rate": gst_rate,
            "taxable": grp["taxable"], "cgst": cgst, "sgst": sgst,
            "tax": grp["tax"], "amount": grp["amount"],
        })
        total_taxable += grp["taxable"]
        total_tax += grp["tax"]
        total_amount += grp["amount"]

    return {
        "total_taxable": total_taxable,
        "total_cgst": total_tax / 2,
        "total_sgst": total_tax / 2,
        "total_tax": total_tax,
        "total_amount": total_amount,
        "hsn_rows": hsn_rows,
    }

def _touch_sync_fields(record_id, table):
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=?, owner_uid=?, owner_email=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), get_current_owner_uid(),
               get_current_owner_email(), record_id))
    conn.commit()
    conn.close()
    
def get_profit_summary(reference_table=None, days=None):
    """एकूण Net Amount आणि Profit ची बेरीज — Reports साठी. reference_table
    दिलं तर फक्त त्या प्रकारच्या transactions पुरता मर्यादित (उदा. फक्त udhaari)."""
    from db_core import _parse_date
    conn = _get_connection()
    c = conn.cursor()
    query = "SELECT * FROM part_usage WHERE (is_deleted IS NULL OR is_deleted=0)"
    params = []
    if reference_table:
        query += " AND reference_table=?"
        params.append(reference_table)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    if days:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        rows = [r for r in rows if _parse_date(r["tx_date"]) and _parse_date(r["tx_date"]) >= cutoff]

    total_net = sum((r["net_amount"] or 0) for r in rows)
    total_profit = sum((r["profit"] or 0) for r in rows)
    return {"total_net_amount": total_net, "total_profit": total_profit, "line_items": len(rows)}


# ======================================================================
# STOCK ADJUSTMENT — नुकसान/चोरी/तुटलेला माल/ऑडिट तफावतीसाठी (खोटी
# Purchase/Sale एन्ट्री टाकायची गरज नाही). तोच stock_ledger वापरतो, फक्त
# reference_table='stock_adjustment' ने वेगळा ओळखला जातो — म्हणजे Reports/
# History मध्ये "हे adjustment होतं, sale/purchase नाही" हे स्पष्ट दिसेल.
# ======================================================================

def adjust_stock(part_id, qty_change, reason="Adjustment", notes="", tx_date=""):
    """qty_change पॉझिटिव्ह = स्टॉक वाढ (उदा. सापडलेला जुना माल),
    निगेटिव्ह = स्टॉक घट (उदा. तुटलं/चोरी). दोन्ही एकाच लाईव्ह-गणित
    ledger मध्ये नोंदतात — बाकी स्टॉक-रिपोर्ट कधीही चुकीचा होणार नाही."""
    from datetime import datetime as _dt
    qty_change = float(qty_change or 0)
    if qty_change == 0:
        raise ValueError("⚠️ Adjustment Qty शून्य असू शकत नाही.")

    tx_date = tx_date or _dt.now().strftime("%d.%m.%Y")
    full_note = reason + (f" — {notes}" if notes else "")

    if qty_change > 0:
        return record_stock_in(part_id, abs(qty_change), reference_table="stock_adjustment",
                                notes=full_note, tx_date=tx_date)
    else:
        return record_stock_out(part_id, abs(qty_change), reference_table="stock_adjustment",
                                 notes=full_note, tx_date=tx_date)


def get_stock_adjustments(part_id=None, limit=200):
    """Adjustment Audit Trail — कोणत्या Part चा स्टॉक कधी, किती, कशासाठी बदलला."""
    conn = _get_connection()
    c = conn.cursor()
    if part_id:
        c.execute('''SELECT * FROM stock_ledger WHERE reference_table='stock_adjustment'
                     AND part_id=? AND (is_deleted IS NULL OR is_deleted=0)
                     ORDER BY id DESC LIMIT ?''', (part_id, limit))
    else:
        c.execute('''SELECT * FROM stock_ledger WHERE reference_table='stock_adjustment'
                     AND (is_deleted IS NULL OR is_deleted=0)
                     ORDER BY id DESC LIMIT ?''', (limit,))
    data = c.fetchall()
    conn.close()
    return data

# ======================================================================
# CATEGORY MASTER — Part Master मधल्या Category dropdown साठी (+) New
# Category जोडता यावी म्हणून. साधं, हलकं टेबल — फक्त नावं साठवतं.
# ======================================================================

def init_categories_table(conn, c):
    """part_categories टेबल तयार करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS part_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                 )''')
    conn.commit()

    # आधीच वापरलेल्या Categories (जुन्या Parts मधून) आपोआप इथे भरतो —
    # जेणेकरून जुना डेटा असेल तर dropdown रिकामा दिसणार नाही.
    c.execute("SELECT DISTINCT category FROM parts WHERE category IS NOT NULL AND category != ''")
    existing_names = {row[0] for row in c.fetchall()}
    for name in existing_names:
        c.execute("INSERT OR IGNORE INTO part_categories (name) VALUES (?)", (name,))
    conn.commit()


def get_categories():
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM part_categories ORDER BY name COLLATE NOCASE")
    data = c.fetchall()
    conn.close()
    return data


def add_category(name):
    name = (name or "").strip()
    if not name:
        raise ValueError("⚠️ Category नाव रिकामं असू शकत नाही.")
    conn = _get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO part_categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    return name