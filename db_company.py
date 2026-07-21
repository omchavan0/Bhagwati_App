"""
============================================================================
DB COMPANY — Business Profile / Company Settings (Singleton Row — id=1)
============================================================================
इनव्हॉइस, GST Returns, आणि सगळीकडे लागणारी दुकानाची मूळ माहिती (GSTIN,
Bank, Logo) इथे साठते. टेबलमध्ये कायम फक्त एकच रो (id=1) असतो.
============================================================================
"""
from datetime import datetime
from db_core import _get_connection

COMPANY_COLUMNS = [
    ("company_name", "TEXT"),
    ("proprietor_name", "TEXT"),
    ("gstin", "TEXT"),
    ("pan", "TEXT"),
    ("address", "TEXT"),
    ("city", "TEXT"),
    ("state", "TEXT DEFAULT 'Maharashtra'"),
    ("state_code", "TEXT DEFAULT '27'"),
    ("pin_code", "TEXT"),
    ("mobile", "TEXT"),
    ("email", "TEXT"),
    ("website", "TEXT"),
    ("bank_name", "TEXT"),
    ("account_number", "TEXT"),
    ("ifsc", "TEXT"),
    ("upi_id", "TEXT"),
    ("logo_path", "TEXT"),
    ("terms_conditions", "TEXT"),
    ("declaration", "TEXT"),
    ("invoice_prefix", "TEXT DEFAULT 'INV'"),
    ("financial_year_start_month", "INTEGER DEFAULT 4"),
    ("updated_at", "TEXT"),
]


def init_table(conn, c):
    """company_settings टेबल तयार/मायग्रेट करतं — db_core.init_db() कडून कॉल होतं."""
    c.execute('''CREATE TABLE IF NOT EXISTS company_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1)
                 )''')
    conn.commit()

    c.execute("PRAGMA table_info(company_settings)")
    existing = {row[1] for row in c.fetchall()}
    for col_name, col_type in COMPANY_COLUMNS:
        if col_name not in existing:
            c.execute(f"ALTER TABLE company_settings ADD COLUMN {col_name} {col_type}")
    conn.commit()

    # पहिल्यांदाच असेल तर एक default row (id=1 fixed) तयार करतो
    c.execute("SELECT COUNT(*) FROM company_settings WHERE id=1")
    if c.fetchone()[0] == 0:
        c.execute('''INSERT INTO company_settings (id, company_name, state, state_code, invoice_prefix)
                     VALUES (1, 'Bhagwati Auto Electricals', 'Maharashtra', '27', 'INV')''')
    conn.commit()


def get_company_settings():
    """सध्याची Company Profile परत देतो (नेहमी id=1)."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM company_settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    return row


def update_company_settings(**kwargs):
    """दिलेले फील्ड्सच अपडेट करतो — बाकीचे जुनेच राहतात (safe partial update)."""
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.now().isoformat()
    conn = _get_connection()
    c = conn.cursor()
    cols = list(kwargs.keys())
    placeholders = ", ".join(f"{col}=?" for col in cols)
    values = [kwargs[col] for col in cols]
    c.execute(f"UPDATE company_settings SET {placeholders} WHERE id=1", values)
    conn.commit()
    conn.close()


def get_next_invoice_number():
    """Financial Year नुसार पुढचा Invoice No — उदा. INV-2526-000001
    (एप्रिल ते मार्च FY गृहीत धरून, udhaari रेकॉर्ड्सवरून मोजतो)."""
    from db_core import _parse_date

    settings = get_company_settings()
    prefix = (settings["invoice_prefix"] if settings and settings["invoice_prefix"] else "INV")
    fy_start_month = (settings["financial_year_start_month"]
                       if settings and settings["financial_year_start_month"] else 4)

    today = datetime.now()
    fy_start_year = today.year if today.month >= fy_start_month else today.year - 1
    fy_label = f"{str(fy_start_year)[-2:]}{str(fy_start_year + 1)[-2:]}"

    conn = _get_connection()
    c = conn.cursor()
    c.execute("SELECT tx_date FROM udhaari WHERE (is_deleted IS NULL OR is_deleted=0)")
    rows = c.fetchall()
    conn.close()

    fy_begin = datetime(fy_start_year, fy_start_month, 1)
    fy_end = datetime(fy_start_year + 1, fy_start_month, 1)
    count = sum(1 for r in rows if _parse_date(r["tx_date"]) and fy_begin <= _parse_date(r["tx_date"]) < fy_end)

    return f"{prefix}-{fy_label}-{count + 1:06d}"