import flet as ft
from database import (add_expense, update_expense, delete_expense,
                      get_expenses, get_expense_by_id, get_total_expenses,
                      get_accounts)


class ExpenseView(ft.Row):
    """दुकानाचा खर्च — Category, Amount, Payment Mode, Paid To, Receipt No सोबत."""

    def __init__(self, refresh_callback=None):
        super().__init__(expand=True)
        self.refresh_callback = refresh_callback
        self.editing_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        # ---- Form Fields ----
        self.title_field   = ft.TextField(label="📝 Expense Title *", height=55, **S)
        self.amount        = ft.TextField(label="💰 Amount *", height=55,
                                          prefix=ft.Text("₹ "),
                                          keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.exp_date      = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=55, **S)
        self.paid_to       = ft.TextField(label="👤 Paid To (दुकानदार / व्यक्ती)", height=55, **S)
        self.receipt_no    = ft.TextField(label="🧾 Receipt / Bill No", height=55, **S)
        self.notes         = ft.TextField(label="📝 Notes", multiline=True, height=90, **S)

        self.category = ft.Dropdown(
            label="📂 Category", height=55, value="General",
            options=[
                ft.dropdown.Option("General"),
                ft.dropdown.Option("Parts / सामान"),
                ft.dropdown.Option("Rent / भाडे"),
                ft.dropdown.Option("Electricity / वीज"),
                ft.dropdown.Option("Food / चहा-पाणी"),
                ft.dropdown.Option("Salary / पगार"),
                ft.dropdown.Option("Tool / साधन"),
                ft.dropdown.Option("Transport"),
                ft.dropdown.Option("Other"),
            ], **S
        )
        self.payment_mode = ft.Dropdown(
            label="💳 Payment Mode", height=55, value="Cash",
            options=[
                ft.dropdown.Option("Cash"),
                ft.dropdown.Option("UPI / GPay / PhonePe"),
                ft.dropdown.Option("Bank Transfer"),
                ft.dropdown.Option("Cheque"),
            ], **S
        )
        self.account_dropdown = ft.Dropdown(
            label="🏦 कोणत्या Account मधून (optional — निवडलं तर बॅलन्स आपोआप वजा होईल)",
            height=55, **S
        )

        self.status_text = ft.Text("", size=13, visible=False)
        self.form_title  = ft.Text("Add Expense", size=20, weight="bold", color="#ff8800")

        self.save_btn   = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                             height=50, expand=True, on_click=self.save_expense)
        self.delete_btn = ft.OutlinedButton("Delete", height=50, width=100, visible=False,
                                             style=ft.ButtonStyle(color="#ff4444"),
                                             on_click=self.handle_delete)

        left = ft.Container(
            content=ft.Column([
                self.form_title,
                self.status_text,
                self.title_field,
                ft.Row([self.category, self.amount], spacing=10),
                ft.Row([self.exp_date, self.payment_mode], spacing=10),
                self.account_dropdown,
                ft.Row([self.paid_to, self.receipt_no], spacing=10),
                self.notes,
                ft.Row([
                    ft.OutlinedButton("Cancel", height=50, width=100, on_click=self.clear_form),
                    self.delete_btn,
                    self.save_btn,
                ], spacing=10),
            ], scroll="auto", spacing=12),
            padding=20, width=480, bgcolor="#0e0e16",
        )

        # ---- Right: List ----
        self.total_text  = ft.Text("₹0", size=22, weight="bold", color="#ff8800")
        self.expense_list = ft.ListView(expand=True, spacing=8)

        right = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("📉 All Expenses", size=18, weight="bold", color="white"),
                    ft.Container(expand=True),
                    ft.Column([
                        ft.Text("Total Expense", size=10, color="#94a3b8"),
                        self.total_text,
                    ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=0),
                ]),
                self.expense_list,
            ], expand=True),
            padding=20, expand=True,
        )

        self.controls = [left, ft.VerticalDivider(width=1, color="#1a1a26"), right]

    def did_mount(self):
        self._load_account_options()
        self.refresh()

    def _load_account_options(self, select_id=None):
        accounts = get_accounts()
        self.account_dropdown.options = [ft.dropdown.Option(key="", text="— निवडलेलं नाही —")] + [
            ft.dropdown.Option(key=str(a["id"]), text=f"{a['name']} ({a['account_type']})") for a in accounts
        ]
        self.account_dropdown.value = str(select_id) if select_id else ""
        if self.page:
            self.account_dropdown.update()

    # ------------------------------------------------------------------
    def _show_status(self, msg, color):
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        self.status_text.update()

    def save_expense(self, e):
        title = (self.title_field.value or "").strip()
        amt_raw = (self.amount.value or "").strip()

        if not title:
            self._show_status("⚠️ Expense Title भरा.", "#ff4444"); return
        if not amt_raw:
            self._show_status("⚠️ Amount भरा.", "#ff4444"); return
        try:
            amount = float(amt_raw)
        except ValueError:
            self._show_status("⚠️ Amount फक्त नंबरमध्ये.", "#ff4444"); return
        if amount <= 0:
            self._show_status("⚠️ Amount शून्यापेक्षा जास्त असावी.", "#ff4444"); return

        kwargs = dict(
            title=title,
            category=self.category.value or "General",
            amount=amount,
            exp_date=(self.exp_date.value or "").strip(),
            notes=(self.notes.value or "").strip(),
            payment_mode=self.payment_mode.value or "Cash",
            paid_to=(self.paid_to.value or "").strip(),
            receipt_no=(self.receipt_no.value or "").strip(),
            account_id=int(self.account_dropdown.value) if self.account_dropdown.value else None,
        )

        try:
            if self.editing_id:
                update_expense(self.editing_id, **kwargs)
                self._show_status("✅ Expense अपडेट झाला.", "#00ffaa")
            else:
                add_expense(**kwargs)
                self._show_status("✅ Expense सेव्ह झाला.", "#00ffaa")
        except Exception as ex:
            self._show_status(f"❌ एरर: {ex}", "#ff4444"); return

        if self.refresh_callback:
            self.refresh_callback()
        self.clear_form(None)
        self.refresh()

    def handle_delete(self, e):
        if self.editing_id:
            delete_expense(self.editing_id)
            self._show_status("🗑️ डिलीट झालं.", "#ff8800")
            if self.refresh_callback:
                self.refresh_callback()
            self.clear_form(None)
            self.refresh()

    def load_record(self, row):
        self.editing_id = row["id"]
        self.title_field.value    = row["title"] or ""
        self.category.value       = row["category"] or "General"
        self.amount.value         = str(row["amount"] or 0)
        self.exp_date.value       = row["exp_date"] or ""
        self.payment_mode.value   = row["payment_mode"] or "Cash"
        self.paid_to.value        = row["paid_to"] or ""
        self.receipt_no.value     = row["receipt_no"] or ""
        self.notes.value          = row["notes"] or ""
        self._load_account_options(select_id=row["account_id"] if "account_id" in row.keys() and row["account_id"] else None)
        self.form_title.value     = f"✏️ Edit: {row['title']}"
        self.save_btn.text        = "Update"
        self.delete_btn.visible   = True
        self.status_text.visible  = False
        if self.page: self.update()

    def clear_form(self, e):
        for f in (self.title_field, self.amount, self.exp_date,
                  self.paid_to, self.receipt_no, self.notes):
            f.value = ""
        self.category.value      = "General"
        self.payment_mode.value  = "Cash"
        self._load_account_options()
        self.editing_id          = None
        self.form_title.value    = "Add Expense"
        self.save_btn.text       = "Save"
        self.delete_btn.visible  = False
        if self.page: self.update()

    # ------------------------------------------------------------------
    def refresh(self):
        self.expense_list.controls.clear()
        records = get_expenses()

        if not records:
            self.expense_list.controls.append(
                ft.Text("अजून कोणताही खर्च नोंदलेला नाही.", color="grey", italic=True))
        else:
            for row in records:
                self.expense_list.controls.append(self._row_card(row))

        self.total_text.value = f"₹{get_total_expenses():.0f}"
        if self.page: self.update()

    def _row_card(self, row):
        mode_color = {
            "Cash": "#00ffaa", "UPI / GPay / PhonePe": "#00aaff",
            "Bank Transfer": "#aa88ff", "Cheque": "#ff8800",
        }.get(row["payment_mode"] or "Cash", "#94a3b8")

        sub = "  •  ".join(filter(None, [
            row["category"],
            row["exp_date"],
            row["payment_mode"],
            f"To: {row['paid_to']}" if row["paid_to"] else None,
        ]))

        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(row["title"], weight="bold", color="white", size=14),
                    ft.Text(sub, size=11, color="#94a3b8"),
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text(f"₹{row['amount']:.0f}", color="#ff8800",
                            weight="bold", size=16),
                    ft.Container(
                        content=ft.Text(row["payment_mode"] or "Cash",
                                        size=9, color="black"),
                        bgcolor=mode_color, border_radius=4,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2),
            ]),
            bgcolor="#161622", padding=12, border_radius=10, ink=True,
            on_click=lambda e, r=row: self.load_record(r),
        )
