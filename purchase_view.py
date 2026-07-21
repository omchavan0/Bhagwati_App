"""
============================================================================
PURCHASE VIEW — Supplier कडून Parts खरेदी (Input GST + Auto Stock-In)
============================================================================
gst_billing_view.py च्याच पॅटर्नवर बनवलंय, पण दिशा उलट: इथे स्टॉक वजा
न होता वाढतो (record_stock_in), आणि Udhaari ऐवजी Purchase Bill (Payable)
तयार होतो. जुन्या billing_view.py/gst_billing_view.py प्रमाणेच Save वर सगळं
(Bill + Stock + Finance Ledger) एकत्र होतं.
============================================================================
"""
from datetime import datetime

import flet as ft

from database import (
    get_suppliers, add_supplier,
    search_parts, get_part_by_id, get_part_stock,
    get_accounts, add_transaction,
    add_purchase_bill, add_purchase_item, 
)
from gst_utils import determine_tax_mode, split_tax
from db_inventory import record_stock_in, update_part
from customer_lookup import auto_capitalize_words

PAYMENT_MODES = ["Cash", "UPI", "Bank Transfer", "Cheque", "Credit"]


class PurchaseView(ft.Row):
    """Supplier कडून खरेदी — Item Grid + Auto GST + Auto Stock-In."""

    def __init__(self, refresh_callback=None):
        super().__init__(expand=True)
        self.refresh_callback = refresh_callback
        self.cart = []  # dict(part_id, product_name, part_number, hsn_sac, gst_rate, qty, rate, discount_percent)
        self.selected_supplier = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        # ---------------- Top ----------------
        self.bill_no = ft.TextField(label="🧾 Supplier Bill No", height=48, **S)
        self.bill_date = ft.TextField(label="📅 Bill Date (DD.MM.YYYY)", height=48,
                                       value=datetime.now().strftime("%d.%m.%Y"), **S)
        self.supplier_dropdown = ft.Dropdown(label="🏭 Supplier निवडा *", height=48, expand=True, **S)
        self.supplier_search = ft.TextField(label="🔍 नवीन/शोधा", height=48, width=200, **S)
        self.supplier_search.on_submit = self._quick_add_supplier

        # ---------------- Item Grid Add-Row ----------------
        self.part_dropdown = ft.Dropdown(label="🔩 Part निवडा", height=48, expand=True, **S)
        self.item_qty = ft.TextField(label="Qty", height=48, width=80, value="1",
                                      keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.item_rate = ft.TextField(label="Purchase Rate", height=48, width=120,
                                       keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.item_discount = ft.TextField(label="Disc%", height=48, width=80, value="0",
                                           keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.add_item_btn = ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="#00ffaa",
                                           icon_size=32, tooltip="Item जोडा",
                                           on_click=self.handle_add_item)

        # ---------------- Item Grid ----------------
        self.item_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("SI", size=10, color="#94a3b8")),
                ft.DataColumn(ft.Text("Item", size=10, color="#94a3b8")),
                ft.DataColumn(ft.Text("HSN", size=10, color="#94a3b8")),
                ft.DataColumn(ft.Text("Qty", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Rate", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Disc%", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("GST%", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Amount", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("")),
            ],
            rows=[], column_spacing=10, data_row_min_height=36, data_row_max_height=42,
            heading_row_color="#161622", heading_row_height=34,
        )
        self.item_table_holder = ft.Container(
            content=ft.Column([self.item_table], scroll="auto"),
            height=240, bgcolor="#0e0e16", border_radius=10,
            border=ft.Border(top=ft.BorderSide(1, "#1a1a26"), bottom=ft.BorderSide(1, "#1a1a26"),
                              left=ft.BorderSide(1, "#1a1a26"), right=ft.BorderSide(1, "#1a1a26")),
            padding=8,
        )

        # ---------------- Other Charges ----------------
        self.discount = ft.TextField(label="💸 Extra Discount (₹)", height=48, value="0",
                                      keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.transport = ft.TextField(label="🚚 Transport", height=48, value="0",
                                       keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.other_charges = ft.TextField(label="➕ Other Charges", height=48, value="0",
                                           keyboard_type=ft.KeyboardType.NUMBER, **S)
        for f in (self.discount, self.transport, self.other_charges):
            f.on_change = lambda e: self._recalc()

        # ---------------- Payment ----------------
        self.payment_mode = ft.Dropdown(label="💳 Payment Mode", height=48, value="Cash",
                                         options=[ft.dropdown.Option(m) for m in PAYMENT_MODES], **S)
        self.payment_mode.on_change = self._on_payment_mode_change
        self.account_dropdown = ft.Dropdown(label="🏦 Account (पैसे कुठून दिले)", height=48, **S)
        self.paid_amt = ft.TextField(label="✅ Paid Amount", height=48, value="0",
                                      keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.paid_amt.on_change = lambda e: self._recalc()

        # ---------------- Summary ----------------
        self.taxable_text = ft.Text("₹0", size=13, color="white")
        self.cgst_text = ft.Text("₹0", size=13, color="#00aaff")
        self.sgst_text = ft.Text("₹0", size=13, color="#00aaff")
        self.igst_text = ft.Text("₹0", size=13, color="#00aaff")
        self.round_off_text = ft.Text("₹0", size=13, color="#94a3b8")
        self.grand_total_text = ft.Text("₹0", size=22, weight="bold", color="#00ffaa")
        self.due_text = ft.Text("₹0", size=15, weight="bold", color="#ff8800")

        self.status_text = ft.Text("", size=13, visible=False)
        self.save_btn = ft.ElevatedButton(
            "💾 Purchase Bill Save करा", bgcolor="#00ffaa", color="black",
            height=52, expand=True, on_click=self.handle_save_purchase,
        )
        self.new_btn = ft.OutlinedButton("🆕 New", height=52, on_click=lambda e: self._clear_form())

        def _sum_row(label, ctrl):
            return ft.Row([ft.Text(label, size=12, color="#94a3b8"), ft.Container(expand=True), ctrl])

        self.summary_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text("🧾 Purchase Summary", size=14, weight="bold", color="white"),
                    ft.Divider(color="#1a1a26"),
                    _sum_row("Taxable Value", self.taxable_text),
                    _sum_row("CGST", self.cgst_text),
                    _sum_row("SGST", self.sgst_text),
                    _sum_row("IGST", self.igst_text),
                    _sum_row("Round Off", self.round_off_text),
                    ft.Divider(color="#1a1a26"),
                    _sum_row("Grand Total", self.grand_total_text),
                    ft.Container(height=4),
                    _sum_row("Balance Payable", self.due_text),
                ],
                spacing=8,
            ),
            bgcolor="#161622", padding=16, border_radius=12,
        )

        left = ft.Container(
            content=ft.Column(
                [
                    ft.Text("📥 Purchase Entry (खरेदी)", size=20, weight="bold", color="#00ffaa"),
                    self.status_text,
                    ft.Row([self.bill_no, self.bill_date], spacing=10),
                    ft.Row([self.supplier_dropdown, self.supplier_search], spacing=8),
                    ft.Divider(color="#1a1a26"),
                    ft.Text("🛒 Item Grid", size=14, weight="bold", color="white"),
                    ft.Row([self.part_dropdown, self.item_qty, self.item_rate,
                            self.item_discount, self.add_item_btn], spacing=8),
                    self.item_table_holder,
                    ft.Divider(color="#1a1a26"),
                    ft.Text("Other Charges", size=13, weight="bold", color="white"),
                    ft.Row([self.discount, self.transport, self.other_charges], spacing=10),
                ],
                scroll="auto", spacing=10,
            ),
            padding=20, expand=True, bgcolor="#0e0e16",
        )

        right = ft.Container(
            content=ft.Column(
                [
                    ft.Text("💰 Payment & Summary", size=16, weight="bold", color="#00ffaa"),
                    self.payment_mode,
                    self.account_dropdown,
                    self.paid_amt,
                    ft.Container(height=6),
                    self.summary_box,
                    ft.Container(height=10),
                    ft.Row([self.new_btn]),
                    self.save_btn,
                ],
                spacing=10, scroll="auto",
            ),
            padding=20, width=380, bgcolor="#0e0e16",
        )

        self.controls = [left, ft.VerticalDivider(width=1, color="#1a1a26"), right]

    # ======================================================================
    def did_mount(self):
        self._load_supplier_options()
        self._load_part_options()
        self._load_account_options()
        self._recalc()

    def _load_supplier_options(self, select_id=None):
        suppliers = get_suppliers()
        self.supplier_dropdown.options = [
            ft.dropdown.Option(key=str(s["id"]), text=f"{s['name']} — {s['mobile'] or ''}") for s in suppliers
        ]
        self.supplier_dropdown.value = str(select_id) if select_id else None
        self.supplier_dropdown.on_change = self._on_supplier_selected
        if self.page:
            self.supplier_dropdown.update()

    def _load_part_options(self):
        opts = []
        for p in search_parts(None):
            stock = get_part_stock(p["id"])
            opts.append(ft.dropdown.Option(
                key=str(p["id"]),
                text=f"{p['product_name']} (Stock: {stock:.0f}, Buy ₹{p['buying_rate']:.0f})",
            ))
        self.part_dropdown.options = opts
        self.part_dropdown.value = None
        self.part_dropdown.on_change = self._on_part_selected
        if self.page:
            self.part_dropdown.update()

    def _load_account_options(self):
        accounts = get_accounts()
        self.account_dropdown.options = [ft.dropdown.Option(key="", text="— निवडलेलं नाही —")] + [
            ft.dropdown.Option(key=str(a["id"]), text=f"{a['name']} ({a['account_type']})") for a in accounts
        ]
        if self.page:
            self.account_dropdown.update()

    def _on_part_selected(self, e):
        # Part निवडताच त्याचा existing buying_rate आपोआप भरतो (हवं तर बदलता येतं)
        if not self.part_dropdown.value:
            return
        part = get_part_by_id(int(self.part_dropdown.value))
        if part:
            self.item_rate.value = str(part["buying_rate"] or 0)
            if self.page:
                self.item_rate.update()

    def _on_supplier_selected(self, e):
        self.selected_supplier = None
        if self.supplier_dropdown.value:
            from database import get_supplier_by_id
            self.selected_supplier = get_supplier_by_id(int(self.supplier_dropdown.value))
        self._recalc()

    def _quick_add_supplier(self, e):
        name = (self.supplier_search.value or "").strip()
        if not name:
            return
        name = auto_capitalize_words(name)
        new_id = add_supplier(name=name)
        self.supplier_search.value = ""
        self._load_supplier_options(select_id=new_id)
        self._on_supplier_selected(None)
        self._show_status(f"ℹ️ नवीन Supplier '{name}' जोडला.", "#00aaff")

    # ======================================================================
    def handle_add_item(self, e):
        if not self.part_dropdown.value:
            self._show_status("⚠️ आधी एक Part निवडा.", "#ff4444")
            return
        try:
            qty = float(self.item_qty.value or 0)
            rate = float(self.item_rate.value or 0)
            discount = float(self.item_discount.value or 0)
        except ValueError:
            self._show_status("⚠️ Qty/Rate/Discount फक्त नंबरमध्ये.", "#ff4444")
            return
        if qty <= 0 or rate <= 0:
            self._show_status("⚠️ Qty आणि Rate शून्यापेक्षा जास्त असावी.", "#ff4444")
            return

        part = get_part_by_id(int(self.part_dropdown.value))
        if not part:
            return

        item = {
            "part_id": part["id"], "product_name": part["product_name"],
            "part_number": part["part_number"] or "",
            "hsn_sac": part["hsn_sac"] if "hsn_sac" in part.keys() and part["hsn_sac"] else "",
            "gst_rate": part["gst_rate"] if "gst_rate" in part.keys() and part["gst_rate"] is not None else 18,
            "qty": qty, "rate": rate, "discount_percent": discount,
        }
        self.cart.append(item)
        self.item_qty.value = "1"
        self.item_discount.value = "0"
        self.status_text.visible = False
        self._recalc()

    def _remove_from_cart(self, index):
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
            self._recalc()

    # ======================================================================
    def _get_tax_mode(self):
        from database import get_company_settings
        company = get_company_settings()
        company_state_code = company["state_code"] if company else "27"
        supplier_state_code = self.selected_supplier["state_code"] if self.selected_supplier else company_state_code
        return determine_tax_mode(company_state_code, supplier_state_code)

    def _on_payment_mode_change(self, e):
        if self.payment_mode.value == "Credit":
            self.paid_amt.value = "0"
        self._recalc()

    def _rebuild_item_table(self):
        rows = []
        for i, item in enumerate(self.cart):
            gross = item["qty"] * item["rate"]
            line_amount = gross - (gross * item["discount_percent"] / 100)
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(i + 1), size=10, color="white")),
                ft.DataCell(ft.Text(item["product_name"], size=10, color="white")),
                ft.DataCell(ft.Text(item["hsn_sac"] or "-", size=10, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{item['qty']:.0f}", size=10, color="white")),
                ft.DataCell(ft.Text(f"{item['rate']:.2f}", size=10, color="white")),
                ft.DataCell(ft.Text(f"{item['discount_percent']:.0f}%", size=10, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{item['gst_rate']:.0f}%", size=10, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{line_amount:.2f}", size=10, weight="bold", color="#00ffaa")),
                ft.DataCell(ft.IconButton(icon=ft.Icons.CLOSE, icon_size=13, icon_color="#ff4444",
                                          on_click=lambda e, idx=i: self._remove_from_cart(idx))),
            ]))
        self.item_table.rows = rows
        if self.page:
            self.item_table.update()

    def _recalc(self):
        tax_mode = self._get_tax_mode()
        taxable_total = cgst_total = sgst_total = igst_total = items_total = 0.0

        for item in self.cart:
            gross = item["qty"] * item["rate"]
            line_amount = gross - (gross * item["discount_percent"] / 100)
            split = split_tax(line_amount, item["gst_rate"], tax_mode, price_includes_gst=False)
            items_total += split["final_amount"]
            taxable_total += split["taxable"]
            cgst_total += split["cgst"]
            sgst_total += split["sgst"]
            igst_total += split["igst"]

        try:
            discount = float(self.discount.value or 0)
        except ValueError:
            discount = 0
        try:
            transport = float(self.transport.value or 0)
        except ValueError:
            transport = 0
        try:
            other = float(self.other_charges.value or 0)
        except ValueError:
            other = 0

        raw_total = items_total - discount + transport + other
        rounded_total = round(raw_total)
        round_off = rounded_total - raw_total

        try:
            paid = float(self.paid_amt.value or 0)
        except ValueError:
            paid = 0
        due = max(rounded_total - paid, 0)

        self._rebuild_item_table()
        self.taxable_text.value = f"₹{taxable_total:,.2f}"
        self.cgst_text.value = f"₹{cgst_total:,.2f}"
        self.sgst_text.value = f"₹{sgst_total:,.2f}"
        self.igst_text.value = f"₹{igst_total:,.2f}"
        self.round_off_text.value = f"₹{round_off:,.2f}"
        self.grand_total_text.value = f"₹{rounded_total:,.2f}"
        self.due_text.value = f"₹{due:,.2f}"

        self._last_calc = {
            "taxable_total": taxable_total, "cgst_total": cgst_total, "sgst_total": sgst_total,
            "igst_total": igst_total, "discount": discount, "transport": transport, "other": other,
            "rounded_total": rounded_total, "round_off": round_off, "paid": paid, "due": due,
            "items_total": items_total,
        }

        if self.page:
            self.update()

    # ======================================================================
    def handle_save_purchase(self, e):
        if not self.supplier_dropdown.value:
            self._show_status("⚠️ आधी Supplier निवडा.", "#ff4444")
            return
        if not self.cart:
            self._show_status("⚠️ किमान एक Item Grid मध्ये जोडा.", "#ff4444")
            return

        calc = self._last_calc
        supplier = self.selected_supplier
        bill_date = (self.bill_date.value or "").strip()

        try:
            purchase_id = add_purchase_bill(
                supplier_name=supplier["name"], supplier_id=supplier["id"],
                bill_no=(self.bill_no.value or "").strip(), bill_date=bill_date,
                sub_total=calc["items_total"], discount=calc["discount"],
                transport=calc["transport"], other_charges=calc["other"],
                taxable_value=calc["taxable_total"], cgst=calc["cgst_total"],
                sgst=calc["sgst_total"], igst=calc["igst_total"],
                round_off=calc["round_off"], grand_total=calc["rounded_total"],
                paid_amt=calc["paid"], due_amt=calc["due"],
                payment_mode=self.payment_mode.value or "Cash",
                notes=f"Purchase from {supplier['name']}",
            )

            for item in self.cart:
                gross = item["qty"] * item["rate"]
                line_amount = gross - (gross * item["discount_percent"] / 100)
                add_purchase_item(
                    purchase_id=purchase_id, part_id=item["part_id"],
                    product_name=item["product_name"], part_number=item["part_number"],
                    hsn_sac=item["hsn_sac"], qty=item["qty"], purchase_rate=item["rate"],
                    gst_rate=item["gst_rate"], discount_percent=item["discount_percent"],
                    net_amount=line_amount, tx_date=bill_date,
                )
                update_part(part_id=item["part_id"], buy_rate=item["rate"])

            if calc["paid"] > 0 and self.account_dropdown.value:
                add_transaction(
                    int(self.account_dropdown.value), "debit", calc["paid"],
                    category=f"Purchase: {supplier['name']}", tx_date=bill_date,
                    notes=self.bill_no.value or "", reference_table="purchase_bills",
                    reference_id=purchase_id,
                )

        except Exception as ex:
            import traceback
            traceback.print_exc()
            self._show_status(f"❌ एरर: {ex}", "#ff4444")
            return

        self._show_status(f"✅ Purchase Bill सेव्ह झालं! स्टॉक आपोआप जमा झाला.", "#00ffaa")
        if self.refresh_callback:
            self.refresh_callback()
        self._clear_form()

    # ======================================================================
    def _show_status(self, msg, color):
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        if self.page:
            self.status_text.update()

    def _clear_form(self):
        self.bill_no.value = ""
        self.bill_date.value = datetime.now().strftime("%d.%m.%Y")
        self.supplier_dropdown.value = None
        self.selected_supplier = None
        self.supplier_search.value = ""
        self.discount.value = "0"
        self.transport.value = "0"
        self.other_charges.value = "0"
        self.payment_mode.value = "Cash"
        self.account_dropdown.value = ""
        self.paid_amt.value = "0"
        self.cart = []
        self._load_supplier_options()
        self._load_part_options()
        self._recalc()