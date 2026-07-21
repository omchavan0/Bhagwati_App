import flet as ft
from database import (add_work, update_work, delete_work,
                      get_daily_work, get_work_by_id, toggle_work_status)


class WorkView(ft.Row):
    """रोजची कामं — Customer, Vehicle, Mobile, Labour+Parts Charge, Parts Used, Status."""

    def __init__(self, refresh_callback=None):
        super().__init__(expand=True)
        self.refresh_callback = refresh_callback
        self.editing_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        # ---- Form Fields ----
        self.customer_name = ft.TextField(label="👤 Customer Name *", height=55, **S)
        self.mobile        = ft.TextField(label="📱 Mobile Number", height=55,
                                          keyboard_type=ft.KeyboardType.PHONE, **S)
        self.vehicle       = ft.TextField(label="🚗 Vehicle Name", height=55, **S)
        self.vehicle_no    = ft.TextField(label="🔢 Vehicle Number", height=55, **S)
        self.work_desc     = ft.TextField(label="🔧 Work Description *",
                                          multiline=True, height=80, **S)
        self.parts_used    = ft.TextField(label="🔩 Parts Used / Material",
                                          multiline=True, height=70, **S)
        self.labour_charge = ft.TextField(label="👷 Labour Charge", height=55,
                                          prefix=ft.Text("₹ "),
                                          keyboard_type=ft.KeyboardType.NUMBER,
                                          value="0", **S)
        self.parts_charge  = ft.TextField(label="🔩 Parts Charge", height=55,
                                          prefix=ft.Text("₹ "),
                                          keyboard_type=ft.KeyboardType.NUMBER,
                                          value="0", **S)
        self.total_charge  = ft.TextField(label="💰 Total Charge", height=55,
                                          prefix=ft.Text("₹ "),
                                          read_only=True, **S)
        self.work_date     = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=55, **S)

        # Total = Labour + Parts auto-calculate
        self.labour_charge.on_change = self._recalc_total
        self.parts_charge.on_change  = self._recalc_total

        self.status_dropdown = ft.Dropdown(
            label="📌 Status", height=55, value="Pending",
            options=[
                ft.dropdown.Option("Pending"),
                ft.dropdown.Option("In Progress"),
                ft.dropdown.Option("Done"),
            ], **S
        )
        self.priority_dropdown = ft.Dropdown(
            label="🚨 Priority", height=55, value="Normal",
            options=[
                ft.dropdown.Option("Normal"),
                ft.dropdown.Option("Urgent"),
            ], **S
        )

        self.status_text = ft.Text("", size=13, visible=False)
        self.form_title  = ft.Text("Add Daily Work", size=20, weight="bold", color="#00ffaa")

        self.save_btn   = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                             height=50, expand=True, on_click=self.save_work)
        self.delete_btn = ft.OutlinedButton("Delete", height=50, width=100, visible=False,
                                             style=ft.ButtonStyle(color="#ff4444"),
                                             on_click=self.handle_delete)

        left = ft.Container(
            content=ft.Column([
                self.form_title,
                self.status_text,
                ft.Row([self.customer_name, self.mobile], spacing=10),
                ft.Row([self.vehicle, self.vehicle_no], spacing=10),
                self.work_desc,
                self.parts_used,
                ft.Row([self.labour_charge, self.parts_charge, self.total_charge], spacing=10),
                ft.Row([self.work_date, self.priority_dropdown], spacing=10),
                self.status_dropdown,
                ft.Row([
                    ft.OutlinedButton("Cancel", height=50, width=100, on_click=self.clear_form),
                    self.delete_btn,
                    self.save_btn,
                ], spacing=10),
            ], scroll="auto", spacing=12),
            padding=20, width=480, bgcolor="#0e0e16",
        )

        # ---- Right: List ----
        self.pending_text = ft.Text("0", size=20, weight="bold", color="#ff8800")
        self.inprog_text  = ft.Text("0", size=20, weight="bold", color="#00aaff")
        self.done_text    = ft.Text("0", size=20, weight="bold", color="#00ffaa")
        self.work_list    = ft.ListView(expand=True, spacing=8)

        def stat_chip(label, value_text, color):
            return ft.Container(
                content=ft.Column([
                    ft.Text(label, size=10, color="#94a3b8"),
                    value_text,
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor="#161622", padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                border_radius=10, expand=True,
            )

        right = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("📝 Daily Work", size=18, weight="bold", color="white"),
                    ft.Container(expand=True),
                    stat_chip("Pending", self.pending_text, "#ff8800"),
                    stat_chip("In Progress", self.inprog_text, "#00aaff"),
                    stat_chip("Done", self.done_text, "#00ffaa"),
                ], spacing=8),
                self.work_list,
            ], expand=True),
            padding=20, expand=True,
        )

        self.controls = [left, ft.VerticalDivider(width=1, color="#1a1a26"), right]

    def did_mount(self):
        self.refresh()

    # ------------------------------------------------------------------
    def _recalc_total(self, e):
        try:
            labour = float(self.labour_charge.value or 0)
            parts  = float(self.parts_charge.value or 0)
            self.total_charge.value = f"{labour + parts:.2f}"
        except ValueError:
            self.total_charge.value = ""
        self.total_charge.update()

    def _show_status(self, msg, color):
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        self.status_text.update()

    # ------------------------------------------------------------------
    def save_work(self, e):
        name = (self.customer_name.value or "").strip()
        desc = (self.work_desc.value or "").strip()

        if not name:
            self._show_status("⚠️ Customer Name भरा.", "#ff4444"); return
        if not desc:
            self._show_status("⚠️ Work Description भरा.", "#ff4444"); return

        try:
            labour = float(self.labour_charge.value or 0)
            parts  = float(self.parts_charge.value or 0)
        except ValueError:
            self._show_status("⚠️ Charge amount फक्त नंबरमध्ये.", "#ff4444"); return

        charge_amt = labour + parts

        kwargs = dict(
            customer_name=name,
            vehicle=(self.vehicle.value or "").strip(),
            work_desc=desc,
            charge_amt=charge_amt,
            work_date=(self.work_date.value or "").strip(),
            status=self.status_dropdown.value or "Pending",
            mobile=(self.mobile.value or "").strip(),
            vehicle_no=(self.vehicle_no.value or "").strip(),
            labour_charge=labour,
            parts_charge=parts,
            parts_used=(self.parts_used.value or "").strip(),
        )

        try:
            if self.editing_id:
                update_work(self.editing_id, **kwargs)
                self._show_status("✅ काम अपडेट झालं.", "#00ffaa")
            else:
                add_work(**kwargs)
                self._show_status("✅ काम सेव्ह झालं.", "#00ffaa")
        except Exception as ex:
            self._show_status(f"❌ एरर: {ex}", "#ff4444"); return

        if self.refresh_callback:
            self.refresh_callback()
        self.clear_form(None)
        self.refresh()

    def handle_delete(self, e):
        if self.editing_id:
            delete_work(self.editing_id)
            self._show_status("🗑️ डिलीट झालं.", "#ff8800")
            if self.refresh_callback:
                self.refresh_callback()
            self.clear_form(None)
            self.refresh()

    def handle_toggle(self, record_id):
        toggle_work_status(record_id)
        self.refresh()

    def load_record(self, row):
        self.editing_id          = row["id"]
        self.customer_name.value = row["customer_name"] or ""
        self.mobile.value        = row["mobile"] or ""
        self.vehicle.value       = row["vehicle"] or ""
        self.vehicle_no.value    = row["vehicle_no"] or ""
        self.work_desc.value     = row["work_desc"] or ""
        self.parts_used.value    = row["parts_used"] or ""
        self.labour_charge.value = str(row["labour_charge"] or 0)
        self.parts_charge.value  = str(row["parts_charge"] or 0)
        self.total_charge.value  = str(row["charge_amt"] or 0)
        self.work_date.value     = row["work_date"] or ""
        self.status_dropdown.value = row["status"] or "Pending"
        self.form_title.value    = f"✏️ Edit: {row['customer_name']}"
        self.save_btn.text       = "Update"
        self.delete_btn.visible  = True
        self.status_text.visible = False
        if self.page: self.update()

    def clear_form(self, e):
        for f in (self.customer_name, self.mobile, self.vehicle,
                  self.vehicle_no, self.work_desc, self.parts_used, self.work_date):
            f.value = ""
        self.labour_charge.value   = "0"
        self.parts_charge.value    = "0"
        self.total_charge.value    = ""
        self.status_dropdown.value = "Pending"
        self.editing_id            = None
        self.form_title.value      = "Add Daily Work"
        self.save_btn.text         = "Save"
        self.delete_btn.visible    = False
        if self.page: self.update()

    # ------------------------------------------------------------------
    def refresh(self):
        self.work_list.controls.clear()
        records = get_daily_work()

        if not records:
            self.work_list.controls.append(
                ft.Text("अजून कोणतंही काम नोंदलेलं नाही.", color="grey", italic=True))
        else:
            for row in records:
                self.work_list.controls.append(self._row_card(row))

        pending = sum(1 for r in records if r["status"] == "Pending")
        inprog  = sum(1 for r in records if r["status"] == "In Progress")
        done    = sum(1 for r in records if r["status"] == "Done")
        self.pending_text.value = str(pending)
        self.inprog_text.value  = str(inprog)
        self.done_text.value    = str(done)

        if self.page: self.update()

    def _row_card(self, row):
        status = row["status"] or "Pending"
        s_color = {"Pending": "#ff8800", "In Progress": "#00aaff", "Done": "#00ffaa"}.get(status, "#94a3b8")
        s_icon  = {"Pending": "⏳", "In Progress": "🔧", "Done": "✅"}.get(status, "•")

        charge = row["charge_amt"] or 0
        sub_parts = []
        if row["vehicle"]:
            sub_parts.append(f"{row['vehicle']}")
        if row["vehicle_no"]:
            sub_parts.append(row["vehicle_no"])
        if row["work_date"]:
            sub_parts.append(row["work_date"])
        sub = "  •  ".join(sub_parts)

        labour_str = f"L: ₹{row['labour_charge']:.0f}" if row["labour_charge"] else ""
        parts_str  = f"P: ₹{row['parts_charge']:.0f}" if row["parts_charge"] else ""
        breakdown  = "  |  ".join(filter(None, [labour_str, parts_str]))

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Text(row["customer_name"], weight="bold", color="white", size=14),
                        ft.Text(row["work_desc"] or "", size=12, color="#94a3b8"),
                        ft.Text(sub, size=11, color="#64748b"),
                        ft.Text(breakdown, size=11, color="#64748b") if breakdown else ft.Container(height=0),
                    ], spacing=2),
                    expand=True,
                    on_click=lambda e, r=row: self.load_record(r),
                ),
                ft.Column([
                    ft.Text(f"₹{charge:.0f}", weight="bold", color="white", size=15),
                    ft.TextButton(
                        f"{s_icon} {status}",
                        style=ft.ButtonStyle(color=s_color),
                        on_click=lambda e, rid=row["id"]: self.handle_toggle(rid),
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2),
            ]),
            bgcolor="#161622", padding=12, border_radius=10,
        )
