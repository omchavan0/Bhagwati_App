"""
============================================================================
BILLING VIEW — एका Sale मध्ये सगळं आपोआप जोडणारा व्ह्यू
============================================================================
हा व्ह्यू "FinalSaleTransferAndPDF" च्या कल्पनेलाच पुढे नेतो, पण एक वेगळी
(राॅ Google Sheet) Inventory ठेवण्याऐवजी आधीच अस्तित्वात असलेल्या Ledger-based
आर्किटेक्चरचा वापर करतो — त्यामुळे दोन वेगवेगळे "source of truth" तयार होत
नाहीत आणि स्टॉक/पैसे कधीही विसंगत होत नाहीत.

एक Sale Save केल्यावर आपोआप होणाऱ्या गोष्टी:
  1. Udhaari रेकॉर्ड तयार होतो (Total/Paid/Due सह) — due>0 असेल तर तो
     आपोआप "Udhaari" मॉड्यूलमध्ये उधारी म्हणून ट्रॅक होतो.
  2. Cart मधल्या प्रत्येक Part साठी part_usage नोंद होते — यामुळे:
        - स्टॉक आपोआप ledger मधून वजा होतो (db_inventory.record_stock_out)
        - Profit (Sell - Buying) आपोआप कॅल्क्युलेट/साठवला जातो
  3. Daily Work Log मध्ये एक नोंद होते (कोणतं काम, कोणत्या गाडीवर).
  4. जेवढी रक्कम "आत्ता" मिळाली (Paid Amount) आणि Account निवडलं असेल तर,
     त्या Account च्या Finance Ledger मध्ये credit एन्ट्री जाते.
  5. एक PDF Invoice तयार होतो (invoice.py वापरून).
  6. Google Sheets sync — वेगळं काही करावं लागत नाही; add_udhaari/add_work
     आधीच db_udhaari.py/db_work.py मधून _safe_sync() ला कॉल करतात, आणि तेच
     gsheet_sync.py (Udhaari_Log / Daily_Work_Log) मिरर करतं.

टीप: final_sale_transfer_and_pdf.py (राॅ gspread + वेगळी Inventory sheet)
वापरणं बंद करून, हाच व्ह्यू "Sale" साठी वापरण्याची शिफारस आहे.
============================================================================
"""
import os
from datetime import datetime

import flet as ft

from database import (
    get_clients, add_client,
    search_parts, get_part_by_id, get_part_stock, add_part_usage,
    get_accounts, add_transaction,
    add_udhaari, get_by_id,
    add_work,
)
from invoice import generate_invoice
from gst_invoice_pro import generate_full_gst_invoice
from customer_lookup import smart_customer_lookup, auto_capitalize_words


def _get_output_dir():
    """Desktop वर Downloads फोल्डर वापरतो; नसेल तर app च्या 'invoices' फोल्डरमध्ये."""
    try:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads, exist_ok=True)
        return downloads
    except Exception:
        fallback = os.path.join(os.getcwd(), "invoices")
        os.makedirs(fallback, exist_ok=True)
        return fallback


PAYMENT_MODES = ["Cash", "UPI", "Bank Transfer", "Credit"]


