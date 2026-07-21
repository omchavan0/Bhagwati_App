"""
============================================================================
DATABASE.PY — Backward-compatible FACADE
============================================================================
हे आता खरं database नाही — फक्त एक "पूल" आहे जो खालच्या वेगळ्या db_*.py
मॉड्यूल्समधून सगळे functions एकत्र आणून देतो:

    db_core.py     -> connection, cloud-sync engine, backup, PIN, session
    db_udhaari.py  -> उधारी (Credit/Debit) टेबल
    db_expenses.py -> दुकानाचा खर्च
    db_work.py     -> रोजची कामं (Daily Work)
    db_clients.py  -> Garage Groups / Clients
    db_finance.py  -> Accounts (Cash/Bank/UPI) + Ledger-based Balance

का असं केलं?
जुन्या सगळ्या फाईल्स (udhaari_view.py, expense_view.py, work_view.py,
clients_view.py, main.py, इ.) `from database import xyz` असं वापरतात.
त्या सगळ्या फाईल्समध्ये बदल न करता आपण आतला कोड आरामात 5 वेगळ्या,
लहान, स्वतंत्र फाईल्समध्ये विभागू शकलो — म्हणजे उद्या Udhaari मध्ये बदल
केला तर Expenses/Work/Clients चा कोड टच होतच नाही, त्यामुळे तो चुकून
तुटण्याची शक्यता जवळपास शून्य होते.

नवीन कोड लिहिताना: शक्य असल्यास थेट `from db_udhaari import ...` असं
संबंधित मॉड्यूलमधूनच import कर (जुन्या फाईल्ससाठी हा facade आहेच).
============================================================================
"""

from db_core import *          # noqa: F401,F403  connection, sync, backup, PIN, session
from db_udhaari import *       # noqa: F401,F403  उधारी
from db_expenses import *      # noqa: F401,F403  खर्च
from db_work import *          # noqa: F401,F403  रोजचं काम
from db_clients import *       # noqa: F401,F403  Clients/Garage Groups
from db_finance import *       # noqa: F401,F403  Accounts (Cash/Bank/UPI) + Ledger
from db_inventory import *     # noqa: F401,F403  Parts Catalog + Stock Ledger + Profit
from db_company import *       # noqa: F401,F403  Company Settings / Business Profile
from db_customers import *     # noqa: F401,F403  GST Customer Master   👈 नवीन
from db_labour import *        # noqa: F401,F403  Labour/Service Master   👈 नवीन
from db_suppliers import *     # noqa: F401,F403  Supplier Master   👈 नवीन
from db_purchase import *      # noqa: F401,F403  Purchase Bill + Register   👈 नवीन
from db_gst_returns import *   # noqa: F401,F403  GSTR-1 / GSTR-3B / HSN Returns   👈 नवीन
from db_stock_in import *      # noqa: F401,F403  Reverse-GST Stock-In Entry   👈 नवीन