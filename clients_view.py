import flet as ft
from database import (
    add_client, update_client, delete_client,
    get_clients, get_client_by_id, search_clients, get_client_profile,
)


class ClientsView(ft.Container):
    """Garage Groups / Clients मॅनेज करणारा व्ह्यू.
    - + Add Client बटणाने नवीन Garage/Client बनवता येतो
    - यादीतल्या कार्डवर क्लिक केलं की त्या client चा पूर्ण प्रोफाइल (30 दिवसांचं
      काम, वाहनं, पैसे/जमा/बाकी) उघडतो
    - प्रोफाइलमधूनच Edit / Delete करता येतं
    - on_edit_record दिलं असेल तर प्रोफाइलमधल्या एका रेकॉर्डवर क्लिक करून
      थेट Udhaari फॉर्ममध्ये एडिट करता येतं"""

    def __init__(self, on_edit_record=None):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.on_edit_record = on_edit_record
        self.editing_client_id = None  # Add/Edit dialog कोणत्या client साठी आहे

        # ---------------- Search + List ----------------
        self.search_field = ft.TextField(
            hint_text="Garage नाव / Owner / मोबाईल शोधा...",
            bgcolor="#161622", height=45,
            border_color="#1a1a26", focused_border_color="#00ffaa",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.handle_search,
        )
        self.client_list = ft.ListView(expand=True, spacing=10)

        add_btn = ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD, size=18), ft.Text("Add Client", weight="bold")], spacing=6),
            bgcolor="#00ffaa", color="black", height=45,
            on_click=lambda e: self.open_add_edit_dialog(None),
        )

        # ---------------- Add/Edit Dialog फील्ड्स ----------------
        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}
        self.f_garage = ft.TextField(label="🏢 Garage Name *", height=52, **S)
        self.f_owner = ft.TextField(label="👤 Owner Name", height=52, **S)
        self.f_mobile = ft.TextField(label="📱 Mobile Number", height=52, **S)
        self.f_location = ft.TextField(label="📍 Location", height=52, **S)
        self.dialog_msg = ft.Text("", size=12, visible=False)

        self.save_client_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                                   on_click=self.handle_save_client)
        self.delete_client_btn = ft.TextButton("Delete", visible=False,
                                                 style=ft.ButtonStyle(color="#ff4444"),
                                                 on_click=self.handle_delete_client)

        self.add_edit_dialog = ft.AlertDialog(
            title=ft.Text("नवीन Client / Garage"),
            content=ft.Container(
                content=ft.Column(
                    [self.f_garage, self.f_owner, self.f_mobile, self.f_location, self.dialog_msg],
                    tight=True, spacing=10,
                ),
                width=380,
            ),
            actions=[
                self.delete_client_btn,
                ft.TextButton("Cancel", on_click=self.close_add_edit_dialog),
                self.save_client_btn,
            ],
        )

        # ---------------- Delete confirm ----------------
        self.confirm_delete_dialog = ft.AlertDialog(
            title=ft.Text("Client डिलीट करायचा?"),
            content=ft.Text("Client काढला जाईल, पण त्याच्याशी जोडलेल्या उधारी नोंदी सुरक्षित राहतील."),
            actions=[
                ft.TextButton("नाही", on_click=self._close_confirm_delete),
                ft.TextButton("हो, डिलीट करा", style=ft.ButtonStyle(color="#ff4444"),
                              on_click=self._confirm_delete_now),
            ],
        )

        # ---------------- Profile Dialog ----------------
        self.profile_body = ft.Column(spacing=10, scroll="auto")
        self.profile_dialog = ft.AlertDialog(
            title=ft.Text("Client Profile"),
            content=ft.Container(content=self.profile_body, width=460, height=560),
            actions=[
                ft.TextButton("✏️ Edit", on_click=self._edit_from_profile),
                ft.TextButton("Close", on_click=self.close_profile_dialog),
            ],
        )

        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("🏢 Garage Groups / Clients", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True),
                        add_btn,
                    ]
                ),
                ft.Container(height=5),
                self.search_field,
                ft.Container(height=10),
                self.client_list,
            ],
            spacing=10,
            expand=True,
        )

    # ==================================================================
    def did_mount(self):
        for d in (self.add_edit_dialog, self.confirm_delete_dialog, self.profile_dialog):
            if d not in self.page.overlay:
                self.page.overlay.append(d)
        self.page.update()
        self.refresh()

    def refresh(self, query=None):
        if self.page is None:
            return
        self.client_list.controls.clear()
        records = search_clients(query) if query else get_clients()

        if not records:
            self.client_list.controls.append(
                ft.Text("अजून कोणताही Client जोडलेला नाही. वरती '+ Add Client' दाबा.",
                        color="grey", italic=True))
        else:
            for row in records:
                self.client_list.controls.append(self._client_card(row))
        self.update()

    def handle_search(self, e):
        self.refresh(query=self.search_field.value)

    # ==================================================================
    def _client_card(self, row):
        sub_parts = [row["owner_name"], row["mobile"], row["location"]]
        sub = "  •  ".join([p for p in sub_parts if p])

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text("🏢", size=20),
                        bgcolor="#12251e", width=44, height=44, border_radius=10,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(row["garage_name"], weight="bold", color="white", size=15),
                            ft.Text(sub or "—", size=11, color="#94a3b8"),
                        ], spacing=2, expand=True,
                    ),
                    ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color="#64748b"),
                ],
                spacing=12,
            ),
            bgcolor="#161622", padding=14, border_radius=12, ink=True,
            on_click=lambda e, cid=row["id"]: self.open_profile(cid),
        )

    # ==================================================================
    # Add / Edit Client Dialog
    # ==================================================================
    def open_add_edit_dialog(self, client_row):
        self.dialog_msg.visible = False
        if client_row is None:
            self.editing_client_id = None
            self.add_edit_dialog.title = ft.Text("➕ नवीन Client / Garage")
            self.f_garage.value = ""
            self.f_owner.value = ""
            self.f_mobile.value = ""
            self.f_location.value = ""
            self.delete_client_btn.visible = False
            self.save_client_btn.text = "Save"
        else:
            self.editing_client_id = client_row["id"]
            self.add_edit_dialog.title = ft.Text(f"✏️ Edit: {client_row['garage_name']}")
            self.f_garage.value = client_row["garage_name"] or ""
            self.f_owner.value = client_row["owner_name"] or ""
            self.f_mobile.value = client_row["mobile"] or ""
            self.f_location.value = client_row["location"] or ""
            self.delete_client_btn.visible = True
            self.save_client_btn.text = "Update"

        self.add_edit_dialog.open = True
        self.page.update()

    def close_add_edit_dialog(self, e):
        self.add_edit_dialog.open = False
        self.page.update()

    def handle_save_client(self, e):
        garage = (self.f_garage.value or "").strip()
        if not garage:
            self.dialog_msg.value = "⚠️ Garage Name भरा."
            self.dialog_msg.color = "#ff4444"
            self.dialog_msg.visible = True
            self.dialog_msg.update()
            return

        kwargs = dict(
            garage_name=garage,
            owner_name=(self.f_owner.value or "").strip(),
            mobile=(self.f_mobile.value or "").strip(),
            location=(self.f_location.value or "").strip(),
        )

        if self.editing_client_id:
            update_client(self.editing_client_id, **kwargs)
        else:
            add_client(**kwargs)

        self.add_edit_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    # ==================================================================
    # Delete Client
    # ==================================================================
    def handle_delete_client(self, e):
        # Add/Edit dialog बंद करून confirm dialog उघड
        self.add_edit_dialog.open = False
        self.confirm_delete_dialog.open = True
        self.page.update()

    def _close_confirm_delete(self, e):
        self.confirm_delete_dialog.open = False
        self.page.update()

    def _confirm_delete_now(self, e):
        if self.editing_client_id:
            delete_client(self.editing_client_id)
        self.confirm_delete_dialog.open = False
        self.profile_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    # ==================================================================
    # Profile Dialog — 30 दिवसांचं काम + पूर्ण हिसाब
    # ==================================================================
    def open_profile(self, client_id):
        profile = get_client_profile(client_id, days=30)
        if not profile:
            return

        self.editing_client_id = client_id
        self.profile_dialog.title = ft.Text(profile["garage_name"])

        def stat(title, value, color="white"):
            return ft.Container(
                content=ft.Column(
                    [ft.Text(title, size=10, color="#94a3b8"), ft.Text(value, size=16, weight="bold", color=color)],
                    spacing=2,
                ),
                bgcolor="#161622", padding=10, border_radius=10, expand=True,
            )

        info_lines = [f"👤 {profile['owner_name']}" if profile["owner_name"] else None,
                      f"📱 {profile['mobile']}" if profile["mobile"] else None,
                      f"📍 {profile['location']}" if profile["location"] else None]
        info_lines = [x for x in info_lines if x]

        vehicles_text = ", ".join(profile["vehicles"]) if profile["vehicles"] else "—"

        stats_row = ft.Row(
            [
                stat("एकूण काम", f"₹{profile['total_amt']:.0f}", "#00ffaa"),
                stat("जमा (Paid)", f"₹{profile['total_paid']:.0f}", "#00aaff"),
                stat("बाकी (Due)", f"₹{profile['total_due']:.0f}", "#ff8800"),
            ],
            spacing=8,
        )

        # सर्व नोंदी दाखवतो (Trans. Date रिकामी असली तरी) — जेणेकरून
        # "गाडी कोणती, काय काम, किती पैसे" हे प्रत्येक कामाचं पूर्ण चित्र दिसेल.
        all_records = profile["all_records"]
        records_list = ft.ListView(spacing=8, height=280)
        if not all_records:
            records_list.controls.append(
                ft.Text("अजून या Client चं कोणतंही काम नोंदलेलं नाही.",
                        color="grey", italic=True, size=12))
        else:
            for r in all_records:
                icon = "📤" if (r["type"] or "Given") == "Given" else "📥"
                veh = r["vehicle"] or ""
                if r["vehicle_no"]:
                    veh += f" ({r['vehicle_no']})"
                due_badge = f"  •  ⏳ Due ₹{r['due_amt']:.0f}" if (r["due_amt"] or 0) > 0 else "  •  ✅ Paid Full"
                records_list.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(f"{icon} {veh or 'वाहन नमूद नाही'}", weight="bold", size=13, color="white"),
                                ft.Text(r["notes"] or "Service / Work", size=11, color="#94a3b8"),
                                ft.Text(
                                    f"₹{r['total_amt']:.0f}  |  Paid ₹{r['paid_amt']:.0f}{due_badge}"
                                    f"  •  {r['tx_date'] or 'तारीख नमूद नाही'}",
                                    size=11, color="#64748b",
                                ),
                            ], spacing=2,
                        ),
                        bgcolor="#161622", padding=10, border_radius=8, ink=True,
                        on_click=lambda e, rid=r["id"]: self._open_record(rid),
                    )
                )

        self.profile_body.controls = [
            ft.Row([ft.Text(t, size=12, color="#94a3b8") for t in info_lines], spacing=15) if info_lines else ft.Container(height=0),
            ft.Text(f"🚗 वाहनं: {vehicles_text}", size=12, color="#94a3b8"),
            ft.Container(height=6),
            stats_row,
            ft.Container(height=8),
            ft.Text(f"सर्व कामाच्या नोंदी — एकूण नोंदी: {profile['record_count']}",
                    size=13, weight="bold", color="white"),
            ft.Text("प्रत्येक नोंदीवर क्लिक करून पूर्ण details/edit उघडा.",
                    size=11, color="#64748b", italic=True),
            records_list,
        ]

        self.profile_dialog.open = True
        self.page.update()

    def close_profile_dialog(self, e):
        self.profile_dialog.open = False
        self.page.update()

    def _edit_from_profile(self, e):
        client_row = get_client_by_id(self.editing_client_id)
        self.profile_dialog.open = False
        self.page.update()
        if client_row:
            self.open_add_edit_dialog(client_row)

    def _open_record(self, record_id):
        self.profile_dialog.open = False
        self.page.update()
        if self.on_edit_record:
            self.on_edit_record(record_id)
