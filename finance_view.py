import flet as ft
from database import (
    add_account, update_account, archive_account, get_accounts,
    get_account_by_id, get_all_account_balances, get_account_balance,
    add_transaction, record_transfer, delete_transaction,
    get_account_transactions, has_any_transactions, ACCOUNT_TYPES,
    update_transaction, get_transaction_by_id,
)


class FinanceView(ft.Container):
    """Cash / Bank / UPI खाती + प्रत्येक खात्याचा live हिशोब (Ledger).
    - + Add Account: नवीन खातं (Opening Balance सकट)
    - खात्याच्या कार्डवर क्लिक -> Detail: बॅलन्स + अलीकडचे व्यवहार + Deposit/
      Withdraw/Transfer/Edit/Archive
    - सगळ्या खात्यांची एकूण बेरीज (Grand Total) वरती दिसते"""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.editing_account_id = None

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        # ---------------- Header + Grand Total ----------------
        self.grand_total_text = ft.Text("₹0", size=22, weight="bold", color="#00ffaa")
        add_btn = ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD, size=18), ft.Text("Add Account", weight="bold")], spacing=6),
            bgcolor="#00ffaa", color="black", height=45,
            on_click=lambda e: self.open_add_edit_dialog(None),
        )
        self.account_list = ft.ListView(expand=True, spacing=10)

        # ---------------- Add/Edit Account Dialog ----------------
        self.f_name = ft.TextField(label="🏦 Account Name *", height=52, **S)
        self.f_type = ft.Dropdown(
            label="📂 Type", height=52,
            options=[ft.dropdown.Option(t) for t in ACCOUNT_TYPES], value="Cash", **S
        )
        self.f_opening = ft.TextField(label="💰 Opening Balance", height=52,
                                       prefix=ft.Text("₹ "), keyboard_type=ft.KeyboardType.NUMBER,
                                       value="0", **S)
        self.f_notes = ft.TextField(label="📝 Notes", height=52, **S)
        self.acc_dialog_msg = ft.Text("", size=12, color="#ff4444", visible=False)

        self.save_account_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                                    on_click=self.handle_save_account)
        self.archive_account_btn = ft.TextButton("Archive", visible=False,
                                                   style=ft.ButtonStyle(color="#ff8800"),
                                                   on_click=self.handle_archive_account)

        self.add_edit_dialog = ft.AlertDialog(
            title=ft.Text("➕ नवीन Account"),
            content=ft.Container(
                content=ft.Column(
                    [self.f_name, self.f_type, self.f_opening, self.f_notes, self.acc_dialog_msg],
                    tight=True, spacing=10,
                ),
                width=380,
            ),
            actions=[
                self.archive_account_btn,
                ft.TextButton("Cancel", on_click=self.close_add_edit_dialog),
                self.save_account_btn,
            ],
        )

        # ---------------- Archive confirm ----------------
        self.confirm_archive_dialog = ft.AlertDialog(
            title=ft.Text("Account आर्काइव्ह करायचं?"),
            content=ft.Text("हे खातं dropdown मधून गायब होईल, पण त्याचा जुना हिशोब (history) सुरक्षित राहील."),
            actions=[
                ft.TextButton("नाही", on_click=self._close_confirm_archive),
                ft.TextButton("हो, आर्काइव्ह करा", style=ft.ButtonStyle(color="#ff8800"),
                              on_click=self._confirm_archive_now),
            ],
        )

        # ---------------- Deposit/Withdraw Dialog ----------------
        self.tx_account_id = None
        self.tx_mode = "credit"  # "credit" (Deposit) | "debit" (Withdraw)
        self.tx_amount = ft.TextField(label="💰 Amount *", height=52, prefix=ft.Text("₹ "),
                                       keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.tx_date = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=52, **S)
        self.tx_category = ft.TextField(label="📂 Category (उदा. Sale Payment)", height=52, **S)
        self.tx_notes = ft.TextField(label="📝 Notes", height=52, **S)
        self.tx_dialog_msg = ft.Text("", size=12, color="#ff4444", visible=False)
        self.save_tx_btn = ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black",
                                              on_click=self.handle_save_transaction)
        self.tx_dialog = ft.AlertDialog(
            title=ft.Text("💵 Deposit"),
            content=ft.Container(
                content=ft.Column([self.tx_amount, self.tx_date, self.tx_category, self.tx_notes, self.tx_dialog_msg],
                                   tight=True, spacing=10),
                width=380,
            ),
            actions=[ft.TextButton("Cancel", on_click=self.close_tx_dialog), self.save_tx_btn],
        )

        # ---------------- Edit Transaction Dialog (फक्त मॅन्युअल एन्ट्रीजसाठी) ----------------
        # टीप: फक्त 'amount' कॉलम मध्ये बदल करत नाही — ती चुकीच्या नोंदी दुरुस्त
        # करण्यासाठी (उदा. रक्कम चुकीची टाकली गेली) संपूर्ण एन्ट्रीच एडिट करतो.
        # Sale/Expense कडून आपोआप आलेल्या एन्ट्रीज (reference_table असलेल्या)
        # आणि Transfer च्या एन्ट्रीज इथून एडिट होत नाहीत (त्या मूळ स्क्रीनवरूनच
        # बदलाव्या लागतील) — ledger दोन्ही बाजूंनी नेहमी जुळलेला राहावा म्हणून.
        self.edit_tx_id = None
        self.edit_tx_account_id = None
        self.edit_tx_amount = ft.TextField(label="💰 Amount *", height=52, prefix=ft.Text("₹ "),
                                            keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.edit_tx_date = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=52, **S)
        self.edit_tx_category = ft.TextField(label="📂 Category", height=52, **S)
        self.edit_tx_notes = ft.TextField(label="📝 Notes", height=52, **S)
        self.edit_tx_dialog_msg = ft.Text("", size=12, color="#ff4444", visible=False)
        self.edit_tx_dialog = ft.AlertDialog(
            title=ft.Text("✏️ Transaction Edit करा"),
            content=ft.Container(
                content=ft.Column(
                    [self.edit_tx_amount, self.edit_tx_date, self.edit_tx_category,
                     self.edit_tx_notes, self.edit_tx_dialog_msg],
                    tight=True, spacing=10,
                ),
                width=380,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self.close_edit_tx_dialog),
                ft.ElevatedButton("Update करा", bgcolor="#00ffaa", color="black",
                                  on_click=self.handle_update_transaction),
            ],
        )

        # ---------------- Transfer Dialog ----------------
        self.transfer_from_id = None
        self.transfer_to_dropdown = ft.Dropdown(label="➡️ कोणत्या खात्यात पाठवायचं", height=52, **S)
        self.transfer_amount = ft.TextField(label="💰 Amount *", height=52, prefix=ft.Text("₹ "),
                                             keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.transfer_date = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=52, **S)
        self.transfer_notes = ft.TextField(label="📝 Notes", height=52, **S)
        self.transfer_dialog_msg = ft.Text("", size=12, color="#ff4444", visible=False)
        self.transfer_dialog = ft.AlertDialog(
            title=ft.Text("🔁 Transfer"),
            content=ft.Container(
                content=ft.Column(
                    [self.transfer_to_dropdown, self.transfer_amount, self.transfer_date,
                     self.transfer_notes, self.transfer_dialog_msg],
                    tight=True, spacing=10,
                ),
                width=380,
            ),
            actions=[ft.TextButton("Cancel", on_click=self.close_transfer_dialog),
                     ft.ElevatedButton("Transfer करा", bgcolor="#00ffaa", color="black",
                                       on_click=self.handle_save_transfer)],
        )

        # ---------------- Account Detail Dialog ----------------
        self.detail_body = ft.Column(spacing=10, scroll="auto")
        self.detail_dialog = ft.AlertDialog(
            title=ft.Text("Account"),
            content=ft.Container(content=self.detail_body, width=460, height=520),
            actions=[
                ft.TextButton("✏️ Edit", on_click=self._edit_from_detail),
                ft.TextButton("Close", on_click=self.close_detail_dialog),
            ],
        )

        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("💰 Finance / Accounts", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True),
                        add_btn,
                    ]
                ),
                ft.Container(
                    content=ft.Row(
                        [ft.Text("एकूण सर्व खात्यांची बेरीज (Grand Total)", size=13, color="#94a3b8"),
                         ft.Container(expand=True), self.grand_total_text],
                    ),
                    bgcolor="#161622", padding=16, border_radius=12,
                ),
                ft.Container(height=10),
                self.account_list,
            ],
            spacing=12,
            expand=True,
        )

    # ==================================================================
    def did_mount(self):
        for d in (self.add_edit_dialog, self.confirm_archive_dialog, self.tx_dialog,
                  self.transfer_dialog, self.detail_dialog, self.edit_tx_dialog):
            if d not in self.page.overlay:
                self.page.overlay.append(d)
        self.page.update()
        self.refresh()

    def refresh(self):
        if self.page is None:
            return
        self.account_list.controls.clear()
        data = get_all_account_balances()

        if not data["accounts"]:
            self.account_list.controls.append(
                ft.Text("अजून कोणतंही Account नाही. वरती '+ Add Account' दाबा.",
                        color="grey", italic=True))
        else:
            for acc in data["accounts"]:
                self.account_list.controls.append(self._account_card(acc))

        self.grand_total_text.value = f"₹{data['grand_total']:.0f}"
        self.grand_total_text.color = "#00ffaa" if data["grand_total"] >= 0 else "#ff4444"
        self.update()

    # ==================================================================
    def _account_card(self, acc):
        type_icon = {"Cash": "💵", "Bank": "🏦", "UPI": "📱", "Cheque": "🧾"}.get(acc["account_type"], "💰")
        bal_color = "#00ffaa" if acc["balance"] >= 0 else "#ff4444"

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(type_icon, size=20),
                        bgcolor="#12251e", width=44, height=44, border_radius=10,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(acc["name"], weight="bold", color="white", size=15),
                            ft.Text(acc["account_type"], size=11, color="#94a3b8"),
                        ], spacing=2, expand=True,
                    ),
                    ft.Text(f"₹{acc['balance']:.0f}", weight="bold", size=16, color=bal_color),
                    ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color="#64748b"),
                ],
                spacing=12,
            ),
            bgcolor="#161622", padding=14, border_radius=12, ink=True,
            on_click=lambda e, aid=acc["id"]: self.open_detail(aid),
        )

    # ==================================================================
    # Add / Edit Account
    # ==================================================================
    def open_add_edit_dialog(self, account_row):
        self.acc_dialog_msg.visible = False
        if account_row is None:
            self.editing_account_id = None
            self.add_edit_dialog.title = ft.Text("➕ नवीन Account")
            self.f_name.value = ""
            self.f_type.value = "Cash"
            self.f_opening.value = "0"
            self.f_opening.disabled = False
            self.f_notes.value = ""
            self.archive_account_btn.visible = False
            self.save_account_btn.text = "Save"
        else:
            self.editing_account_id = account_row["id"]
            self.add_edit_dialog.title = ft.Text(f"✏️ Edit: {account_row['name']}")
            self.f_name.value = account_row["name"] or ""
            self.f_type.value = account_row["account_type"] or "Cash"
            self.f_opening.value = "0"
            self.f_opening.disabled = True  # जुनं account असेल तर opening balance परत बदलता येत नाही
            self.f_notes.value = account_row["notes"] or ""
            self.archive_account_btn.visible = True
            self.save_account_btn.text = "Update"

        self.add_edit_dialog.open = True
        self.page.update()

    def close_add_edit_dialog(self, e):
        self.add_edit_dialog.open = False
        self.page.update()

    def handle_save_account(self, e):
        name = (self.f_name.value or "").strip()
        if not name:
            self.acc_dialog_msg.value = "⚠️ Account Name भरा."
            self.acc_dialog_msg.visible = True
            self.acc_dialog_msg.update()
            return

        try:
            opening = float(self.f_opening.value or 0) if not self.f_opening.disabled else 0
        except ValueError:
            self.acc_dialog_msg.value = "⚠️ Opening Balance फक्त नंबरमध्ये."
            self.acc_dialog_msg.visible = True
            self.acc_dialog_msg.update()
            return

        if self.editing_account_id:
            update_account(self.editing_account_id, name, self.f_type.value or "Cash",
                            (self.f_notes.value or "").strip())
        else:
            add_account(name, self.f_type.value or "Cash", opening, (self.f_notes.value or "").strip())

        self.add_edit_dialog.open = False
        self.page.update()
        self.refresh()

    def handle_archive_account(self, e):
        self.add_edit_dialog.open = False
        self.confirm_archive_dialog.open = True
        self.page.update()

    def _close_confirm_archive(self, e):
        self.confirm_archive_dialog.open = False
        self.page.update()

    def _confirm_archive_now(self, e):
        if self.editing_account_id:
            archive_account(self.editing_account_id)
        self.confirm_archive_dialog.open = False
        self.detail_dialog.open = False
        self.page.update()
        self.refresh()

    # ==================================================================
    # Account Detail — बॅलन्स + इतिहास + actions
    # ==================================================================
    def open_detail(self, account_id):
        account = get_account_by_id(account_id)
        if not account:
            return

        self.editing_account_id = account_id
        balance = get_account_balance(account_id)
        self.detail_dialog.title = ft.Text(account["name"])

        deposit_btn = ft.ElevatedButton(
            "💵 Deposit", bgcolor="#00ffaa", color="black", expand=True,
            on_click=lambda e: self._open_tx_dialog(account_id, "credit"),
        )
        withdraw_btn = ft.OutlinedButton(
            "💸 Withdraw", expand=True, style=ft.ButtonStyle(color="#ff8800"),
            on_click=lambda e: self._open_tx_dialog(account_id, "debit"),
        )
        transfer_btn = ft.OutlinedButton(
            "🔁 Transfer", expand=True, style=ft.ButtonStyle(color="#00aaff"),
            on_click=lambda e: self._open_transfer_dialog(account_id),
        )

        history = get_account_transactions(account_id, limit=100)
        history_list = ft.ListView(spacing=8, height=260)
        if not history:
            history_list.controls.append(
                ft.Text("अजून कोणताही व्यवहार नाही.", color="grey", italic=True, size=12))
        else:
            for tx in history:
                is_credit = tx["entry_type"] == "credit"
                icon = "🟢" if is_credit else "🔴"
                sign = "+" if is_credit else "-"
                color = "#00ffaa" if is_credit else "#ff4444"
                is_editable = not tx["reference_table"] and not tx["transfer_pair_id"]
                action_buttons = []
                if is_editable:
                    action_buttons.append(
                        ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, icon_size=16, icon_color="#00aaff",
                                      tooltip="Edit करा",
                                      on_click=lambda e, tid=tx["id"]: self._open_edit_tx_dialog(account_id, tid))
                    )
                action_buttons.append(
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color="#64748b",
                                  tooltip="डिलीट करा",
                                  on_click=lambda e, tid=tx["id"]: self._delete_tx(account_id, tid))
                )
                history_list.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(f"{icon} {tx['category'] or 'Manual'}", weight="bold", size=13, color="white"),
                                        ft.Text(f"{tx['tx_date'] or ''}  •  {tx['notes'] or ''}", size=11, color="#94a3b8"),
                                    ], spacing=2, expand=True,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(f"{sign}₹{tx['amount']:.0f}", weight="bold", color=color),
                                        ft.Row(action_buttons, spacing=0),
                                    ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=0,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        bgcolor="#161622", padding=10, border_radius=8,
                    )
                )

        self.detail_body.controls = [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("सध्याचा बॅलन्स", size=11, color="#94a3b8"),
                        ft.Text(f"₹{balance:.0f}", size=26, weight="bold",
                                color="#00ffaa" if balance >= 0 else "#ff4444"),
                    ], spacing=2,
                ),
                bgcolor="#12251e", padding=16, border_radius=12,
            ),
            ft.Row([deposit_btn, withdraw_btn, transfer_btn], spacing=8),
            ft.Container(height=6),
            ft.Text(f"अलीकडचे व्यवहार ({len(history)})", size=13, weight="bold", color="white"),
            history_list,
        ]

        self.detail_dialog.open = True
        self.page.update()

    def close_detail_dialog(self, e):
        self.detail_dialog.open = False
        self.page.update()

    def _edit_from_detail(self, e):
        account = get_account_by_id(self.editing_account_id)
        self.detail_dialog.open = False
        self.page.update()
        if account:
            self.open_add_edit_dialog(account)

    def _delete_tx(self, account_id, tx_id):
        delete_transaction(tx_id)
        self.open_detail(account_id)  # detail dialog refresh
        self.refresh()

    # ==================================================================
    # Edit Transaction — फक्त मॅन्युअल Deposit/Withdraw एन्ट्रीजसाठी
    # ==================================================================
    def _open_edit_tx_dialog(self, account_id, tx_id):
        tx = get_transaction_by_id(tx_id)
        if not tx:
            return
        self.edit_tx_id = tx_id
        self.edit_tx_account_id = account_id
        self.edit_tx_amount.value = str(tx["amount"] or 0)
        self.edit_tx_date.value = tx["tx_date"] or ""
        self.edit_tx_category.value = tx["category"] or ""
        self.edit_tx_notes.value = tx["notes"] or ""
        self.edit_tx_dialog_msg.visible = False
        self.edit_tx_dialog.open = True
        self.page.update()

    def close_edit_tx_dialog(self, e):
        self.edit_tx_dialog.open = False
        self.page.update()

    def handle_update_transaction(self, e):
        try:
            amount = float(self.edit_tx_amount.value or 0)
        except ValueError:
            amount = 0

        try:
            update_transaction(
                self.edit_tx_id,
                amount=amount,
                category=(self.edit_tx_category.value or "").strip(),
                tx_date=(self.edit_tx_date.value or "").strip(),
                notes=(self.edit_tx_notes.value or "").strip(),
            )
        except ValueError as ex:
            self.edit_tx_dialog_msg.value = f"⚠️ {ex}"
            self.edit_tx_dialog_msg.visible = True
            self.edit_tx_dialog_msg.update()
            return

        self.edit_tx_dialog.open = False
        self.page.update()
        self.open_detail(self.edit_tx_account_id)  # detail dialog + बॅलन्स refresh
        self.refresh()

    # ==================================================================
    # Deposit / Withdraw Dialog
    # ==================================================================
    def _open_tx_dialog(self, account_id, mode):
        self.tx_account_id = account_id
        self.tx_mode = mode
        self.tx_dialog.title = ft.Text("💵 Deposit" if mode == "credit" else "💸 Withdraw")
        self.tx_amount.value = ""
        self.tx_date.value = ""
        self.tx_category.value = "Manual Deposit" if mode == "credit" else "Manual Withdrawal"
        self.tx_notes.value = ""
        self.tx_dialog_msg.visible = False
        self.tx_dialog.open = True
        self.page.update()

    def close_tx_dialog(self, e):
        self.tx_dialog.open = False
        self.page.update()

    def handle_save_transaction(self, e):
        try:
            amount = float(self.tx_amount.value or 0)
        except ValueError:
            amount = 0
        if amount <= 0:
            self.tx_dialog_msg.value = "⚠️ Amount शून्यापेक्षा जास्त असावी."
            self.tx_dialog_msg.visible = True
            self.tx_dialog_msg.update()
            return

        try:
            add_transaction(
                self.tx_account_id, self.tx_mode, amount,
                category=(self.tx_category.value or "Manual").strip(),
                tx_date=(self.tx_date.value or "").strip(),
                notes=(self.tx_notes.value or "").strip(),
            )
        except ValueError as ex:
            self.tx_dialog_msg.value = f"⚠️ {ex}"
            self.tx_dialog_msg.visible = True
            self.tx_dialog_msg.update()
            return

        self.tx_dialog.open = False
        self.page.update()
        self.open_detail(self.tx_account_id)
        self.refresh()

    # ==================================================================
    # Transfer Dialog
    # ==================================================================
    def _open_transfer_dialog(self, account_id):
        self.transfer_from_id = account_id
        others = [a for a in get_accounts() if a["id"] != account_id]
        self.transfer_to_dropdown.options = [
            ft.dropdown.Option(key=str(a["id"]), text=a["name"]) for a in others
        ]
        self.transfer_to_dropdown.value = None
        self.transfer_amount.value = ""
        self.transfer_date.value = ""
        self.transfer_notes.value = ""
        self.transfer_dialog_msg.visible = False
        self.transfer_dialog.open = True
        self.page.update()

    def close_transfer_dialog(self, e):
        self.transfer_dialog.open = False
        self.page.update()

    def handle_save_transfer(self, e):
        if not self.transfer_to_dropdown.value:
            self.transfer_dialog_msg.value = "⚠️ कोणत्या खात्यात पाठवायचं ते निवडा."
            self.transfer_dialog_msg.visible = True
            self.transfer_dialog_msg.update()
            return

        try:
            amount = float(self.transfer_amount.value or 0)
        except ValueError:
            amount = 0

        try:
            record_transfer(
                self.transfer_from_id, int(self.transfer_to_dropdown.value), amount,
                tx_date=(self.transfer_date.value or "").strip(),
                notes=(self.transfer_notes.value or "").strip(),
            )
        except ValueError as ex:
            self.transfer_dialog_msg.value = f"⚠️ {ex}"
            self.transfer_dialog_msg.visible = True
            self.transfer_dialog_msg.update()
            return

        self.transfer_dialog.open = False
        self.page.update()
        self.open_detail(self.transfer_from_id)
        self.refresh()
