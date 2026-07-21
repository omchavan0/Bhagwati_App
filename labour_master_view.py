import flet as ft
from database import (
    add_labour, update_labour, archive_labour, get_labour_list, search_labour,
)


class LabourMasterView(ft.Container):
    """Labour/Service Master — SAC Code + GST सह. Stock नसतो, त्यामुळे
    inventory_view.py पेक्षा हलकं — फक्त Catalog + Add/Edit/Archive."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.editing_labour_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        self.search_field = ft.TextField(
            hint_text="Labour Name / Technician शोधा...",
            bgcolor="#161622", height=45,
            border_color="#1a1a26", focused_border_color="#00ffaa",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.handle_search,
        )
        self.labour_list = ft.ListView(expand=True, spacing=10)

        add_btn = ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD, size=18), ft.Text("Add Labour", weight="bold")], spacing=6),
            bgcolor="#00ffaa", color="black", height=45,
            on_click=lambda e: self.open_add_edit_dialog(None),
        )

        # ---------------- Add/Edit Dialog फील्ड्स ----------------
        self.f_name = ft.TextField(label="🔧 Labour/Service Name *", height=52, **S)
        self.f_sac = ft.TextField(label="🧾 SAC Code", height=52, value="998714", **S)
        self.f_gst_rate = ft.Dropdown(
            label="📐 GST %", height=52, value="18",
            options=[ft.dropdown.Option(v) for v in ("0", "5", "12", "18", "28")], **S
        )
        self.f_gst_enabled = ft.Switch(label="GST लागू करायचा?", value=True, active_color="#00ffaa")
        self.f_charge = ft.TextField(label="💰 डिफॉल्ट Labour Charge", height=52,
                                      prefix=ft.Text("₹ "), keyboard_type=ft.KeyboardType.NUMBER,
                                      value="0", **S)
        self.f_technician = ft.TextField(label="👨‍🔧 Technician (ऐच्छिक)", height=52, **S)
        self.f_description = ft.TextField(label="📝 Description", height=70, multiline=True, **S)
        self.dialog_msg = ft.Text("", size=12, color="#ff4444", visible=False)

        self.save_labour_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                                   on_click=self.handle_save_labour)
        self.archive_labour_btn = ft.TextButton("Archive", visible=False,
                                                  style=ft.ButtonStyle(color="#ff8800"),
                                                  on_click=self.handle_archive_labour)

        self.add_edit_dialog = ft.AlertDialog(
            title=ft.Text("➕ नवीन Labour/Service"),
            content=ft.Container(
                content=ft.Column(
                    [
                        self.f_name,
                        ft.Row([self.f_sac, self.f_gst_rate], spacing=10),
                        self.f_gst_enabled,
                        self.f_charge,
                        self.f_technician,
                        self.f_description,
                        self.dialog_msg,
                    ],
                    tight=True, spacing=10,
                ),
                width=400,
            ),
            actions=[
                self.archive_labour_btn,
                ft.TextButton("Cancel", on_click=self.close_add_edit_dialog),
                self.save_labour_btn,
            ],
        )

        self.confirm_archive_dialog = ft.AlertDialog(
            title=ft.Text("Labour Item आर्काइव्ह करायचं?"),
            content=ft.Text("हे dropdown मधून गायब होईल, पण जुन्या बिलांमधली नोंद सुरक्षित राहील."),
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
                        ft.Text("🔧 Labour / Service Master", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True),
                        add_btn,
                    ]
                ),
                ft.Container(height=5),
                self.search_field,
                ft.Container(height=10),
                self.labour_list,
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
        self.labour_list.controls.clear()
        records = search_labour(query) if query else get_labour_list()

        if not records:
            self.labour_list.controls.append(
                ft.Text("अजून कोणतंही Labour Item जोडलेलं नाही. वरती '+ Add Labour' दाबा.",
                        color="grey", italic=True))
        else:
            for row in records:
                self.labour_list.controls.append(self._labour_card(row))
        self.update()

    def handle_search(self, e):
        self.refresh(query=self.search_field.value)

    # ==================================================================
    def _labour_card(self, row):
        gst_on = bool(row["gst_enabled"]) if "gst_enabled" in row.keys() else True
        sub_parts = [row["sac_code"], f"GST {row['gst_rate']:.0f}%" if gst_on else "No GST", row["technician"]]
        sub = "  •  ".join([p for p in sub_parts if p])

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text("🔧", size=20),
                        bgcolor="#12251e", width=44, height=44, border_radius=10,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(row["labour_name"], weight="bold", color="white", size=15),
                            ft.Text(sub or "—", size=11, color="#94a3b8"),
                        ], spacing=2, expand=True,
                    ),
                    ft.Text(f"₹{(row['labour_charge'] or 0):.0f}", weight="bold", size=15, color="#00ffaa"),
                    ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color="#64748b"),
                ],
                spacing=12,
            ),
            bgcolor="#161622", padding=14, border_radius=12, ink=True,
            on_click=lambda e, row=row: self.open_add_edit_dialog(row),
        )

    # ==================================================================
    def open_add_edit_dialog(self, labour_row):
        self.dialog_msg.visible = False
        if labour_row is None:
            self.editing_labour_id = None
            self.add_edit_dialog.title = ft.Text("➕ नवीन Labour/Service")
            self.f_name.value = ""
            self.f_sac.value = "998714"
            self.f_gst_rate.value = "18"
            self.f_gst_enabled.value = True
            self.f_charge.value = "0"
            self.f_technician.value = ""
            self.f_description.value = ""
            self.archive_labour_btn.visible = False
            self.save_labour_btn.text = "Save"
        else:
            self.editing_labour_id = labour_row["id"]
            self.add_edit_dialog.title = ft.Text(f"✏️ Edit: {labour_row['labour_name']}")
            self.f_name.value = labour_row["labour_name"] or ""
            self.f_sac.value = labour_row["sac_code"] or "998714"
            self.f_gst_rate.value = str(labour_row["gst_rate"]) if labour_row["gst_rate"] is not None else "18"
            self.f_gst_enabled.value = bool(labour_row["gst_enabled"]) if "gst_enabled" in labour_row.keys() else True
            self.f_charge.value = str(labour_row["labour_charge"] or 0)
            self.f_technician.value = labour_row["technician"] or ""
            self.f_description.value = labour_row["description"] or ""
            self.archive_labour_btn.visible = True
            self.save_labour_btn.text = "Update"

        self.add_edit_dialog.open = True
        self.page.update()

    def close_add_edit_dialog(self, e):
        self.add_edit_dialog.open = False
        self.page.update()

    def handle_save_labour(self, e):
        name = (self.f_name.value or "").strip()
        if not name:
            self._show_dialog_msg("⚠️ Labour/Service Name भरा.")
            return
        try:
            charge = float(self.f_charge.value or 0)
        except ValueError:
            self._show_dialog_msg("⚠️ Charge फक्त नंबरमध्ये.")
            return

        kwargs = dict(
            labour_name=name,
            sac_code=(self.f_sac.value or "998714").strip(),
            gst_rate=float(self.f_gst_rate.value or 18),
            gst_enabled=self.f_gst_enabled.value,
            labour_charge=charge,
            technician=(self.f_technician.value or "").strip(),
            description=(self.f_description.value or "").strip(),
        )

        if self.editing_labour_id:
            update_labour(self.editing_labour_id, **kwargs)
        else:
            add_labour(**kwargs)

        self.add_edit_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    def _show_dialog_msg(self, text):
        self.dialog_msg.value = text
        self.dialog_msg.visible = True
        self.dialog_msg.update()

    # ==================================================================
    def handle_archive_labour(self, e):
        self.add_edit_dialog.open = False
        self.confirm_archive_dialog.open = True
        self.page.update()

    def _close_confirm_archive(self, e):
        self.confirm_archive_dialog.open = False
        self.page.update()

    def _confirm_archive_now(self, e):
        if self.editing_labour_id:
            archive_labour(self.editing_labour_id)
        self.confirm_archive_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)