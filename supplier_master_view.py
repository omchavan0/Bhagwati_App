import flet as ft
from database import (
    add_supplier, update_supplier, archive_supplier,
    get_suppliers, get_supplier_by_id, search_suppliers,
)
from gst_utils import is_valid_gstin_format, get_state_code_from_name


class SupplierMasterView(ft.Container):
    """Purchase साठी Supplier/Vendor Master — customer_master_view.py प्रमाणेच."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.editing_supplier_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        self.search_field = ft.TextField(
            hint_text="नाव / मोबाईल / GSTIN शोधा...",
            bgcolor="#161622", height=45,
            border_color="#1a1a26", focused_border_color="#00ffaa",
            prefix_icon=ft.Icons.SEARCH,
        )
        self.search_field.on_change = self.handle_search
        self.supplier_list = ft.ListView(expand=True, spacing=10)

        add_btn = ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD, size=18), ft.Text("Add Supplier", weight="bold")], spacing=6),
            bgcolor="#00ffaa", color="black", height=45,
            on_click=lambda e: self.open_add_edit_dialog(None),
        )

        # ---------------- Add/Edit Dialog फील्ड्स ----------------
        self.f_name = ft.TextField(label="🏭 Supplier Name *", height=52, **S)
        self.f_mobile = ft.TextField(label="📱 Mobile", height=52, **S)
        self.f_email = ft.TextField(label="📧 Email", height=52, **S)
        self.f_gstin = ft.TextField(label="🧾 GSTIN (रिकामं ठेवलं तर Unregistered)", height=52, **S)
        self.f_gstin.on_change = self._on_gstin_change
        self.gstin_status_text = ft.Text("", size=11)

        self.f_address = ft.TextField(label="📍 Address", height=52, **S)
        self.f_city = ft.TextField(label="🏙️ City", height=52, **S)
        self.f_state = ft.Dropdown(
            label="राज्य (State)", height=52, value="Maharashtra",
            options=[ft.dropdown.Option(s) for s in
                     ["Maharashtra", "Gujarat", "Karnataka", "Tamil Nadu", "Telangana",
                      "Andhra Pradesh", "Delhi", "Uttar Pradesh", "Madhya Pradesh",
                      "Rajasthan", "West Bengal", "Punjab", "Haryana", "Kerala",
                      "Bihar", "Goa", "Other State"]],
            **S,
        )
        self.f_pin_code = ft.TextField(label="PIN Code", height=52, **S)
        self.f_business_type = ft.Dropdown(
            label="Business Type", height=52,
            options=[ft.dropdown.Option(t) for t in
                     ["Manufacturer", "Wholesaler", "Distributor", "Retailer", "Other"]],
            value="Wholesaler", **S,
        )
        self.f_notes = ft.TextField(label="📝 Notes", height=52, **S)
        self.dialog_msg = ft.Text("", size=12, visible=False)

        self.save_supplier_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                                     on_click=self.handle_save_supplier)
        self.archive_supplier_btn = ft.TextButton("Archive", visible=False,
                                                    style=ft.ButtonStyle(color="#ff8800"),
                                                    on_click=self.handle_archive_supplier)

        self.add_edit_dialog = ft.AlertDialog(
            title=ft.Text("नवीन Supplier"),
            content=ft.Container(
                content=ft.Column(
                    [
                        self.f_name,
                        ft.Row([self.f_mobile, self.f_email], spacing=10),
                        self.f_gstin, self.gstin_status_text,
                        self.f_address,
                        ft.Row([self.f_city, self.f_state], spacing=10),
                        ft.Row([self.f_pin_code, self.f_business_type], spacing=10),
                        self.f_notes, self.dialog_msg,
                    ],
                    tight=True, spacing=10, scroll="auto",
                ),
                width=420, height=480,
            ),
            actions=[
                self.archive_supplier_btn,
                ft.TextButton("Cancel", on_click=self.close_add_edit_dialog),
                self.save_supplier_btn,
            ],
        )

        self.confirm_archive_dialog = ft.AlertDialog(
            title=ft.Text("Supplier आर्काइव्ह करायचा?"),
            content=ft.Text("हा dropdown मधून गायब होईल, पण जुना Purchase हिशोब सुरक्षित राहील."),
            actions=[
                ft.TextButton("नाही", on_click=self._close_confirm_archive),
                ft.TextButton("हो, आर्काइव्ह करा", style=ft.ButtonStyle(color="#ff8800"),
                              on_click=self._confirm_archive_now),
            ],
        )

        self.content = ft.Column(
            [
                ft.Row([ft.Text("🏭 Supplier Master", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True), add_btn]),
                ft.Container(height=5),
                self.search_field,
                ft.Container(height=10),
                self.supplier_list,
            ],
            spacing=10, expand=True,
        )

    # ==================================================================
    def did_mount(self):
        for d in (self.add_edit_dialog, self.confirm_archive_dialog):
            if d not in self.page.overlay:
                self.page.overlay.append(d)
        self.page.update()
        self.refresh()

    def refresh(self, query=None):
        if self.page is None:
            return
        self.supplier_list.controls.clear()
        records = search_suppliers(query) if query else get_suppliers()

        if not records:
            self.supplier_list.controls.append(
                ft.Text("अजून कोणताही Supplier जोडलेला नाही.", color="grey", italic=True))
        else:
            for row in records:
                self.supplier_list.controls.append(self._supplier_card(row))
        self.update()

    def handle_search(self, e):
        self.refresh(query=self.search_field.value)

    def _supplier_card(self, row):
        is_registered = (row["registration_status"] if "registration_status" in row.keys() else "Unregistered") == "Registered"
        badge_color = "#00ffaa" if is_registered else "#64748b"
        badge_text = "Registered" if is_registered else "Unregistered"
        sub_parts = [row["mobile"], row["gstin"] or None, row["city"]]
        sub = "  •  ".join([p for p in sub_parts if p])

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(content=ft.Text("🏭", size=20), bgcolor="#12251e",
                                 width=44, height=44, border_radius=10, alignment=ft.Alignment(0, 0)),
                    ft.Column([ft.Text(row["name"], weight="bold", color="white", size=15),
                               ft.Text(sub or "—", size=11, color="#94a3b8")], spacing=2, expand=True),
                    ft.Container(content=ft.Text(badge_text, size=10, color="black" if is_registered else "white"),
                                 bgcolor=badge_color, border_radius=6,
                                 padding=ft.Padding(left=8, right=8, top=4, bottom=4)),
                ],
                spacing=12,
            ),
            bgcolor="#161622", padding=14, border_radius=12, ink=True,
            on_click=lambda e, row=row: self.open_add_edit_dialog(row),
        )

    def _on_gstin_change(self, e):
        gstin = (self.f_gstin.value or "").strip()
        if not gstin:
            self.gstin_status_text.value = "ℹ️ GSTIN रिकामं -> Unregistered समजला जाईल."
            self.gstin_status_text.color = "#64748b"
        elif is_valid_gstin_format(gstin):
            self.gstin_status_text.value = "✅ बरोबर GSTIN फॉरमॅट."
            self.gstin_status_text.color = "#00ffaa"
        else:
            self.gstin_status_text.value = "⚠️ GSTIN फॉरमॅट चुकीचा वाटतोय."
            self.gstin_status_text.color = "#ff8800"
        self.gstin_status_text.visible = True
        if self.page:
            self.gstin_status_text.update()

    def open_add_edit_dialog(self, supplier_row):
        self.dialog_msg.visible = False
        self.gstin_status_text.visible = False
        if supplier_row is None:
            self.editing_supplier_id = None
            self.add_edit_dialog.title = ft.Text("➕ नवीन Supplier")
            for f in (self.f_name, self.f_mobile, self.f_email, self.f_gstin,
                      self.f_address, self.f_city, self.f_pin_code, self.f_notes):
                f.value = ""
            self.f_state.value = "Maharashtra"
            self.f_business_type.value = "Wholesaler"
            self.archive_supplier_btn.visible = False
            self.save_supplier_btn.text = "Save"
        else:
            self.editing_supplier_id = supplier_row["id"]
            self.add_edit_dialog.title = ft.Text(f"✏️ Edit: {supplier_row['name']}")
            self.f_name.value = supplier_row["name"] or ""
            self.f_mobile.value = supplier_row["mobile"] or ""
            self.f_email.value = supplier_row["email"] or ""
            self.f_gstin.value = supplier_row["gstin"] or ""
            self.f_address.value = supplier_row["address"] or ""
            self.f_city.value = supplier_row["city"] or ""
            self.f_state.value = supplier_row["state"] or "Maharashtra"
            self.f_pin_code.value = supplier_row["pin_code"] or ""
            self.f_business_type.value = supplier_row["business_type"] or "Wholesaler"
            self.f_notes.value = supplier_row["notes"] or ""
            self.archive_supplier_btn.visible = True
            self.save_supplier_btn.text = "Update"

        self.add_edit_dialog.open = True
        self.page.update()

    def close_add_edit_dialog(self, e):
        self.add_edit_dialog.open = False
        self.page.update()

    def handle_save_supplier(self, e):
        name = (self.f_name.value or "").strip()
        if not name:
            self._show_dialog_msg("⚠️ Supplier Name भरा.")
            return

        gstin = (self.f_gstin.value or "").strip().upper()
        if gstin and not is_valid_gstin_format(gstin):
            self._show_dialog_msg("⚠️ GSTIN फॉरमॅट चुकीचा आहे.")
            return

        kwargs = dict(
            name=name, mobile=(self.f_mobile.value or "").strip(),
            email=(self.f_email.value or "").strip(), gstin=gstin,
            address=(self.f_address.value or "").strip(), city=(self.f_city.value or "").strip(),
            state=self.f_state.value or "Maharashtra",
            state_code=get_state_code_from_name(self.f_state.value),
            pin_code=(self.f_pin_code.value or "").strip(),
            business_type=self.f_business_type.value or "Wholesaler",
            notes=(self.f_notes.value or "").strip(),
        )

        if self.editing_supplier_id:
            update_supplier(self.editing_supplier_id, **kwargs)
        else:
            add_supplier(**kwargs)

        self.add_edit_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    def _show_dialog_msg(self, text):
        self.dialog_msg.value = text
        self.dialog_msg.color = "#ff4444"
        self.dialog_msg.visible = True
        self.dialog_msg.update()

    def handle_archive_supplier(self, e):
        self.add_edit_dialog.open = False
        self.confirm_archive_dialog.open = True
        self.page.update()

    def _close_confirm_archive(self, e):
        self.confirm_archive_dialog.open = False
        self.page.update()

    def _confirm_archive_now(self, e):
        if self.editing_supplier_id:
            archive_supplier(self.editing_supplier_id)
        self.confirm_archive_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)