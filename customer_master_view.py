import flet as ft
from database import (
    add_customer, update_customer, archive_customer,
    get_customers, get_customer_by_id, search_customers,
)
from gst_utils import is_valid_gstin_format, get_state_code_from_name


class CustomerMasterView(ft.Container):
    """GST Customer Master — Billing साठी लागणारा प्रत्येक ग्राहकाचा पूर्ण
    प्रोफाइल (GSTIN/State सकट). Registered/Unregistered बॅज GSTIN वरून
    आपोआप ठरतो — वेगळं टॉगल नाही (चुकीच्या एन्ट्रीची शक्यता कमी व्हावी म्हणून)."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.editing_customer_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        self.search_field = ft.TextField(
            hint_text="नाव / मोबाईल / GSTIN / गाडी नंबर शोधा...",
            bgcolor="#161622", height=45,
            border_color="#1a1a26", focused_border_color="#00ffaa",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.handle_search,
        )
        self.customer_list = ft.ListView(expand=True, spacing=10)

        add_btn = ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD, size=18), ft.Text("Add Customer", weight="bold")], spacing=6),
            bgcolor="#00ffaa", color="black", height=45,
            on_click=lambda e: self.open_add_edit_dialog(None),
        )

        # ---------------- Add/Edit Dialog फील्ड्स ----------------
        self.f_name = ft.TextField(label="👤 Customer Name *", height=52, **S)
        self.f_mobile = ft.TextField(label="📱 Mobile", height=52, **S)
        self.f_email = ft.TextField(label="📧 Email", height=52, **S)
        self.f_gstin = ft.TextField(label="🧾 GSTIN (रिकामं ठेवलं तर Unregistered)", height=52,
                                     on_change=self._on_gstin_change, **S)
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

        self.f_vehicle = ft.TextField(label="🚗 Vehicle", height=52, **S)
        self.f_vehicle_no = ft.TextField(label="🔢 Vehicle Number", height=52, **S)

        self.f_business_type = ft.Dropdown(
            label="Business Type", height=52,
            options=[ft.dropdown.Option(t) for t in
                     ["Individual", "Retail", "Wholesale", "Corporate", "Government", "Other"]],
            value="Individual", **S,
        )
        self.f_customer_type = ft.Dropdown(
            label="Customer Type", height=52, value="Retail",
            options=[ft.dropdown.Option(t) for t in ["Retail", "Wholesale", "Fleet", "Corporate"]],
            **S,
        )
        self.f_notes = ft.TextField(label="📝 Notes", height=52, **S)
        self.dialog_msg = ft.Text("", size=12, visible=False)

        self.save_customer_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                                     on_click=self.handle_save_customer)
        self.archive_customer_btn = ft.TextButton("Archive", visible=False,
                                                    style=ft.ButtonStyle(color="#ff8800"),
                                                    on_click=self.handle_archive_customer)

        self.add_edit_dialog = ft.AlertDialog(
            title=ft.Text("नवीन Customer"),
            content=ft.Container(
                content=ft.Column(
                    [
                        self.f_name,
                        ft.Row([self.f_mobile, self.f_email], spacing=10),
                        self.f_gstin, self.gstin_status_text,
                        self.f_address,
                        ft.Row([self.f_city, self.f_state], spacing=10),
                        self.f_pin_code,
                        ft.Row([self.f_vehicle, self.f_vehicle_no], spacing=10),
                        ft.Row([self.f_business_type, self.f_customer_type], spacing=10),
                        self.f_notes, self.dialog_msg,
                    ],
                    tight=True, spacing=10, scroll="auto",
                ),
                width=420, height=520,
            ),
            actions=[
                self.archive_customer_btn,
                ft.TextButton("Cancel", on_click=self.close_add_edit_dialog),
                self.save_customer_btn,
            ],
        )

        self.confirm_archive_dialog = ft.AlertDialog(
            title=ft.Text("Customer आर्काइव्ह करायचा?"),
            content=ft.Text("हा Customer dropdown मधून गायब होईल, पण जुना बिलिंग हिशोब सुरक्षित राहील."),
            actions=[
                ft.TextButton("नाही", on_click=self._close_confirm_archive),
                ft.TextButton("हो, आर्काइव्ह करा", style=ft.ButtonStyle(color="#ff8800"),
                              on_click=self._confirm_archive_now),
            ],
        )

        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("👥 GST Customer Master", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True),
                        add_btn,
                    ]
                ),
                ft.Container(height=5),
                self.search_field,
                ft.Container(height=10),
                self.customer_list,
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
        self.customer_list.controls.clear()
        records = search_customers(query) if query else get_customers()

        if not records:
            self.customer_list.controls.append(
                ft.Text("अजून कोणताही Customer जोडलेला नाही. वरती '+ Add Customer' दाबा.",
                        color="grey", italic=True))
        else:
            for row in records:
                self.customer_list.controls.append(self._customer_card(row))
        self.update()

    def handle_search(self, e):
        self.refresh(query=self.search_field.value)

    # ==================================================================
    def _customer_card(self, row):
        is_registered = (row["registration_status"] if "registration_status" in row.keys() else "Unregistered") == "Registered"
        badge_color = "#00ffaa" if is_registered else "#64748b"
        badge_text = "Registered" if is_registered else "Unregistered"

        sub_parts = [row["mobile"], row["gstin"] or None, row["city"]]
        sub = "  •  ".join([p for p in sub_parts if p])

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text("👤", size=20),
                        bgcolor="#12251e", width=44, height=44, border_radius=10,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(row["name"], weight="bold", color="white", size=15),
                            ft.Text(sub or "—", size=11, color="#94a3b8"),
                        ], spacing=2, expand=True,
                    ),
                    ft.Container(
                        content=ft.Text(badge_text, size=10, color="black" if is_registered else "white"),
                        bgcolor=badge_color, border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    ),
                ],
                spacing=12,
            ),
            bgcolor="#161622", padding=14, border_radius=12, ink=True,
            on_click=lambda e, row=row: self.open_add_edit_dialog(row),
        )

    # ==================================================================
    def _on_gstin_change(self, e):
        gstin = (self.f_gstin.value or "").strip()
        if not gstin:
            self.gstin_status_text.value = "ℹ️ GSTIN रिकामं -> ग्राहक Unregistered समजला जाईल."
            self.gstin_status_text.color = "#64748b"
        elif is_valid_gstin_format(gstin):
            self.gstin_status_text.value = "✅ बरोबर GSTIN फॉरमॅट -> Registered ग्राहक."
            self.gstin_status_text.color = "#00ffaa"
        else:
            self.gstin_status_text.value = "⚠️ GSTIN फॉरमॅट चुकीचा वाटतोय (15 अक्षरं हवीत)."
            self.gstin_status_text.color = "#ff8800"
        self.gstin_status_text.visible = True
        if self.page:
            self.gstin_status_text.update()

    # ==================================================================
    def open_add_edit_dialog(self, customer_row):
        self.dialog_msg.visible = False
        self.gstin_status_text.visible = False
        if customer_row is None:
            self.editing_customer_id = None
            self.add_edit_dialog.title = ft.Text("➕ नवीन Customer")
            for f in (self.f_name, self.f_mobile, self.f_email, self.f_gstin, self.f_address,
                      self.f_city, self.f_pin_code, self.f_vehicle, self.f_vehicle_no, self.f_notes):
                f.value = ""
            self.f_state.value = "Maharashtra"
            self.f_business_type.value = "Individual"
            self.f_customer_type.value = "Retail"
            self.archive_customer_btn.visible = False
            self.save_customer_btn.text = "Save"
        else:
            self.editing_customer_id = customer_row["id"]
            self.add_edit_dialog.title = ft.Text(f"✏️ Edit: {customer_row['name']}")
            self.f_name.value = customer_row["name"] or ""
            self.f_mobile.value = customer_row["mobile"] or ""
            self.f_email.value = customer_row["email"] or ""
            self.f_gstin.value = customer_row["gstin"] or ""
            self.f_address.value = customer_row["address"] or ""
            self.f_city.value = customer_row["city"] or ""
            self.f_state.value = customer_row["state"] or "Maharashtra"
            self.f_pin_code.value = customer_row["pin_code"] or ""
            self.f_vehicle.value = customer_row["vehicle"] or ""
            self.f_vehicle_no.value = customer_row["vehicle_no"] or ""
            self.f_business_type.value = customer_row["business_type"] or "Individual"
            self.f_customer_type.value = customer_row["customer_type"] or "Retail"
            self.f_notes.value = customer_row["notes"] or ""
            self.archive_customer_btn.visible = True
            self.save_customer_btn.text = "Update"

        self.add_edit_dialog.open = True
        self.page.update()

    def close_add_edit_dialog(self, e):
        self.add_edit_dialog.open = False
        self.page.update()

    def handle_save_customer(self, e):
        name = (self.f_name.value or "").strip()
        if not name:
            self._show_dialog_msg("⚠️ Customer Name भरा.")
            return

        gstin = (self.f_gstin.value or "").strip().upper()
        if gstin and not is_valid_gstin_format(gstin):
            self._show_dialog_msg("⚠️ GSTIN फॉरमॅट चुकीचा आहे (15 अक्षरं हवीत) — रिकामं ठेव किंवा दुरुस्त कर.")
            return

        kwargs = dict(
            name=name,
            mobile=(self.f_mobile.value or "").strip(),
            email=(self.f_email.value or "").strip(),
            gstin=gstin,
            address=(self.f_address.value or "").strip(),
            city=(self.f_city.value or "").strip(),
            state=self.f_state.value or "Maharashtra",
            state_code=get_state_code_from_name(self.f_state.value),
            pin_code=(self.f_pin_code.value or "").strip(),
            vehicle=(self.f_vehicle.value or "").strip(),
            vehicle_no=(self.f_vehicle_no.value or "").strip(),
            business_type=self.f_business_type.value or "Individual",
            customer_type=self.f_customer_type.value or "Retail",
            notes=(self.f_notes.value or "").strip(),
        )

        if self.editing_customer_id:
            update_customer(self.editing_customer_id, **kwargs)
        else:
            add_customer(**kwargs)

        self.add_edit_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    def _show_dialog_msg(self, text):
        self.dialog_msg.value = text
        self.dialog_msg.color = "#ff4444"
        self.dialog_msg.visible = True
        self.dialog_msg.update()

    # ==================================================================
    def handle_archive_customer(self, e):
        self.add_edit_dialog.open = False
        self.confirm_archive_dialog.open = True
        self.page.update()

    def _close_confirm_archive(self, e):
        self.confirm_archive_dialog.open = False
        self.page.update()

    def _confirm_archive_now(self, e):
        if self.editing_customer_id:
            archive_customer(self.editing_customer_id)
        self.confirm_archive_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)