class BillingView(ft.Row):
    """एक पूर्ण Sale process करणारा व्ह्यू — Parts निवडा, Payment ठरवा, Save दाबा."""

    def __init__(self, refresh_callback=None):
        super().__init__(expand=True)
        self.refresh_callback = refresh_callback
        self.cart = []  # प्रत्येक item: dict(part_id, product_name, part_number,
                        #                      qty, buying_rate, sell_rate,
                        #                      discount_percent, net_amount)

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        # ---------------- Customer / Vehicle ----------------
        self.client_dropdown = ft.Dropdown(label="🏢 Garage / Client (optional)", height=52, **S)
        self.customer_name = ft.TextField(label="👤 Customer Name *", height=52, **S)
        self.mobile = ft.TextField(label="📱 Mobile", height=52, **S)
        self.vehicle = ft.TextField(label="🚗 Vehicle", height=52, **S)
        self.vehicle_no = ft.TextField(label="🔢 Vehicle Number", height=52, **S)

        # टीप: on_blur/on_change constructor मध्ये न देता वेगळं set केलंय —
        # आधीच्या Dropdown TypeError प्रमाणे कुठल्याही Flet version वर सुरक्षित
        # चालावं म्हणून हाच पॅटर्न सगळीकडे वापरलाय.
        self.customer_name.on_change = lambda e: self._auto_cap(self.customer_name)
        self.customer_name.on_blur = lambda e: self._try_autofill(self.customer_name.value)
        self.mobile.on_blur = lambda e: self._try_autofill(self.mobile.value)
        self.vehicle_no.on_blur = lambda e: self._try_autofill(self.vehicle_no.value)
        self.work_desc = ft.TextField(label="🔧 Work Description", multiline=True, height=70, **S)
        self.tx_date = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=52,
                                     value=datetime.now().strftime("%d.%m.%Y"), **S)

        # ---------------- Parts Add Row ----------------
        self.part_dropdown = ft.Dropdown(label="🔩 Part निवडा", height=52, expand=True, **S)
        self.part_qty = ft.TextField(label="Qty", height=52, width=90,
                                      keyboard_type=ft.KeyboardType.NUMBER, value="1", **S)
        self.part_discount = ft.TextField(label="Disc %", height=52, width=90,
                                           keyboard_type=ft.KeyboardType.NUMBER, value="0", **S)
        self.add_part_btn = ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="#00ffaa",
                                           icon_size=32, tooltip="Cart मध्ये जोडा",
                                           on_click=self.handle_add_part)

        self.parts_total_text = ft.Text("₹0", size=14, weight="bold", color="#00ffaa")

        # ---------------- Labour + Totals ----------------
        # टीप: on_change हे constructor मध्ये न देता, object तयार झाल्यावर वेगळं
        # set केलंय — काही Flet versions मध्ये control च्या __init__() ने थेट
        # on_change स्वीकारला नाही तर TypeError येतो; अशा प्रकारे ते सगळ्याच
        # versions मध्ये सुरक्षित चालतं.
        self.labour_charge = ft.TextField(label="👷 Labour Charge", height=52, value="0",
                                           prefix=ft.Text("₹ "), keyboard_type=ft.KeyboardType.NUMBER,
                                           **S)
        self.labour_charge.on_change = lambda e: self._recalc()
        self.grand_total_text = ft.Text("₹0", size=20, weight="bold", color="white")

        # ---------------- Payment ----------------
        self.payment_mode = ft.Dropdown(label="💳 Payment Mode", height=52, value="Cash",
                                         options=[ft.dropdown.Option(m) for m in PAYMENT_MODES],
                                         **S)
        self.payment_mode.on_change = self._on_payment_mode_change
        self.account_dropdown = ft.Dropdown(label="🏦 कोणत्या Account मध्ये जमा", height=52, **S)
        self.paid_amt = ft.TextField(label="✅ Paid Amount (आत्ता मिळाले)", height=52,
                                      prefix=ft.Text("₹ "), keyboard_type=ft.KeyboardType.NUMBER,
                                      value="0", **S)
        self.paid_amt.on_change = lambda e: self._recalc()
        self.due_amt_text = ft.Text("₹0", size=16, weight="bold", color="#ff8800")

        self.paper_size = ft.Dropdown(
            label="🖨️ Bill Size", height=52, value="A5",
            options=[ft.dropdown.Option("A5", "A5 (अर्धा पेज)"),
                     ft.dropdown.Option("A4", "A4 (फुल पेज)")],
            **S,
        )
        self.gst_bill_toggle = ft.Switch(label="🧾 GST Bill (Tax Invoice)?", value=False,
                                          active_color="#00ffaa",
                                          on_change=self._on_gst_toggle_change)
        self.customer_gstin = ft.TextField(label="GSTIN (ग्राहकाचा, ऐच्छिक)", height=52,
                                            visible=False, **S)
        self.customer_state = ft.Dropdown(
            label="Place of Supply (राज्य)", height=52, value="Maharashtra", visible=False,
            options=[ft.dropdown.Option("Maharashtra"), ft.dropdown.Option("Other State")],
            **S,
        )

        self.status_text = ft.Text("", size=13, visible=False)
        self.save_btn = ft.ElevatedButton(
            "💾 Sale Save करा + Bill बनवा", bgcolor="#00ffaa", color="black",
            height=52, expand=True, on_click=self.handle_save_sale,
        )

        # ---------------- Item List (Tally/Vyapar-style DataTable) ----------------
        self.item_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("SI", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Item", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("HSN/SAC", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Qty", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Rate", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("GST%", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Disc%", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Amount", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("")),
            ],
            rows=[],
            column_spacing=14, data_row_min_height=38, data_row_max_height=44,
            heading_row_color="#161622", heading_row_height=36,
        )
        self.item_table_holder = ft.Container(
            content=ft.Column([self.item_table], scroll="auto"),
            height=220, bgcolor="#0e0e16", border_radius=10,
            border=ft.Border.all(1, "#1a1a26"), padding=8,
        )

        # ---------------- Live Bill Summary (Sub Total / GST / Net Total / Paid / Due) ----------------
        def _summary_row(label, value_control, bold=False):
            return ft.Row(
                [ft.Text(label, size=13, color="#94a3b8", weight="bold" if bold else None),
                 ft.Container(expand=True), value_control],
            )

        self.sub_total_text = ft.Text("₹0", size=14, color="white")
        self.gst_summary_text = ft.Text("₹0", size=14, color="#00aaff")
        self.summary_paid_text = ft.Text("₹0", size=14, color="white")
        self.summary_due_text = ft.Text("₹0", size=14, color="#ff8800")
        self.summary_net_total_text = ft.Text("₹0", size=20, weight="bold", color="#00ffaa")

        self.gst_summary_row = _summary_row("GST (Included)", self.gst_summary_text)
        self.gst_summary_row.visible = False

        self.bill_summary_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text("🧾 Bill Summary", size=15, weight="bold", color="white"),
                    ft.Divider(color="#1a1a26"),
                    _summary_row("Sub Total (Items + Labour)", self.sub_total_text),
                    self.gst_summary_row,
                    ft.Divider(color="#1a1a26"),
                    _summary_row("Net Total (Grand Total)", self.summary_net_total_text, bold=True),
                    ft.Container(height=4),
                    _summary_row("Payment Paid", self.summary_paid_text),
                    _summary_row("Payment Due", self.summary_due_text),
                ],
                spacing=10,
            ),
            bgcolor="#161622", padding=18, border_radius=12,
        )


        left = ft.Container(
            content=ft.Column(
                [
                    ft.Text("🧾 New Sale / Billing", size=20, weight="bold", color="#00ffaa"),
                    self.status_text,
                    ft.Row([self.client_dropdown]),
                    ft.Row([self.customer_name, self.mobile], spacing=10),
                    ft.Row([self.vehicle, self.vehicle_no], spacing=10),
                    self.work_desc,
                    self.tx_date,
                    ft.Divider(color="#1a1a26"),
                    ft.Text("🔩 Parts Used", size=14, weight="bold", color="white"),
                    ft.Row([self.part_dropdown, self.part_qty, self.part_discount, self.add_part_btn], spacing=8),
                    ft.Divider(color="#1a1a26"),
                    self.labour_charge,
                    ft.Row([ft.Text("Grand Total:", size=15, color="#94a3b8"),
                            ft.Container(expand=True), self.grand_total_text]),
                    ft.Divider(color="#1a1a26"),
                    ft.Text("💰 Payment", size=14, weight="bold", color="white"),
                    self.payment_mode,
                    self.account_dropdown,
                    self.paid_amt,
                    ft.Row([ft.Text("Due राहील:", size=13, color="#94a3b8"),
                            ft.Container(expand=True), self.due_amt_text]),
                    ft.Container(height=6),
                    self.paper_size,
                    self.gst_bill_toggle,
                    ft.Row([self.customer_gstin, self.customer_state], spacing=10),
                    ft.Container(height=6),
                    self.save_btn,
                ],
                scroll="auto", spacing=10,
            ),
            padding=20, width=520, bgcolor="#0e0e16",
        )

        self.info_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Text("📋 Item List", size=18, weight="bold", color="#00ffaa"),
                    self.item_table_holder,
                    ft.Container(height=6),
                    self.bill_summary_box,
                    ft.Container(height=10),
                    ft.Text(
                        "ℹ️ Parts एक-एक करून डावीकडून Cart मध्ये जोडा — स्टॉक आपोआप वजा होईल, "
                        "Profit ट्रॅक होईल आणि इथे Item List + GST गणित लाइव्ह दिसेल.",
                        size=12, color="#64748b", italic=True,
                    ),
                ],
                spacing=10, scroll="auto",
            ),
            padding=25, expand=True,
        )

        self.controls = [left, ft.VerticalDivider(width=1, color="#1a1a26"), self.info_panel]

    # ======================================================================
    def did_mount(self):
        self._load_client_options()
        self._load_part_options()
        self._load_account_options()
        self._recalc()

    def _load_client_options(self):
        clients = get_clients()
        self.client_dropdown.options = [ft.dropdown.Option(key="", text="— कोणीही नाही —")] + [
            ft.dropdown.Option(key=str(c["id"]), text=c["garage_name"]) for c in clients
        ]
        if self.page:
            self.client_dropdown.update()

    def _load_part_options(self):
        parts = search_parts(None)
        opts = []
        for p in parts:
            stock = get_part_stock(p["id"])
            opts.append(ft.dropdown.Option(
                key=str(p["id"]),
                text=f"{p['product_name']}  (Stock: {stock:.0f}, ₹{p['sell_rate']:.0f})",
            ))
        self.part_dropdown.options = opts
        if self.page:
            self.part_dropdown.update()

    def _load_account_options(self):
        accounts = get_accounts()
        self.account_dropdown.options = [ft.dropdown.Option(key="", text="— निवडलेलं नाही —")] + [
            ft.dropdown.Option(key=str(a["id"]), text=f"{a['name']} ({a['account_type']})") for a in accounts
        ]
        if self.page:
            self.account_dropdown.update()

    # ======================================================================
    def _on_payment_mode_change(self, e):
        # Credit निवडलं तर डिफॉल्ट Paid Amount 0 करतो (पूर्ण उधारी गृहीत धरून)
        if self.payment_mode.value == "Credit":
            self.paid_amt.value = "0"
        else:
            self.paid_amt.value = self._grand_total_str()
        self._recalc()

    def _on_gst_toggle_change(self, e):
        # GST Bill निवडलं तरच GSTIN/Place-of-Supply फील्ड्स दिसतील
        self.customer_gstin.visible = self.gst_bill_toggle.value
        self.customer_state.visible = self.gst_bill_toggle.value
        self._recalc()
        if self.page:
            self.update()

    # ======================================================================
    # Cart — Add / Remove
    # ======================================================================
    def handle_add_part(self, e):
        if not self.part_dropdown.value:
            self._show_status("⚠️ आधी एक Part निवडा.", "#ff4444")
            return
        try:
            qty = float(self.part_qty.value or 0)
            discount = float(self.part_discount.value or 0)
        except ValueError:
            self._show_status("⚠️ Qty/Discount फक्त नंबरमध्ये.", "#ff4444")
            return
        if qty <= 0:
            self._show_status("⚠️ Qty शून्यापेक्षा जास्त असावी.", "#ff4444")
            return

        part = get_part_by_id(int(self.part_dropdown.value))
        if not part:
            return

        gross = qty * (part["sell_rate"] or 0)
        net_amount = gross - (gross * discount / 100)

        item = {
            "part_id": part["id"],
            "product_name": part["product_name"],
            "part_number": part["part_number"] or "",
            "qty": qty,
            "buying_rate": part["buying_rate"] or 0,
            "sell_rate": part["sell_rate"] or 0,
            "discount_percent": discount,
            "net_amount": net_amount,
            "hsn_sac": part["hsn_sac"] if "hsn_sac" in part.keys() and part["hsn_sac"] else "",
            "gst_rate": part["gst_rate"] if "gst_rate" in part.keys() and part["gst_rate"] is not None else 18,
        }
        self.cart.append(item)
        self._refresh_cart_ui()

        self.part_qty.value = "1"
        self.part_discount.value = "0"
        self.status_text.visible = False
        self.page.update()

    def _remove_from_cart(self, index):
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
            self._refresh_cart_ui()
            self.page.update()

    def _auto_cap(self, field):
        """नाव टाईप करताना, स्पेस देऊन नवीन शब्द सुरू केला की त्याचं पहिलं
        अक्षर आपोआप Capital करतो (उरलेलं जसंच्या तसं)."""
        value = field.value or ""
        capitalized = auto_capitalize_words(value)
        if capitalized != value:
            field.value = capitalized
            if self.page:
                field.update()

    def _try_autofill(self, value):
        """नाव/मोबाईल/गाडी नंबर यापैकी कुठलंही टाकून फोकस सोडला की, जुना
        ग्राहक असेल तर बाकीच्या रिकाम्या फील्ड्स आपोआप भरतो — आधीच काही
        टाईप केलेलं असेल तर ते ओव्हरराईट करत नाही."""
        row = smart_customer_lookup(value)
        if not row:
            return

        filled_something = False
        if not (self.customer_name.value or "").strip() and row["name"]:
            self.customer_name.value = row["name"]
            filled_something = True
        if not (self.mobile.value or "").strip() and row["mobile"]:
            self.mobile.value = row["mobile"]
            filled_something = True
        if not (self.vehicle.value or "").strip() and row["vehicle"]:
            self.vehicle.value = row["vehicle"]
            filled_something = True
        if not (self.vehicle_no.value or "").strip() and row["vehicle_no"]:
            self.vehicle_no.value = row["vehicle_no"]
            filled_something = True
        if "client_id" in row.keys() and row["client_id"]:
            self.client_dropdown.value = str(row["client_id"])
            filled_something = True

        if filled_something and self.page:
            self.update()
            self._show_status("ℹ️ जुना ग्राहक सापडला — माहिती आपोआप भरली.", "#00aaff")

    def _refresh_cart_ui(self):
        self._recalc()  # हेच आता Item Table + Bill Summary दोन्ही रीबिल्ड करतं

    def _rebuild_item_table(self, labour):
        rows = []
        for i, item in enumerate(self.cart):
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(i + 1), size=11, color="white")),
                ft.DataCell(ft.Text(item["product_name"], size=11, color="white")),
                ft.DataCell(ft.Text(item.get("hsn_sac", "") or "-", size=11, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{item['qty']:.0f}", size=11, color="white")),
                ft.DataCell(ft.Text(f"{item['sell_rate']:.2f}", size=11, color="white")),
                ft.DataCell(ft.Text(f"{item.get('gst_rate', 18):.0f}%", size=11, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{item['discount_percent']:.0f}%", size=11, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{item['net_amount']:.2f}", size=11, weight="bold", color="#00ffaa")),
                ft.DataCell(ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, icon_color="#ff4444",
                                          on_click=lambda e, idx=i: self._remove_from_cart(idx))),
            ]))
        if labour > 0:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("-", size=11, color="white")),
                ft.DataCell(ft.Text("Labour Charge", size=11, italic=True, color="white")),
                ft.DataCell(ft.Text("998714", size=11, color="#94a3b8")),
                ft.DataCell(ft.Text("1", size=11, color="white")),
                ft.DataCell(ft.Text(f"{labour:.2f}", size=11, color="white")),
                ft.DataCell(ft.Text("18%", size=11, color="#94a3b8")),
                ft.DataCell(ft.Text("0%", size=11, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{labour:.2f}", size=11, weight="bold", color="#00ffaa")),
                ft.DataCell(ft.Text("")),
            ]))
        self.item_table.rows = rows
        if self.page:
            self.item_table.update()

    def _gst_preview(self):
        """GST Bill टॉगल चालू असेल तरच — Grand Total मधून मागच्या बाजूने GST
        किती आहे ते दाखवतं (invoice.py मधल्याच price_includes_gst=True सूत्राने,
        फक्त इथे लाइव्ह प्रीव्ह्यूसाठी — अंतिम बिल invoice.py मध्येच बनतं)."""
        if not self.gst_bill_toggle.value:
            return 0.0
        total_tax = 0.0
        for item in self.cart:
            rate = item.get("gst_rate", 18) or 18
            taxable = item["net_amount"] / (1 + rate / 100) if rate else item["net_amount"]
            total_tax += item["net_amount"] - taxable
        try:
            labour = float(self.labour_charge.value or 0)
        except ValueError:
            labour = 0
        if labour > 0:
            taxable = labour / 1.18
            total_tax += labour - taxable
        return total_tax

    # ======================================================================
    # Totals
    # ======================================================================
    def _parts_total(self):
        return sum(item["net_amount"] for item in self.cart)

    def _grand_total_str(self):
        try:
            labour = float(self.labour_charge.value or 0)
        except ValueError:
            labour = 0
        return f"{self._parts_total() + labour:.2f}"

    def _recalc(self):
        parts_total = self._parts_total()
        try:
            labour = float(self.labour_charge.value or 0)
        except ValueError:
            labour = 0
        grand_total = parts_total + labour

        self.parts_total_text.value = f"₹{parts_total:.0f}"
        self.grand_total_text.value = f"₹{grand_total:.0f}"

        try:
            paid = float(self.paid_amt.value or 0)
        except ValueError:
            paid = 0
        due = max(grand_total - paid, 0)
        self.due_amt_text.value = f"₹{due:.0f}"

        # ---- उजवीकडचा प्रोफेशनल Item List + Bill Summary ----
        self._rebuild_item_table(labour)
        gst_amt = self._gst_preview()
        self.sub_total_text.value = f"₹{grand_total:,.2f}"
        self.gst_summary_row.visible = self.gst_bill_toggle.value
        self.gst_summary_text.value = f"₹{gst_amt:,.2f}  (Taxable ₹{grand_total - gst_amt:,.2f})"
        self.summary_net_total_text.value = f"₹{grand_total:,.2f}"
        self.summary_paid_text.value = f"₹{paid:,.2f}"
        self.summary_due_text.value = f"₹{due:,.2f}"

        if self.page:
            self.update()

    # ======================================================================
    # SAVE — इथेच सगळं एकत्र होतं (Udhaari + Part Usage + Daily Work + Ledger + PDF)
    # ======================================================================
    def handle_save_sale(self, e):
        name = (self.customer_name.value or "").strip()
        if not name:
            self._show_status("⚠️ Customer Name भरा.", "#ff4444")
            return

        parts_total = self._parts_total()
        try:
            labour = float(self.labour_charge.value or 0)
        except ValueError:
            self._show_status("⚠️ Labour Charge फक्त नंबरमध्ये.", "#ff4444")
            return

        grand_total = parts_total + labour
        if grand_total <= 0:
            self._show_status("⚠️ किमान एक Part किंवा Labour Charge टाका.", "#ff4444")
            return

        try:
            paid_amt = float(self.paid_amt.value or 0)
        except ValueError:
            self._show_status("⚠️ Paid Amount फक्त नंबरमध्ये.", "#ff4444")
            return

        due_amt = max(grand_total - paid_amt, 0)
        client_id = int(self.client_dropdown.value) if self.client_dropdown.value else None
        tx_date = (self.tx_date.value or "").strip()
        work_desc = (self.work_desc.value or "").strip() or "Service / Work"

        try:
            # 1) Udhaari रेकॉर्ड — Total/Paid/Due सह (due>0 म्हणजे आपोआप उधारी)
            new_id = add_udhaari(
                name=name, mobile=(self.mobile.value or "").strip(),
                vehicle=(self.vehicle.value or "").strip(),
                vehicle_no=(self.vehicle_no.value or "").strip(),
                address="", tx_date=tx_date, due_date="",
                total_amt=grand_total, paid_amt=paid_amt, due_amt=due_amt,
                notes=work_desc, type="Given", client_id=client_id,
            )

            # 2) प्रत्येक Part साठी usage नोंद — स्टॉक आपोआप वजा + profit ट्रॅक
            for item in self.cart:
                add_part_usage(
                    reference_table="udhaari", reference_id=new_id,
                    part_id=item["part_id"], product_name=item["product_name"],
                    part_number=item["part_number"], qty=item["qty"],
                    buying_rate=item["buying_rate"], sell_rate=item["sell_rate"],
                    discount_percent=item["discount_percent"],
                    tx_date=tx_date, notes="Sale",
                )

            # 3) Daily Work Log नोंद
            parts_names = ", ".join(item["product_name"] for item in self.cart)
            add_work(
                customer_name=name, vehicle=(self.vehicle.value or "").strip(),
                work_desc=work_desc, charge_amt=grand_total, work_date=tx_date,
                status="Done", mobile=(self.mobile.value or "").strip(),
                vehicle_no=(self.vehicle_no.value or "").strip(),
                labour_charge=labour, parts_charge=parts_total, parts_used=parts_names,
            )

            # 4) आत्ता मिळालेली रक्कम — निवडलेल्या Account च्या ledger मध्ये जमा
            if paid_amt > 0 and self.account_dropdown.value:
                add_transaction(
                    int(self.account_dropdown.value), "credit", paid_amt,
                    category=f"Sale: {name}", tx_date=tx_date, notes=work_desc,
                    reference_table="udhaari", reference_id=new_id,
                )

            # 5) PDF Invoice — GST Bill असेल तर Santosh Diesel स्टाईल पूर्ण Tax
            #    Invoice (gst_invoice_pro.py), नाहीतर आधीचं साधं A4/A5 बिल (invoice.py)
            row = get_by_id(new_id)
            downloads_dir = _get_output_dir()
            safe_name = "".join(ch if ch.isalnum() else "_" for ch in name)
            pdf_path = os.path.join(downloads_dir, f"Bill_{safe_name}_{new_id}.pdf")

            is_gst = self.gst_bill_toggle.value
            customer_state = "Maharashtra" if self.customer_state.value != "Other State" else "Other State"

            if is_gst:
                gst_line_items = [
                    {
                        "description": item["product_name"], "hsn_sac": item["hsn_sac"],
                        "part_no": item["part_number"] or "-",
                        "qty": item["qty"], "rate": item["sell_rate"],
                        "discount_percent": item["discount_percent"], "gst_rate": item["gst_rate"],
                    }
                    for item in self.cart
                ]
                if labour > 0:
                    gst_line_items.append({
                        "description": "Labour Charge", "hsn_sac": "998714", "part_no": "-",
                        "qty": 1, "rate": labour, "discount_percent": 0, "gst_rate": 18,
                    })
                generate_full_gst_invoice(
                    buyer={
                        "name": name, "mobile": (self.mobile.value or "").strip(),
                        "address": (self.vehicle.value or "").strip(), "gstin": (self.customer_gstin.value or "").strip(),
                        "state": customer_state,
                    },
                    line_items=gst_line_items, filepath=pdf_path,
                    invoice_no=f"INV-{new_id:04d}", invoice_date=tx_date,
                    mode_of_payment=self.payment_mode.value or "Cash",
                    is_intra_state=(customer_state == "Maharashtra"),
                    notes=work_desc,
                )
            else:
                line_items = [
                    {
                        "description": item["product_name"], "hsn_sac": item["hsn_sac"],
                        "qty": item["qty"], "rate": item["sell_rate"],
                        "discount_percent": item["discount_percent"], "gst_rate": item["gst_rate"],
                    }
                    for item in self.cart
                ]
                if labour > 0:
                    line_items.append({
                        "description": "Labour Charge", "hsn_sac": "998714",
                        "qty": 1, "rate": labour, "discount_percent": 0, "gst_rate": 18,
                    })
                generate_invoice(
                    row, pdf_path, page_size=self.paper_size.value or "A5",
                    is_gst=False, line_items=line_items,
                )


        except Exception as ex:
            import traceback
            traceback.print_exc()  # टर्मिनलमध्ये पूर्ण एरर दिसेल — डिबगसाठी उपयोगी
            self._show_status(f"❌ एरर: {ex}", "#ff4444")
            return

        self._show_status(f"✅ Sale सेव्ह झाली! Bill: {pdf_path}", "#00ffaa")
        if self.refresh_callback:
            self.refresh_callback()
        self._clear_form()

    def _show_status(self, msg, color):
        """टीप: फक्त वरचा छोटा status_text दाखवण्याऐवजी, आता SnackBar सुद्धा
        दाखवतो — फॉर्म खाली scroll केलेला असेल तरी मेसेज चुकणार नाही.
        Save क्लिक केल्यावर 'काहीच झालं नाही' असं वाटू नये म्हणून हे मुद्दाम
        जोडलंय — प्रत्यक्षात बहुतेकदा वरचा (न दिसलेला) status_text मध्येच
        Customer Name/Amount आवश्यक असल्याचा इशारा आधीच येत असतो."""
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        if self.page:
            self.status_text.update()
            try:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(msg, color="white"),
                    bgcolor=("#1f8f5f" if color == "#00ffaa" else "#b3261e"),
                    open=True,
                )
                self.page.update()
            except Exception:
                pass  # SnackBar फेल झालं तरी वरचा status_text तरी दिसेलच
        else:
            print(f"[BillingView status] {msg}")  # डिबगसाठी टर्मिनलमध्येही दिसेल

    def _clear_form(self):
        for f in (self.customer_name, self.mobile, self.vehicle, self.vehicle_no, self.work_desc):
            f.value = ""
        self.client_dropdown.value = ""
        self.tx_date.value = datetime.now().strftime("%d.%m.%Y")
        self.labour_charge.value = "0"
        self.paid_amt.value = "0"
        self.payment_mode.value = "Cash"
        self.account_dropdown.value = ""
        self.paper_size.value = "A5"
        self.gst_bill_toggle.value = False
        self.customer_gstin.value = ""
        self.customer_gstin.visible = False
        self.customer_state.value = "Maharashtra"
        self.customer_state.visible = False
        self.cart = []
        self._refresh_cart_ui()
        self._load_part_options()  # ताजा stock दाखवण्यासाठी
        if self.page:
            self.update()
