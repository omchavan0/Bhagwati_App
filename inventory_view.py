import flet as ft
from database import (
    add_part, update_part, archive_part, get_parts, get_part_by_id, search_parts,
    get_part_stock, record_stock_in, get_low_stock_parts, get_all_parts_with_stock,
)


class InventoryView(ft.Container):
    """Parts Catalog + Stock (Ledger-based, कधीही corrupt न होणारा).
    - + Add Part: नवीन Part (Buying/Sell Rate, Low-stock सीमा सकट)
    - कार्डवर क्लिक -> Detail: सध्याचा live stock + "+ Stock In" (नवीन माल आला)
      + Edit/Archive
    - वरती Low-Stock parts चा banner (असतील तर)"""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.editing_part_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        # ---------------- Header + Search ----------------
        self.low_stock_banner = ft.Container(visible=False)
        self.search_field = ft.TextField(
            hint_text="Product Name / Part Number शोधा...",
            bgcolor="#161622", height=45,
            border_color="#1a1a26", focused_border_color="#00ffaa",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.handle_search,
        )
        self.part_list = ft.ListView(expand=True, spacing=10)

        add_btn = ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD, size=18), ft.Text("Add Part", weight="bold")], spacing=6),
            bgcolor="#00ffaa", color="black", height=45,
            on_click=lambda e: self.open_add_edit_dialog(None),
        )

        # ---------------- Add/Edit Part Dialog ----------------
        self.f_name = ft.TextField(label="🔩 Product Name *", height=52, **S)
        self.f_number = ft.TextField(label="🔢 Part Number", height=52, **S)
        self.f_buying = ft.TextField(label="💰 Buying Rate", height=52, prefix=ft.Text("₹ "),
                                      keyboard_type=ft.KeyboardType.NUMBER, value="0", **S)
        self.f_selling = ft.TextField(label="💵 Sell Rate", height=52, prefix=ft.Text("₹ "),
                                       keyboard_type=ft.KeyboardType.NUMBER, value="0", **S)
        self.f_opening_stock = ft.TextField(label="📦 सुरुवातीचा Stock (Qty)", height=52,
                                             keyboard_type=ft.KeyboardType.NUMBER, value="0", **S)
        self.f_low_alert = ft.TextField(label="⚠️ Low-Stock Alert Qty", height=52,
                                         keyboard_type=ft.KeyboardType.NUMBER, value="0", **S)
        self.f_hsn = ft.TextField(label="🧾 HSN/SAC Code", height=52, **S)
        self.f_gst_rate = ft.Dropdown(
            label="📐 GST %", height=52, value="18",
            options=[ft.dropdown.Option(v) for v in ("0", "5", "12", "18", "28")], **S
        )
        # 👇 नवीन फील्ड्स
        self.f_mrp = ft.TextField(label="🏷️ MRP", height=52, prefix=ft.Text("₹ "),
                                   keyboard_type=ft.KeyboardType.NUMBER, value="0", **S)
        self.f_discount = ft.TextField(label="💸 Discount %", height=52,
                                        keyboard_type=ft.KeyboardType.NUMBER, value="0", **S)
        self.f_barcode = ft.TextField(label="🔖 Barcode", height=52, **S)
        self.f_brand = ft.TextField(label="🏭 Brand", height=52, **S)
        self.f_category = ft.TextField(label="📂 Category", height=52, **S)
        self.f_unit = ft.Dropdown(
            label="📏 Unit", height=52, value="Nos",
            options=[ft.dropdown.Option(u) for u in ("Nos", "Kg", "Ltr", "Meter", "Box", "Set", "Pair")], **S
        )
        self.f_location = ft.TextField(label="📍 Rack/Location", height=52, **S)

        self.f_notes = ft.TextField(label="📝 Notes", height=52, **S)
        self.dialog_msg = ft.Text("", size=12, color="#ff4444", visible=False)

        self.save_part_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                                 on_click=self.handle_save_part)
        self.archive_part_btn = ft.TextButton("Archive", visible=False,
                                                style=ft.ButtonStyle(color="#ff8800"),
                                                on_click=self.handle_archive_part)

        self.add_edit_dialog = ft.AlertDialog(
            title=ft.Text("➕ नवीन Part"),
            content=ft.Container(
                content=ft.Column(
                    [self.f_name, self.f_number, ft.Row([self.f_buying, self.f_selling], spacing=10),
                     self.f_opening_stock, self.f_low_alert,
                     ft.Row([self.f_hsn, self.f_gst_rate], spacing=10),
                     ft.Row([self.f_mrp, self.f_discount], spacing=10),
                     ft.Row([self.f_barcode, self.f_brand], spacing=10),
                     ft.Row([self.f_category, self.f_unit], spacing=10),
                     self.f_location,
                     self.f_notes, self.dialog_msg],
                    tight=True, spacing=10,
                ),
                width=400,
            ),
            actions=[
                self.archive_part_btn,
                ft.TextButton("Cancel", on_click=self.close_add_edit_dialog),
                self.save_part_btn,
            ],
        )

        # ---------------- Archive confirm ----------------
        self.confirm_archive_dialog = ft.AlertDialog(
            title=ft.Text("Part आर्काइव्ह करायचं?"),
            content=ft.Text("हा Part dropdown मधून गायब होईल, पण जुन्या बिलांमधली नोंद (profit history) सुरक्षित राहील."),
            actions=[
                ft.TextButton("नाही", on_click=self._close_confirm_archive),
                ft.TextButton("हो, आर्काइव्ह करा", style=ft.ButtonStyle(color="#ff8800"),
                              on_click=self._confirm_archive_now),
            ],
        )

        # ---------------- Stock-In Dialog ----------------
        self.stock_in_part_id = None
        self.stock_in_qty = ft.TextField(label="📦 किती Qty जमा करायची *", height=52,
                                          keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.stock_in_date = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=52, **S)
        self.stock_in_notes = ft.TextField(label="📝 Notes (उदा. Supplier नाव)", height=52, **S)
        self.stock_in_msg = ft.Text("", size=12, color="#ff4444", visible=False)
        self.stock_in_dialog = ft.AlertDialog(
            title=ft.Text("📦 Stock In (नवीन माल जमा)"),
            content=ft.Container(
                content=ft.Column([self.stock_in_qty, self.stock_in_date, self.stock_in_notes, self.stock_in_msg],
                                   tight=True, spacing=10),
                width=380,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self.close_stock_in_dialog),
                ft.ElevatedButton("जमा करा", bgcolor="#00ffaa", color="black",
                                  on_click=self.handle_save_stock_in),
            ],
        )

        # ---------------- Part Detail Dialog ----------------
        self.detail_body = ft.Column(spacing=10, scroll="auto")
        self.detail_dialog = ft.AlertDialog(
            title=ft.Text("Part"),
            content=ft.Container(content=self.detail_body, width=440, height=340),
            actions=[
                ft.TextButton("✏️ Edit", on_click=self._edit_from_detail),
                ft.TextButton("Close", on_click=self.close_detail_dialog),
            ],
        )

        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("📦 Inventory / Parts", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True),
                        add_btn,
                    ]
                ),
                self.low_stock_banner,
                ft.Container(height=5),
                self.search_field,
                ft.Container(height=10),
                self.part_list,
            ],
            spacing=10,
            expand=True,
        )

    # ==================================================================
    def did_mount(self):
        for d in (self.add_edit_dialog, self.confirm_archive_dialog, self.stock_in_dialog, self.detail_dialog):
            if d not in self.page.overlay:
                self.page.overlay.append(d)
        self.page.update()
        self.refresh()

    def refresh(self, query=None):
        if self.page is None:
            return
        self.part_list.controls.clear()
        records = search_parts(query) if query else get_parts()

        if not records:
            self.part_list.controls.append(
                ft.Text("अजून कोणताही Part जोडलेला नाही. वरती '+ Add Part' दाबा.",
                        color="grey", italic=True))
        else:
            for row in records:
                stock = get_part_stock(row["id"])
                self.part_list.controls.append(self._part_card(row, stock))

        low_stock = get_low_stock_parts()
        if low_stock:
            names = ", ".join(item["part"]["product_name"] for item in low_stock[:5])
            more = f" +{len(low_stock)-5} अजून" if len(low_stock) > 5 else ""
            self.low_stock_banner.content = ft.Container(
                content=ft.Row([
                    ft.Text("⚠️", size=16),
                    ft.Text(f"Low Stock: {names}{more}", size=12, color="#ff8800", weight="bold"),
                ], spacing=8),
                bgcolor="#2a1a0a", padding=12, border_radius=10,
                border=ft.Border.all(1, "#ff8800"),
            )
            self.low_stock_banner.visible = True
        else:
            self.low_stock_banner.visible = False

        self.update()

    def handle_search(self, e):
        self.refresh(query=self.search_field.value)

    # ==================================================================
    def _part_card(self, row, stock):
        alert_qty = row["low_stock_alert_qty"] or 0
        is_low = alert_qty > 0 and stock <= alert_qty
        stock_color = "#ff4444" if is_low else "#00ffaa"

        sub_parts = [row["part_number"], f"Buy ₹{row['buying_rate']:.0f}", f"Sell ₹{row['sell_rate']:.0f}"]
        sub = "  •  ".join([p for p in sub_parts if p])

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text("🔩", size=20),
                        bgcolor="#12251e", width=44, height=44, border_radius=10,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(row["product_name"], weight="bold", color="white", size=15),
                            ft.Text(sub or "—", size=11, color="#94a3b8"),
                        ], spacing=2, expand=True,
                    ),
                    ft.Column(
                        [
                            ft.Text(f"{stock:.0f}", weight="bold", size=16, color=stock_color),
                            ft.Text("in stock", size=10, color="#64748b"),
                        ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=0,
                    ),
                    ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color="#64748b"),
                ],
                spacing=12,
            ),
            bgcolor="#161622", padding=14, border_radius=12, ink=True,
            border=ft.Border.all(1, "#ff4444") if is_low else None,
            on_click=lambda e, pid=row["id"]: self.open_detail(pid),
        )

    # ==================================================================
    # Add / Edit Part
    # ==================================================================
    def open_add_edit_dialog(self, part_row):
        self.dialog_msg.visible = False
        if part_row is None:
            self.editing_part_id = None
            self.add_edit_dialog.title = ft.Text("➕ नवीन Part")
            self.f_name.value = ""
            self.f_number.value = ""
            self.f_buying.value = "0"
            self.f_selling.value = "0"
            self.f_opening_stock.value = "0"
            self.f_opening_stock.disabled = False
            self.f_low_alert.value = "0"
            self.f_hsn.value = ""
            self.f_gst_rate.value = "18"
            self.f_mrp.value = "0"                # 👈 नवीन
            self.f_discount.value = "0"            # 👈 नवीन
            self.f_barcode.value = ""              # 👈 नवीन
            self.f_brand.value = ""                # 👈 नवीन
            self.f_category.value = ""             # 👈 नवीन
            self.f_unit.value = "Nos"              # 👈 नवीन
            self.f_location.value = ""             # 👈 नवीन
            self.f_notes.value = ""
            self.f_notes.value = ""
            self.archive_part_btn.visible = False
            self.save_part_btn.text = "Save"
        else:
            self.editing_part_id = part_row["id"]
            self.add_edit_dialog.title = ft.Text(f"✏️ Edit: {part_row['product_name']}")
            self.f_name.value = part_row["product_name"] or ""
            self.f_number.value = part_row["part_number"] or ""
            self.f_buying.value = str(part_row["buying_rate"] or 0)
            self.f_selling.value = str(part_row["sell_rate"] or 0)
            self.f_opening_stock.value = "0"
            self.f_opening_stock.disabled = True  # जुन्या Part साठी स्टॉक फक्त "Stock In" नेच वाढवायचा
            self.f_low_alert.value = str(part_row["low_stock_alert_qty"] or 0)
            self.f_hsn.value = part_row["hsn_sac"] if "hsn_sac" in part_row.keys() and part_row["hsn_sac"] else ""
            self.f_gst_rate.value = str(part_row["gst_rate"]) if "gst_rate" in part_row.keys() and part_row["gst_rate"] is not None else "18"
            self.f_mrp.value = str(part_row["mrp"]) if "mrp" in part_row.keys() and part_row["mrp"] is not None else "0"
            self.f_discount.value = str(part_row["discount_percent"]) if "discount_percent" in part_row.keys() and part_row["discount_percent"] is not None else "0"
            self.f_barcode.value = part_row["barcode"] if "barcode" in part_row.keys() and part_row["barcode"] else ""
            self.f_brand.value = part_row["brand"] if "brand" in part_row.keys() and part_row["brand"] else ""
            self.f_category.value = part_row["category"] if "category" in part_row.keys() and part_row["category"] else ""
            self.f_unit.value = part_row["unit"] if "unit" in part_row.keys() and part_row["unit"] else "Nos"
            self.f_location.value = part_row["location"] if "location" in part_row.keys() and part_row["location"] else ""
            self.f_notes.value = part_row["notes"] or ""
            self.archive_part_btn.visible = True
            self.save_part_btn.text = "Update"

        self.add_edit_dialog.open = True
        self.page.update()

    def close_add_edit_dialog(self, e):
        self.add_edit_dialog.open = False
        self.page.update()

    def handle_save_part(self, e):
        name = (self.f_name.value or "").strip()
        if not name:
            self._show_dialog_msg("⚠️ Product Name भरा.")
            return

        try:
            buying = float(self.f_buying.value or 0)
            selling = float(self.f_selling.value or 0)
            low_alert = float(self.f_low_alert.value or 0)
            opening_stock = float(self.f_opening_stock.value or 0) if not self.f_opening_stock.disabled else 0
            mrp = float(self.f_mrp.value or 0)
            discount = float(self.f_discount.value or 0)
        except ValueError:
            self._show_dialog_msg("⚠️ Rate/Qty फक्त नंबरमध्ये.")
            return

        if self.editing_part_id:
            update_part(self.editing_part_id, name, (self.f_number.value or "").strip(),
                        buying, selling, low_alert, (self.f_notes.value or "").strip(),
                        hsn_sac=(self.f_hsn.value or "").strip(),
                        gst_rate=float(self.f_gst_rate.value or 18),
                        mrp=mrp, discount_percent=discount,                              # 👈 नवीन
                        barcode=(self.f_barcode.value or "").strip(),                    # 👈
                        brand=(self.f_brand.value or "").strip(),                        # 👈
                        category=(self.f_category.value or "").strip(),                  # 👈
                        unit=self.f_unit.value or "Nos",                                 # 👈
                        location=(self.f_location.value or "").strip()) 
            # 👇 नवीन फील्ड्स
        else:
            new_id = add_part(name, (self.f_number.value or "").strip(), buying, selling,
                               low_alert, (self.f_notes.value or "").strip(),
                               hsn_sac=(self.f_hsn.value or "").strip(),
                               gst_rate=float(self.f_gst_rate.value or 18),
                               mrp=mrp, discount_percent=discount,                        # 👈 नवीन
                               barcode=(self.f_barcode.value or "").strip(),              # 👈
                               brand=(self.f_brand.value or "").strip(),                  # 👈
                               category=(self.f_category.value or "").strip(),            # 👈
                               unit=self.f_unit.value or "Nos",                           # 👈
                               location=(self.f_location.value or "").strip())
            if opening_stock > 0:
                record_stock_in(new_id, opening_stock, notes="सुरुवातीचा स्टॉक")

        self.add_edit_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    def _show_dialog_msg(self, text):
        self.dialog_msg.value = text
        self.dialog_msg.visible = True
        self.dialog_msg.update()

    # ==================================================================
    # Archive
    # ==================================================================
    def handle_archive_part(self, e):
        self.add_edit_dialog.open = False
        self.confirm_archive_dialog.open = True
        self.page.update()

    def _close_confirm_archive(self, e):
        self.confirm_archive_dialog.open = False
        self.page.update()

    def _confirm_archive_now(self, e):
        if self.editing_part_id:
            archive_part(self.editing_part_id)
        self.confirm_archive_dialog.open = False
        self.detail_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    # ==================================================================
    # Part Detail — live stock + actions
    # ==================================================================
    def open_detail(self, part_id):
        part = get_part_by_id(part_id)
        if not part:
            return

        self.editing_part_id = part_id
        stock = get_part_stock(part_id)
        self.detail_dialog.title = ft.Text(part["product_name"])

        is_low = (part["low_stock_alert_qty"] or 0) > 0 and stock <= (part["low_stock_alert_qty"] or 0)

        stock_in_btn = ft.ElevatedButton(
            "📦 Stock In (माल जमा करा)", bgcolor="#00ffaa", color="black", expand=True,
            on_click=lambda e: self._open_stock_in_dialog(part_id),
        )

        self.detail_body.controls = [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("सध्याचा Stock", size=11, color="#94a3b8"),
                        ft.Text(f"{stock:.0f}", size=26, weight="bold",
                                color="#ff4444" if is_low else "#00ffaa"),
                        ft.Text("⚠️ Low Stock!", size=11, color="#ff4444", weight="bold") if is_low else ft.Container(height=0),
                    ], spacing=2,
                ),
                bgcolor="#12251e", padding=16, border_radius=12,
            ),
            ft.Row(
                [
                    ft.Text(f"Buying Rate: ₹{part['buying_rate']:.0f}", size=12, color="#94a3b8"),
                    ft.Text(f"Sell Rate: ₹{part['sell_rate']:.0f}", size=12, color="#94a3b8"),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Text(f"Part Number: {part['part_number'] or '—'}", size=12, color="#94a3b8"),
            ft.Container(height=6),
            stock_in_btn,
        ]

        self.detail_dialog.open = True
        self.page.update()

    def close_detail_dialog(self, e):
        self.detail_dialog.open = False
        self.page.update()

    def _edit_from_detail(self, e):
        part = get_part_by_id(self.editing_part_id)
        self.detail_dialog.open = False
        self.page.update()
        if part:
            self.open_add_edit_dialog(part)

    # ==================================================================
    # Stock-In Dialog
    # ==================================================================
    def _open_stock_in_dialog(self, part_id):
        self.stock_in_part_id = part_id
        self.stock_in_qty.value = ""
        self.stock_in_date.value = ""
        self.stock_in_notes.value = ""
        self.stock_in_msg.visible = False
        self.stock_in_dialog.open = True
        self.page.update()

    def close_stock_in_dialog(self, e):
        self.stock_in_dialog.open = False
        self.page.update()

    def handle_save_stock_in(self, e):
        try:
            qty = float(self.stock_in_qty.value or 0)
        except ValueError:
            qty = 0

        try:
            record_stock_in(
                self.stock_in_part_id, qty,
                tx_date=(self.stock_in_date.value or "").strip(),
                notes=(self.stock_in_notes.value or "").strip(),
            )
        except ValueError as ex:
            self.stock_in_msg.value = f"⚠️ {ex}"
            self.stock_in_msg.visible = True
            self.stock_in_msg.update()
            return

        self.stock_in_dialog.open = False
        self.page.update()
        self.open_detail(self.stock_in_part_id)
        self.refresh(query=self.search_field.value)
