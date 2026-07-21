"""
============================================================================
GST BILLING VIEW — Tally/Vyapar-Style Professional GST Invoice Screen
============================================================================
"""
import os
from datetime import datetime

import flet as ft

from database import (
    get_customers, add_customer,
    get_clients, add_client,
    search_parts, get_part_by_id, get_part_stock, add_part_usage,
    get_labour_list,
    get_accounts, add_transaction,
    add_udhaari, get_by_id, add_work,
    get_company_settings, get_next_invoice_number,
)
from gst_invoice_pro import generate_full_gst_invoice
from gst_utils import determine_tax_mode, split_tax
from gst_invoice_calc_engine import calculate_row
from customer_lookup import auto_capitalize_words

PAYMENT_MODES = ["Cash", "UPI", "Bank Transfer", "Card", "Cheque", "Credit"]


def _get_output_dir():
    try:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads, exist_ok=True)
        return downloads
    except Exception:
        fallback = os.path.join(os.getcwd(), "invoices")
        os.makedirs(fallback, exist_ok=True)
        return fallback


class GSTBillingView(ft.Row):
    def __init__(self, refresh_callback=None):
        super().__init__(expand=True)
        self.refresh_callback = refresh_callback
        self.cart = []
        self.selected_customer = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        self.invoice_no_text = ft.Text("", size=13, weight="bold", color="#00ffaa")
        self.invoice_date = ft.TextField(label="📅 Invoice Date (DD.MM.YYYY)", height=48,
                                          value=datetime.now().strftime("%d.%m.%Y"), **S)
        self.sales_person = ft.TextField(label="🧑‍💼 Sales Person", height=48, **S)

        self.customer_dropdown = ft.Dropdown(label="👤 Customer निवडा *", height=48, expand=True, **S)
        self.customer_search = ft.TextField(label="🔍 नवीन/शोधा", height=48, width=200,
                                             on_submit=self._quick_add_customer, **S)
        self.customer_info_text = ft.Text("", size=11, color="#94a3b8")

        # ---------------- Garage/Client Group (optional) ----------------
        self.client_dropdown = ft.Dropdown(label="🏢 Garage / Client (optional)", height=48, expand=True, **S)
        self.quick_add_client_btn = ft.IconButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINE, icon_color="#00ffaa",
            tooltip="नवीन Client पटकन जोडा",
            on_click=self._open_quick_add_client,
        )
        self.qc_garage = ft.TextField(label="🏢 Garage Name *", height=52, **S)
        self.qc_owner = ft.TextField(label="👤 Owner Name", height=52, **S)
        self.qc_mobile = ft.TextField(label="📱 Mobile", height=52, **S)
        self.qc_location = ft.TextField(label="📍 Location", height=52, **S)
        self.qc_msg = ft.Text("", size=12, color="#ff4444", visible=False)
        self.quick_add_client_dialog = ft.AlertDialog(
            title=ft.Text("➕ नवीन Client / Garage"),
            content=ft.Container(
                content=ft.Column([self.qc_garage, self.qc_owner, self.qc_mobile, self.qc_location, self.qc_msg],
                                   tight=True, spacing=10),
                width=360,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self._close_quick_add_client),
                ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black", on_click=self._save_quick_add_client),
            ],
        )

        # ---------------- 🧾 GST Bill Toggle — वर, Customer निवडल्यावर लगेच ----------------
        # टीप: GST हा नेहमी लागू असतोच (Registered dealer कायद्याने प्रत्येक sale वर
        # GST लावतो) — हा टॉगल फक्त "ग्राहकाचा GSTIN बिलावर टाकायचा का" ठरवतो:
        #   ✅ ON  -> GSTIN mandatory -> हा invoice पुढे GSTR-1 च्या B2B मध्ये मोजला जातो
        #   ❌ OFF -> GSTIN रिकामा राहतो -> आपोआप B2C मध्ये मोजला जातो
        # (db_gst_returns.get_gstr1_b2b/b2c हे customer_gstin भरलेला आहे का यावरच ठरवतात)
        self.gst_bill_toggle = ft.Switch(
            label="🧾 GST Bill? (ग्राहकाचा GSTIN टाकायचा — नाहीतर B2C)",
            value=False, active_color="#00ffaa",
            on_change=self._on_gst_toggle_change,
        )
        self.manual_gstin = ft.TextField(label="GSTIN (ग्राहकाचा) *", height=48, visible=False, **S)

        self.vehicle = ft.TextField(label="🚗 Vehicle", height=48, **S)
        self.vehicle_no = ft.TextField(label="🔢 Vehicle Number", height=48, **S)
        self.work_desc = ft.TextField(label="🔧 Work Description / Narration", height=48, **S)

        self.item_type_toggle = ft.Dropdown(
            label="प्रकार", height=48, width=110, value="Part",
            options=[ft.dropdown.Option("Part"), ft.dropdown.Option("Labour")], **S,
        )
        self.part_dropdown = ft.Dropdown(label="🔩 Part/Labour निवडा", height=48, expand=True, **S)
        self.item_qty = ft.TextField(label="Qty", height=48, width=80, value="1",
                                      keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.item_discount = ft.TextField(label="Disc%", height=48, width=80, value="0",
                                           keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.add_item_btn = ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="#00ffaa",
                                           icon_size=32, tooltip="Item Grid मध्ये जोडा",
                                           on_click=self.handle_add_item)
        self.item_type_toggle.on_change = lambda e: self._load_item_options()

        self.item_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Sr.No", size=10, color="#94a3b8")),
                ft.DataColumn(ft.Text("Part Name", size=10, color="#94a3b8")),
                ft.DataColumn(ft.Text("Part No", size=10, color="#94a3b8")),
                ft.DataColumn(ft.Text("HSN/SAC", size=10, color="#94a3b8")),
                ft.DataColumn(ft.Text("GST%", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Rate", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Qty", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Dis.%", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Amount", size=10, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("")),
            ],
            rows=[], column_spacing=10, data_row_min_height=36, data_row_max_height=42,
            heading_row_color="#161622", heading_row_height=34,
        )
        self.item_table_holder = ft.Container(
            content=ft.Column([self.item_table], scroll="auto"),
            height=240, bgcolor="#0e0e16", border_radius=10,
            border=ft.Border.all(1, "#1a1a26"), padding=8,
        )

        self.other_discount = ft.TextField(label="💸 Extra Discount (₹)", height=48, value="0",
                                            keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.transport_charge = ft.TextField(label="🚚 Transport", height=48, value="0",
                                              keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.packing_charge = ft.TextField(label="📦 Packing", height=48, value="0",
                                            keyboard_type=ft.KeyboardType.NUMBER, **S)
        for f in (self.other_discount, self.transport_charge, self.packing_charge):
            f.on_change = lambda e: self._recalc()

        self.payment_mode = ft.Dropdown(label="💳 Payment Mode", height=48, value="Cash",
                                         options=[ft.dropdown.Option(m) for m in PAYMENT_MODES], **S)
        self.payment_mode.on_change = self._on_payment_mode_change
        self.account_dropdown = ft.Dropdown(label="🏦 Account", height=48, **S)
        self.paid_amt = ft.TextField(label="✅ Paid Amount", height=48, value="0",
                                      keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.paid_amt.on_change = lambda e: self._recalc()

        # ---------------- Bill Size (A4/A5) — आपल्याच वापरासाठी ----------------
        self.paper_size = ft.Dropdown(
            label="🖨️ Bill Size", height=48, value="A5",
            options=[ft.dropdown.Option("A5", "A5 (अर्धा पेज)"),
                     ft.dropdown.Option("A4", "A4 (फुल पेज)")],
            **S,
        )

        self.sub_total_text = ft.Text("₹0", size=13, color="white")
        self.taxable_text = ft.Text("₹0", size=13, color="white")
        self.cgst_text = ft.Text("₹0", size=13, color="#00aaff")
        self.sgst_text = ft.Text("₹0", size=13, color="#00aaff")
        self.igst_text = ft.Text("₹0", size=13, color="#00aaff")
        self.round_off_text = ft.Text("₹0", size=13, color="#94a3b8")
        self.grand_total_text = ft.Text("₹0", size=22, weight="bold", color="#00ffaa")
        self.due_text = ft.Text("₹0", size=15, weight="bold", color="#ff8800")
        self.tax_mode_badge = ft.Container(visible=False)

        self.status_text = ft.Text("", size=13, visible=False)
        self.save_btn = ft.ElevatedButton(
            "💾 Save Invoice + Print", bgcolor="#00ffaa", color="black",
            height=52, expand=True, on_click=self.handle_save_invoice,
        )
        self.new_invoice_btn = ft.OutlinedButton("🆕 New Invoice", height=52, on_click=lambda e: self._clear_form())

        def _sum_row(label, ctrl):
            return ft.Row([ft.Text(label, size=12, color="#94a3b8"), ft.Container(expand=True), ctrl])

        self.summary_box = ft.Container(
            content=ft.Column(
                [
                    ft.Row([ft.Text("🧾 GST Summary", size=14, weight="bold", color="white"),
                            ft.Container(expand=True), self.tax_mode_badge]),
                    ft.Divider(color="#1a1a26"),
                    _sum_row("Sub Total", self.sub_total_text),
                    _sum_row("Taxable Value", self.taxable_text),
                    _sum_row("CGST", self.cgst_text),
                    _sum_row("SGST", self.sgst_text),
                    _sum_row("IGST", self.igst_text),
                    _sum_row("Round Off", self.round_off_text),
                    ft.Divider(color="#1a1a26"),
                    _sum_row("Grand Total", self.grand_total_text),
                    ft.Container(height=4),
                    _sum_row("Balance Due", self.due_text),
                ],
                spacing=8,
            ),
            bgcolor="#161622", padding=16, border_radius=12,
        )

        left = ft.Container(
            content=ft.Column(
                [
                    ft.Row([ft.Text("🧾 GST Billing", size=20, weight="bold", color="#00ffaa"),
                            ft.Container(expand=True), self.invoice_no_text]),
                    self.status_text,
                    ft.Row([self.invoice_date, self.sales_person], spacing=10),
                    ft.Divider(color="#1a1a26"),
                    ft.Row([self.customer_dropdown, self.customer_search], spacing=8),
                    self.customer_info_text,
                    ft.Row([self.client_dropdown, self.quick_add_client_btn],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=4),
                    self.gst_bill_toggle,
                    self.manual_gstin,
                    ft.Row([self.vehicle, self.vehicle_no], spacing=10),
                    self.work_desc,
                    ft.Divider(color="#1a1a26"),
                    ft.Text("🛒 Item Grid", size=14, weight="bold", color="white"),
                    ft.Row([self.item_type_toggle, self.part_dropdown, self.item_qty,
                            self.item_discount, self.add_item_btn], spacing=8),
                    self.item_table_holder,
                    ft.Divider(color="#1a1a26"),
                    ft.Text("Other Charges", size=13, weight="bold", color="white"),
                    ft.Row([self.other_discount, self.transport_charge, self.packing_charge], spacing=10),
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
                    self.paper_size,
                    ft.Container(height=6),
                    self.summary_box,
                    ft.Container(height=10),
                    ft.Row([self.new_invoice_btn]),
                    self.save_btn,
                ],
                spacing=10, scroll="auto",
            ),
            padding=20, width=380, bgcolor="#0e0e16",
        )

        self.controls = [left, ft.VerticalDivider(width=1, color="#1a1a26"), right]

    # ======================================================================
    def did_mount(self):
        if self.quick_add_client_dialog not in self.page.overlay:
            self.page.overlay.append(self.quick_add_client_dialog)
        self._load_customer_options()
        self._load_client_options()
        self._load_item_options()
        self._load_account_options()
        self._refresh_invoice_no()
        self._recalc()

    def _refresh_invoice_no(self):
        try:
            self.invoice_no_text.value = f"# {get_next_invoice_number()}"
        except Exception:
            self.invoice_no_text.value = "# INV-000001"
        if self.page:
            self.invoice_no_text.update()

    def _load_customer_options(self, select_id=None):
        customers = get_customers()
        self.customer_dropdown.options = [
            ft.dropdown.Option(key=str(c["id"]), text=f"{c['name']} — {c['mobile'] or ''}") for c in customers
        ]
        self.customer_dropdown.value = str(select_id) if select_id else None
        self.customer_dropdown.on_change = self._on_customer_selected
        if self.page:
            self.customer_dropdown.update()

    def _load_client_options(self, select_id=None):
        clients = get_clients()
        self.client_dropdown.options = [ft.dropdown.Option(key="", text="— कोणीही नाही —")] + [
            ft.dropdown.Option(key=str(c["id"]), text=c["garage_name"]) for c in clients
        ]
        if select_id is not None:
            self.client_dropdown.value = str(select_id)
        if self.page:
            self.client_dropdown.update()

    def _open_quick_add_client(self, e):
        self.qc_garage.value = ""
        self.qc_owner.value = ""
        self.qc_mobile.value = ""
        self.qc_location.value = ""
        self.qc_msg.visible = False
        self.quick_add_client_dialog.open = True
        self.page.update()

    def _close_quick_add_client(self, e):
        self.quick_add_client_dialog.open = False
        self.page.update()

    def _save_quick_add_client(self, e):
        garage = (self.qc_garage.value or "").strip()
        if not garage:
            self.qc_msg.value = "⚠️ Garage Name भरा."
            self.qc_msg.visible = True
            self.qc_msg.update()
            return
        new_id = add_client(
            garage_name=garage, owner_name=(self.qc_owner.value or "").strip(),
            mobile=(self.qc_mobile.value or "").strip(), location=(self.qc_location.value or "").strip(),
        )
        self.quick_add_client_dialog.open = False
        self._load_client_options(select_id=new_id)
        self.page.update()

    def _load_item_options(self):
        kind = self.item_type_toggle.value
        opts = []
        if kind == "Part":
            for p in search_parts(None):
                stock = get_part_stock(p["id"])
                opts.append(ft.dropdown.Option(key=f"part:{p['id']}",
                                                text=f"{p['product_name']} (Stock: {stock:.0f}, ₹{p['sell_rate']:.0f})"))
        else:
            for l in get_labour_list():
                opts.append(ft.dropdown.Option(key=f"labour:{l['id']}",
                                                text=f"{l['labour_name']} (₹{(l['labour_charge'] or 0):.0f})"))
        self.part_dropdown.options = opts
        self.part_dropdown.value = None
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
    # 🧾 GST Bill Toggle — GSTIN field दाखवणे/लपवणे + Customer वरून auto-fill
    # ======================================================================
    def _on_gst_toggle_change(self, e):
        self.manual_gstin.visible = self.gst_bill_toggle.value
        if not self.gst_bill_toggle.value:
            self.manual_gstin.value = ""
        if self.page:
            self.update()

    def _on_customer_selected(self, e):
        if not self.customer_dropdown.value:
            self.selected_customer = None
        else:
            from database import get_customer_by_id
            self.selected_customer = get_customer_by_id(int(self.customer_dropdown.value))
            if self.selected_customer:
                if not (self.vehicle.value or "").strip():
                    self.vehicle.value = self.selected_customer["vehicle"] or ""
                if not (self.vehicle_no.value or "").strip():
                    self.vehicle_no.value = self.selected_customer["vehicle_no"] or ""
                # Customer Master मध्ये आधीच GSTIN भरलेला असेल तर टॉगल आपोआप ON
                if self.selected_customer["gstin"]:
                    self.gst_bill_toggle.value = True
                    self.manual_gstin.value = self.selected_customer["gstin"]
                    self.manual_gstin.visible = True
        self._recalc()

    def _quick_add_customer(self, e):
        name = (self.customer_search.value or "").strip()
        if not name:
            return
        name = auto_capitalize_words(name)
        new_id = add_customer(name=name)
        self.customer_search.value = ""
        self._load_customer_options(select_id=new_id)
        self._on_customer_selected(None)
        self._show_status(f"ℹ️ नवीन Customer '{name}' जोडला — पूर्ण माहिती Customer Master मधून भरा.", "#00aaff")

    # ======================================================================
    def handle_add_item(self, e):
        if not self.part_dropdown.value:
            self._show_status("⚠️ आधी एक Item निवडा.", "#ff4444")
            return
        try:
            qty = float(self.item_qty.value or 0)
            discount = float(self.item_discount.value or 0)
        except ValueError:
            self._show_status("⚠️ Qty/Discount फक्त नंबरमध्ये.", "#ff4444")
            return
        if qty <= 0:
            self._show_status("⚠️ Qty शून्यापेक्षा जास्त असावी.", "#ff4444")
            return

        kind, raw_id = self.part_dropdown.value.split(":")
        item_id = int(raw_id)

        if kind == "part":
            part = get_part_by_id(item_id)
            if not part:
                return
            mrp = part["mrp"] if "mrp" in part.keys() and part["mrp"] else 0
            rate = part["sell_rate"] or mrp or 0
            item = {
                "kind": "part", "part_id": part["id"], "name": part["product_name"],
                "part_number": part["part_number"] or "",
                "hsn_sac": part["hsn_sac"] if "hsn_sac" in part.keys() and part["hsn_sac"] else "",
                "gst_rate": part["gst_rate"] if "gst_rate" in part.keys() and part["gst_rate"] is not None else 18,
                "unit": part["unit"] if "unit" in part.keys() and part["unit"] else "Nos",
                "mrp": mrp,
                "buying_rate": part["buying_rate"] or 0, "rate": rate,
                "qty": qty, "discount_percent": discount,
            }
        else:
            labour = get_labour_by_id_safe(item_id)
            if not labour:
                return
            gst_on = bool(labour["gst_enabled"]) if "gst_enabled" in labour.keys() else True
            item = {
                "kind": "labour", "labour_id": labour["id"], "name": labour["labour_name"],
                "part_number": "", "hsn_sac": labour["sac_code"] or "998714",
                "gst_rate": (labour["gst_rate"] or 18) if gst_on else 0,
                "unit": "Service", "mrp": 0,
                "buying_rate": 0, "rate": labour["labour_charge"] or 0,
                "qty": qty, "discount_percent": discount,
            }

        if item["rate"] <= 0:
            self._show_status(
                f"⚠️ '{item['name']}' चा Sell Rate/MRP दोन्ही ₹0 आहेत — आधी "
                "Inventory Master किंवा Stock-In मध्ये MRP/Sell Rate भरा.",
                "#ff8800",
            )
            return

        self.cart.append(item)
        self.item_qty.value = "1"
        self.item_discount.value = "0"
        self.status_text.visible = False
        self._recalc()

    def _remove_from_cart(self, index):
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
            self._recalc()

    def _get_tax_mode(self):
        company = get_company_settings()
        company_state_code = company["state_code"] if company else "27"
        customer_state_code = self.selected_customer["state_code"] if self.selected_customer else company_state_code
        return determine_tax_mode(company_state_code, customer_state_code)

    def _on_payment_mode_change(self, e):
        if self.payment_mode.value == "Credit":
            self.paid_amt.value = "0"
        self._recalc()

    def _calc_item(self, item):
        unit_price = item.get("mrp") or item["rate"]
        return calculate_row(
            description=item["name"], mrp=unit_price, qty=item["qty"],
            disc_percent=item["discount_percent"], gst_rate=item["gst_rate"],
            hsn_sac=item.get("hsn_sac", ""), part_no=item.get("part_number", "-"),
        )

    def _rebuild_item_table(self):
        rows = []
        for i, item in enumerate(self.cart):
            calc = self._calc_item(item)
            ex_gst_rate = calc["rate"]
            taxable_amount = calc["amount"]
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(i + 1), size=10, color="white")),
                ft.DataCell(ft.Text(item["name"], size=10, color="white")),
                ft.DataCell(ft.Text(item.get("part_number", "") or "-", size=10, color="#94a3b8")),
                ft.DataCell(ft.Text(item["hsn_sac"] or "-", size=10, color="#94a3b8")),
                ft.DataCell(ft.Text(f"{item['gst_rate']:.0f}%", size=10, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{ex_gst_rate:.2f}", size=10, color="white")),
                ft.DataCell(ft.Text(f"{item['qty']:.0f}", size=10, color="white")),
                ft.DataCell(ft.Text(f"{item['discount_percent']:.0f}%", size=10, color="#94a3b8")),
                ft.DataCell(ft.Text(f"₹{taxable_amount:.2f}", size=10, weight="bold", color="#00ffaa")),
                ft.DataCell(ft.IconButton(icon=ft.Icons.CLOSE, icon_size=13, icon_color="#ff4444",
                                          on_click=lambda e, idx=i: self._remove_from_cart(idx))),
            ]))
        self.item_table.rows = rows
        if self.page:
            self.item_table.update()

    def _recalc(self):
        tax_mode = self._get_tax_mode()
        self.tax_mode_badge.content = ft.Container(
            content=ft.Text("CGST+SGST (Intra-State)" if tax_mode == "intra" else "IGST (Inter-State)",
                             size=10, color="black"),
            bgcolor="#00ffaa" if tax_mode == "intra" else "#ff8800",
            border_radius=6, padding=ft.Padding(left=8, top=4, right=8, bottom=4),
        )
        self.tax_mode_badge.visible = True

        items_total = 0.0
        taxable_total = 0.0
        cgst_total = sgst_total = igst_total = 0.0

        for item in self.cart:
            calc = self._calc_item(item)
            taxable_amount = calc["amount"]
            gst_rate = item["gst_rate"]
            total_tax = taxable_amount * gst_rate / 100

            if tax_mode == "intra":
                cgst_total += total_tax / 2
                sgst_total += total_tax / 2
            else:
                igst_total += total_tax

            taxable_total += taxable_amount
            items_total += taxable_amount + total_tax

        try:
            other_discount = float(self.other_discount.value or 0)
        except ValueError:
            other_discount = 0
        try:
            transport = float(self.transport_charge.value or 0)
        except ValueError:
            transport = 0
        try:
            packing = float(self.packing_charge.value or 0)
        except ValueError:
            packing = 0

        raw_total = items_total - other_discount + transport + packing
        rounded_total = round(raw_total)
        round_off = rounded_total - raw_total

        try:
            paid = float(self.paid_amt.value or 0)
        except ValueError:
            paid = 0
        due = max(rounded_total - paid, 0)

        self._rebuild_item_table()
        self.sub_total_text.value = f"₹{items_total:,.2f}"
        self.taxable_text.value = f"₹{taxable_total:,.2f}"
        self.cgst_text.value = f"₹{cgst_total:,.2f}"
        self.sgst_text.value = f"₹{sgst_total:,.2f}"
        self.igst_text.value = f"₹{igst_total:,.2f}"
        self.round_off_text.value = f"₹{round_off:,.2f}"
        self.grand_total_text.value = f"₹{rounded_total:,.2f}"
        self.due_text.value = f"₹{due:,.2f}"

        self._last_calc = {
            "items_total": items_total, "taxable_total": taxable_total,
            "cgst_total": cgst_total, "sgst_total": sgst_total, "igst_total": igst_total,
            "other_discount": other_discount, "transport": transport, "packing": packing,
            "rounded_total": rounded_total, "round_off": round_off, "paid": paid, "due": due,
            "tax_mode": tax_mode,
        }

        if self.page:
            self.update()

    # ======================================================================
    # SAVE
    # ======================================================================
    def handle_save_invoice(self, e):
        if not self.customer_dropdown.value:
            self._show_status("⚠️ आधी Customer निवडा.", "#ff4444")
            return

        if not self.selected_customer:
            from database import get_customer_by_id
            self.selected_customer = get_customer_by_id(int(self.customer_dropdown.value))
        if not self.selected_customer:
            self._show_status("⚠️ Customer माहिती सापडली नाही — Customer dropdown मधून परत निवडा.", "#ff4444")
            return

        if not self.cart:
            self._show_status("⚠️ किमान एक Item/Labour Item Grid मध्ये जोडा.", "#ff4444")
            return

        # 👇 GST Bill टॉगलवरून ठरतं — GSTIN द्यायचा (B2B) की रिकामा ठेवायचा (B2C)
        if self.gst_bill_toggle.value:
            gstin = (self.manual_gstin.value or "").strip().upper()
            if not gstin:
                self._show_status("⚠️ GST Bill साठी GSTIN भरा — किंवा टॉगल बंद करून B2C बिल बनवा.", "#ff4444")
                return
        else:
            gstin = ""  # रिकामा -> आपोआप B2C मध्ये मोजला जाईल

        calc = self._last_calc
        customer = self.selected_customer
        tx_date = (self.invoice_date.value or "").strip()
        work_desc = (self.work_desc.value or "").strip() or "Service / Work"
        client_id = int(self.client_dropdown.value) if self.client_dropdown.value else None

        try:
            invoice_no = get_next_invoice_number()

            new_id = add_udhaari(
                name=customer["name"], mobile=customer["mobile"] or "",
                vehicle=(self.vehicle.value or "").strip(),
                vehicle_no=(self.vehicle_no.value or "").strip(),
                address=customer["address"] or "", tx_date=tx_date, due_date="",
                total_amt=calc["rounded_total"], paid_amt=calc["paid"], due_amt=calc["due"],
                notes=work_desc, type="Given", client_id=client_id,
                invoice_no=invoice_no,
                customer_gstin=gstin,
                customer_state_code=customer["state_code"] or "",
            )

            for item in self.cart:
                if item["kind"] == "part":
                    add_part_usage(
                        reference_table="udhaari", reference_id=new_id,
                        part_id=item["part_id"], product_name=item["name"],
                        part_number=item["part_number"], qty=item["qty"],
                        buying_rate=item["buying_rate"], sell_rate=item["rate"],
                        discount_percent=item["discount_percent"], tx_date=tx_date,
                        notes="GST Sale", hsn_sac=item["hsn_sac"], gst_rate=item["gst_rate"],
                    )

            parts_names = ", ".join(i["name"] for i in self.cart)
            labour_total = sum(i["qty"] * i["rate"] for i in self.cart if i["kind"] == "labour")
            parts_total = sum(i["qty"] * i["rate"] for i in self.cart if i["kind"] == "part")
            add_work(
                customer_name=customer["name"], vehicle=(self.vehicle.value or "").strip(),
                work_desc=work_desc, charge_amt=calc["rounded_total"], work_date=tx_date,
                status="Done", mobile=customer["mobile"] or "",
                vehicle_no=(self.vehicle_no.value or "").strip(),
                labour_charge=labour_total, parts_charge=parts_total, parts_used=parts_names,
            )

            if calc["paid"] > 0 and self.account_dropdown.value:
                add_transaction(
                    int(self.account_dropdown.value), "credit", calc["paid"],
                    category=f"GST Sale: {customer['name']}", tx_date=tx_date, notes=invoice_no,
                    reference_table="udhaari", reference_id=new_id,
                )

            row = get_by_id(new_id)
            downloads_dir = _get_output_dir()
            safe_name = "".join(ch if ch.isalnum() else "_" for ch in customer["name"])
            pdf_path = os.path.join(downloads_dir, f"{invoice_no}_{safe_name}.pdf")

            gst_line_items = [
                {
                    "description": item["name"], "hsn_sac": item["hsn_sac"],
                    "part_no": item.get("part_number", "") or "-",
                    "mrp": item.get("mrp", 0),
                    "qty": item["qty"], "rate": item["rate"],
                    "discount_percent": item["discount_percent"], "gst_rate": item["gst_rate"],
                }
                for item in self.cart
            ]
            if calc["transport"] > 0:
                gst_line_items.append({"description": "Transport Charge", "hsn_sac": "996812",
                                        "part_no": "-", "qty": 1, "rate": calc["transport"],
                                        "discount_percent": 0, "gst_rate": 18})
            if calc["packing"] > 0:
                gst_line_items.append({"description": "Packing Charge", "hsn_sac": "996813",
                                        "part_no": "-", "qty": 1, "rate": calc["packing"],
                                        "discount_percent": 0, "gst_rate": 18})

            generate_full_gst_invoice(
                buyer={
                    "name": customer["name"], "mobile": customer["mobile"] or "",
                    "address": customer["address"] or "", "gstin": gstin,
                    "state": customer["state"] or "Maharashtra",
                },
                line_items=gst_line_items, filepath=pdf_path,
                invoice_no=invoice_no, invoice_date=tx_date,
                mode_of_payment=self.payment_mode.value or "Cash",
                is_intra_state=(calc["tax_mode"] == "intra"),
                notes=work_desc,
                page_size=self.paper_size.value or "A5",
            )

        except Exception as ex:
            import traceback
            traceback.print_exc()
            self._show_status(f"❌ एरर: {ex}", "#ff4444")
            return

        bill_type = "B2B" if gstin else "B2C"
        self._show_status(f"✅ Invoice सेव्ह झालं ({bill_type})! {invoice_no} — {pdf_path}", "#00ffaa")
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
            try:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(msg, color="white"),
                    bgcolor=("#1f8f5f" if color == "#00ffaa" else "#b3261e"), open=True,
                )
                self.page.update()
            except Exception:
                pass

    def _clear_form(self):
        self.customer_dropdown.value = None
        self.selected_customer = None
        self.customer_search.value = ""
        self.client_dropdown.value = ""
        self.gst_bill_toggle.value = False
        self.manual_gstin.value = ""
        self.manual_gstin.visible = False
        for f in (self.vehicle, self.vehicle_no, self.work_desc):
            f.value = ""
        self.invoice_date.value = datetime.now().strftime("%d.%m.%Y")
        self.other_discount.value = "0"
        self.transport_charge.value = "0"
        self.packing_charge.value = "0"
        self.payment_mode.value = "Cash"
        self.account_dropdown.value = ""
        self.paid_amt.value = "0"
        self.paper_size.value = "A5"
        self.cart = []
        self._load_customer_options()
        self._load_client_options()
        self._load_item_options()
        self._refresh_invoice_no()
        self._recalc()


def get_labour_by_id_safe(labour_id):
    from database import get_labour_by_id
    return get_labour_by_id(labour_id)