"""
============================================================================
INVENTORY MASTER VIEW — Part Number (Unique) आधारित Product Database
============================================================================
"""
import flet as ft
from database import (
    add_part, update_part, archive_part, get_parts, get_part_by_id,
    search_parts, get_part_stock, find_part_by_number,
)


class InventoryMasterView(ft.Container):
    """Sr.No, Part Number(Unique), Description, HSN/SAC, GST%, Location,
    Reorder Level (डिफॉल्ट 5, editable), Current Stock — Save/Edit/Delete सह."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.editing_part_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}
        self.S = S

        self.search_field = ft.TextField(
            hint_text="Part Number / Description शोधा...",
            bgcolor="#161622", height=45,
            border_color="#1a1a26", focused_border_color="#00ffaa",
            prefix_icon=ft.Icons.SEARCH,
        )
        self.search_field.on_change = self.handle_search
        self.part_list = ft.ListView(expand=True, spacing=8)

        # ---------------- (+) Add बटण — पॅनलच्या वरती स्पष्ट दिसणारं ----------------
        self.add_btn = ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD_CIRCLE, size=20), ft.Text("नवीन Part जोडा (+)", weight="bold")], spacing=6),
            bgcolor="#00ffaa", color="black", height=48,
            on_click=lambda e: self.open_add_edit_dialog(None),
        )

        # ---------------- Add/Edit Dialog फील्ड्स ----------------
        self.f_part_number = ft.TextField(label="🔢 Part Number * (Unique)", height=52, **S)
        self.f_description = ft.TextField(label="📝 Description *", height=52, **S)
        self.f_hsn = ft.TextField(label="🧾 HSN/SAC Code", height=52, **S)
        self.f_gst_rate = ft.Dropdown(
            label="📐 GST Rate %", height=52, value="18",
            options=[ft.dropdown.Option(v) for v in ("0", "5", "12", "18", "28")], **S
        )
        self.f_location = ft.TextField(label="📍 Location / Rack", height=52, **S)
        self.f_reorder_level = ft.TextField(label="⚠️ Reorder Level", height=52, value="5",
                                             keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.f_opening_stock = ft.TextField(label="📦 सुरुवातीचा Stock (नवीन Part साठीच)", height=52,
                                             value="0", keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.dialog_msg = ft.Text("", size=12, color="#ff4444", visible=False)

        self.save_part_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                                 on_click=self.handle_save_part)
        self.delete_part_btn = ft.TextButton("Delete", visible=False,
                                              style=ft.ButtonStyle(color="#ff4444"),
                                              on_click=self.handle_delete_part)

        self.add_edit_dialog = ft.AlertDialog(
            title=ft.Text("➕ नवीन Part"),
            content=ft.Container(
                content=ft.Column(
                    [
                        self.f_part_number, self.f_description,
                        ft.Row([self.f_hsn, self.f_gst_rate], spacing=10),
                        ft.Row([self.f_location, self.f_reorder_level], spacing=10),
                        self.f_opening_stock, self.dialog_msg,
                    ],
                    tight=True, spacing=10, scroll="auto",
                ),
                width=420, height=420,
            ),
            actions=[
                self.delete_part_btn,
                ft.TextButton("Cancel", on_click=self.close_add_edit_dialog),
                self.save_part_btn,
            ],
        )

        self.confirm_delete_dialog = ft.AlertDialog(
            title=ft.Text("Part डिलीट करायचा?"),
            content=ft.Text("हा Part कायमचा काढला जाईल. जुन्या बिलांमधली नोंद मात्र सुरक्षित राहील."),
            actions=[
                ft.TextButton("नाही", on_click=self._close_confirm_delete),
                ft.TextButton("हो, डिलीट करा", style=ft.ButtonStyle(color="#ff4444"),
                              on_click=self._confirm_delete_now),
            ],
        )

        self.adj_qty = ft.TextField(label="Qty (+ वाढ / - घट)", height=48, **S)
        self.adj_reason = ft.Dropdown(
            label="कारण", height=48, value="Damaged",
            options=[ft.dropdown.Option(r) for r in
                     ["Damaged / तुटलं", "Lost / Theft", "Found / सापडलं", "Audit Correction", "Other"]],
            **S,
        )
        self.adj_notes = ft.TextField(label="Notes (ऐच्छिक)", height=48, **S)
        self.adj_dialog = ft.AlertDialog(
            title=ft.Text("⚙️ Stock Adjust करा"),
            content=ft.Container(
                content=ft.Column([self.adj_qty, self.adj_reason, self.adj_notes], tight=True, spacing=10),
                width=340,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self._close_adj_dialog),
                ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black", on_click=self._save_adjustment),
            ],
        )

        # ---------------- Header row (टेबल सारखी) ----------------
        header_row = ft.Container(
            content=ft.Row([
                ft.Text("Part Number", size=11, weight="bold", color="#94a3b8", width=140),
                ft.Text("Description", size=11, weight="bold", color="#94a3b8", expand=True),
                ft.Text("HSN/SAC", size=11, weight="bold", color="#94a3b8", width=90),
                ft.Text("GST%", size=11, weight="bold", color="#94a3b8", width=60),
                ft.Text("Location", size=11, weight="bold", color="#94a3b8", width=100),
                ft.Text("Reorder", size=11, weight="bold", color="#94a3b8", width=70),
                ft.Text("Stock", size=11, weight="bold", color="#94a3b8", width=70),
            ]),
            padding=ft.Padding(left=14, right=14, top=8, bottom=8),
            bgcolor="#161622", border_radius=8,
        )

        self.content = ft.Column(
            [
                ft.Row([ft.Text("📦 Inventory Master", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True), self.add_btn]),
                ft.Container(height=5),
                self.search_field,
                ft.Container(height=10),
                header_row,
                self.part_list,
            ],
            spacing=10, expand=True,
        )

    def open_adjust_dialog(self, part_row):
        self._adjusting_part_id = part_row["id"]
        self.adj_qty.value = ""
        self.adj_notes.value = ""
        self.adj_dialog.title = ft.Text(f"⚙️ Adjust: {part_row['product_name']}")
        self.adj_dialog.open = True
        self.page.update()

    def _close_adj_dialog(self, e):
        self.adj_dialog.open = False
        self.page.update()

    def _save_adjustment(self, e):
        try:
            qty = float(self.adj_qty.value or 0)
        except ValueError:
            return
        if qty == 0:
            return
        from database import adjust_stock
        adjust_stock(self._adjusting_part_id, qty, reason=self.adj_reason.value, notes=self.adj_notes.value or "")
        self.adj_dialog.open = False
        self.page.update()
        self.refresh()

    # ==================================================================
    def did_mount(self):
        for d in (self.add_edit_dialog, self.confirm_delete_dialog):
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
                ft.Text("अजून कोणताही Part जोडलेला नाही. वरती '+ नवीन Part जोडा' दाबा.",
                        color="grey", italic=True))
        else:
            for row in records:
                self.part_list.controls.append(self._part_row(row))
        self.update()

    def handle_search(self, e):
        self.refresh(query=self.search_field.value)

    def _part_row(self, row):
        stock = get_part_stock(row["id"])
        reorder = row["reorder_level"] if "reorder_level" in row.keys() and row["reorder_level"] is not None else 5
        is_low = stock <= reorder
        stock_color = "#ff4444" if is_low else "#00ffaa"

        return ft.Container(
            content=ft.Row([
                ft.Text(row["part_number"] or "-", size=13, weight="bold", color="white", width=140),
                ft.Text(row["product_name"] or "-", size=13, color="white", expand=True),
                ft.Text(row["hsn_sac"] or "-", size=12, color="#94a3b8", width=90),
                ft.Text(f"{(row['gst_rate'] or 0):.0f}%", size=12, color="#94a3b8", width=60),
                ft.Text(row["location"] or "-", size=12, color="#94a3b8", width=100),
                ft.Text(f"{reorder:.0f}", size=12, color="#94a3b8", width=70),
                ft.Text(f"{stock:.0f}", size=13, weight="bold", color=stock_color, width=70),
            ]),
            bgcolor="#161622", padding=ft.Padding(left=14, right=14, top=10, bottom=10),
            border_radius=8, ink=True,
            border=ft.Border(left=ft.BorderSide(3, "#ff4444")) if is_low else None,
            on_click=lambda e, r=row: self.open_add_edit_dialog(r),
        )

    # ==================================================================
    def open_add_edit_dialog(self, part_row):
        self.dialog_msg.visible = False
        if part_row is None:
            self.editing_part_id = None
            self.add_edit_dialog.title = ft.Text("➕ नवीन Part")
            self.f_part_number.value = ""
            self.f_description.value = ""
            self.f_hsn.value = ""
            self.f_gst_rate.value = "18"
            self.f_location.value = ""
            self.f_reorder_level.value = "5"
            self.f_opening_stock.value = "0"
            self.f_opening_stock.visible = True
            self.delete_part_btn.visible = False
            self.save_part_btn.text = "Save"
        else:
            self.editing_part_id = part_row["id"]
            self.add_edit_dialog.title = ft.Text(f"✏️ Edit: {part_row['part_number']}")
            self.f_part_number.value = part_row["part_number"] or ""
            self.f_description.value = part_row["product_name"] or ""
            self.f_hsn.value = part_row["hsn_sac"] if "hsn_sac" in part_row.keys() and part_row["hsn_sac"] else ""
            self.f_gst_rate.value = str(part_row["gst_rate"]) if "gst_rate" in part_row.keys() and part_row["gst_rate"] is not None else "18"
            self.f_location.value = part_row["location"] if "location" in part_row.keys() and part_row["location"] else ""
            self.f_reorder_level.value = str(part_row["reorder_level"]) if "reorder_level" in part_row.keys() and part_row["reorder_level"] is not None else "5"
            self.f_opening_stock.visible = False   # जुना Part -> स्टॉक फक्त Module 2 (Stock-In) मधूनच वाढतो
            self.delete_part_btn.visible = True
            self.save_part_btn.text = "Update"

        self.add_edit_dialog.open = True
        self.page.update()

    def close_add_edit_dialog(self, e):
        self.add_edit_dialog.open = False
        self.page.update()

    def handle_save_part(self, e):
        part_number = (self.f_part_number.value or "").strip()
        description = (self.f_description.value or "").strip()
        if not part_number:
            self._show_dialog_msg("⚠️ Part Number भरा.")
            return
        if not description:
            self._show_dialog_msg("⚠️ Description भरा.")
            return

        existing = find_part_by_number(part_number, exclude_id=self.editing_part_id)
        if existing:
            self._show_dialog_msg("⚠️ हा Part Number आधीच वापरात आहे — Unique असावा.")
            return

        try:
            reorder_level = float(self.f_reorder_level.value or 5)
            opening_stock = float(self.f_opening_stock.value or 0)
        except ValueError:
            self._show_dialog_msg("⚠️ Reorder Level/Stock फक्त नंबरमध्ये.")
            return

        kwargs = dict(
            product_name=description, part_number=part_number,
            hsn_sac=(self.f_hsn.value or "").strip(),
            gst_rate=float(self.f_gst_rate.value or 18),
            location=(self.f_location.value or "").strip(),
            reorder_level=reorder_level,
        )

        if self.editing_part_id:
            update_part(self.editing_part_id, **kwargs)
        else:
            new_id = add_part(**kwargs)
            if opening_stock > 0:
                from database import record_stock_in
                record_stock_in(new_id, opening_stock, notes="सुरुवातीचा स्टॉक")

        self.add_edit_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)

    def _show_dialog_msg(self, text):
        self.dialog_msg.value = text
        self.dialog_msg.visible = True
        self.dialog_msg.update()

    def handle_delete_part(self, e):
        self.add_edit_dialog.open = False
        self.confirm_delete_dialog.open = True
        self.page.update()

    def _close_confirm_delete(self, e):
        self.confirm_delete_dialog.open = False
        self.page.update()

    def _confirm_delete_now(self, e):
        if self.editing_part_id:
            archive_part(self.editing_part_id)
        self.confirm_delete_dialog.open = False
        self.page.update()
        self.refresh(query=self.search_field.value)