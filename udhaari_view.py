import flet as ft
from database import (
    add_udhaari, update_udhaari, delete_udhaari, get_by_id,
    get_history_by_name, export_to_excel, get_due_customers,
    get_clients, add_client,
    search_parts, get_part_by_id, get_part_stock,
    add_part_usage, get_part_usage_by_reference, clear_part_usage_for_reference,
)
from invoice import generate_invoice
from customer_lookup import smart_customer_lookup, auto_capitalize_words
import os
import urllib.parse


def _get_output_dir():
    """Desktop वर 'Downloads' फोल्डर वापरतो; तो नसेल किंवा access नसेल (उदा. Android)
    तर app च्या स्वतःच्या फोल्डरमध्ये 'exports' नावाचा फोल्डर बनवून वापरतो —
    त्यामुळे Mobile APK वरही Export/Print Bill क्रॅश न होता काम करतं."""
    try:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads, exist_ok=True)
        return downloads
    except Exception:
        fallback = os.path.join(os.getcwd(), "exports")
        os.makedirs(fallback, exist_ok=True)
        return fallback


class UdhaariView(ft.Row):
    """उधारी एंट्री / एडिट फॉर्म.
    - नवीन नोंद सेव्ह केल्यावर, अपडेट केल्यावर किंवा डिलीट केल्यावर refresh_callback() कॉल होतं.
    - load_record(id) कॉल केलं की त्या id ची नोंद फॉर्ममध्ये भरून एडिट-मोडमध्ये जातं.
    - कस्टमरच्या नावावर क्लिक केलं की त्याची संपूर्ण history (popup) दाखवते."""

    def __init__(self, refresh_callback=None):
        super().__init__(expand=True)

        self.refresh_callback = refresh_callback
        self.editing_id = None  # None = नवीन नोंद, अन्यथा त्या id ची नोंद एडिट होतेय

        input_style = {
            "border_color": "#00ffaa",
            "focused_border_color": "#00ffaa",
            "border_radius": 8,
        }

        # --- Garage/Client Group निवडण्यासाठी dropdown (optional) ---
        self.client_dropdown = ft.Dropdown(
            label="🏢 Garage / Client (optional)",
            height=55, expand=True,
            **input_style
        )
        self.quick_add_client_btn = ft.IconButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINE, icon_color="#00ffaa",
            tooltip="नवीन Client पटकन जोडा",
            on_click=self._open_quick_add_client,
        )

        # --- Quick-add client mini dialog ---
        self.qc_garage = ft.TextField(label="🏢 Garage Name *", height=52, **input_style)
        self.qc_owner = ft.TextField(label="👤 Owner Name", height=52, **input_style)
        self.qc_mobile = ft.TextField(label="📱 Mobile", height=52, **input_style)
        self.qc_location = ft.TextField(label="📍 Location", height=52, **input_style)
        self.qc_msg = ft.Text("", size=12, color="#ff4444", visible=False)
        self.quick_add_dialog = ft.AlertDialog(
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

        # --- फॉर्म फील्ड्स ---
        self.name = ft.TextField(label="👤 Customer Name *", height=55, on_blur=self._maybe_show_history, **input_style)
        self.mobile = ft.TextField(label="📱 Phone Number", height=55, **input_style)
        self.car_name = ft.TextField(label="🚗 Vehicle", height=55, **input_style)
        self.car_no = ft.TextField(label="🔢 Vehicle Number", height=55, **input_style)
        self.address = ft.TextField(label="📍 Address", height=55, **input_style)

        # टीप: नाव टाईप करताना auto-capitalize, आणि मोबाईल/गाडी नंबरवर फोकस
        # सोडला की जुना ग्राहक असेल तर बाकी माहिती आपोआप भरते (नवीन नोंद
        # असतानाच — जुनी नोंद एडिट करत असताना डेटा बदलत नाही).
        self.name.on_change = lambda e: self._auto_cap(self.name)
        self.mobile.on_blur = self._lookup_by_mobile
        self.car_no.on_blur = self._lookup_by_vehicle_no

        self.date = ft.TextField(label="📅 Trans. Date", height=55, **input_style)
        self.due_date = ft.TextField(label="📅 Due Date", height=55, **input_style)
        self.total_amt = ft.TextField(
            label="📊 Total Amount *", height=55, prefix=ft.Text("₹ "),
            keyboard_type=ft.KeyboardType.NUMBER, **input_style
        )
        self.paid_amt = ft.TextField(
            label="✅ Paid Amount", height=55, prefix=ft.Text("₹ "),
            keyboard_type=ft.KeyboardType.NUMBER, value="0", **input_style
        )
        self.due_amt = ft.TextField(
            label="⏳ Due Amount", height=55, prefix=ft.Text("₹ "),
            read_only=True, **input_style
        )
        self.notes = ft.TextField(label="📝 Notes", multiline=True, height=120, **input_style)

        # ---------------- 🔩 Parts Used — collapsible section ----------------
        # टीप: हे पूर्णपणे optional आहे — काही Parts न वापरता (फक्त Labour/Service)
        # Udhaari नोंद करता येईलच. Parts जोडले तरच स्टॉक (db_inventory ledger)
        # आपोआप वजा होतो आणि Profit ट्रॅक होतो — billing_view.py सारखाच पॅटर्न,
        # पण इथे तो पूर्णपणे ऐच्छिक (collapsed by default) ठेवलाय जेणेकरून जुनी
        # साधी Udhaari नोंद अजूनही तितक्याच पटकन होईल.
        self.cart = []  # प्रत्येक item: dict(part_id, product_name, part_number,
                        #                      qty, buying_rate, sell_rate,
                        #                      discount_percent, net_amount)

        self.part_dropdown = ft.Dropdown(label="🔩 Part निवडा", height=52, expand=True, **input_style)
        self.part_qty = ft.TextField(label="Qty", height=52, width=80, value="1",
                                      keyboard_type=ft.KeyboardType.NUMBER, **input_style)
        self.part_discount = ft.TextField(label="Disc %", height=52, width=80, value="0",
                                           keyboard_type=ft.KeyboardType.NUMBER, **input_style)
        self.add_part_btn = ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="#00ffaa",
                                           icon_size=30, tooltip="Cart मध्ये जोडा",
                                           on_click=self.handle_add_part)
        self.parts_cart_list = ft.ListView(spacing=6, height=140)
        self.parts_total_text = ft.Text("₹0", size=14, weight="bold", color="#00ffaa")

        self.parts_section_body = ft.Column(
            [
                ft.Row([self.part_dropdown, self.part_qty, self.part_discount, self.add_part_btn], spacing=8),
                self.parts_cart_list,
                ft.Row([ft.Text("Parts Total:", size=13, color="#94a3b8"),
                        ft.Container(expand=True), self.parts_total_text]),
            ],
            visible=False, spacing=8,
        )
        self.parts_toggle_icon = ft.Icon(ft.Icons.EXPAND_MORE, color="#00ffaa")
        self.parts_section_header = ft.Container(
            content=ft.Row(
                [
                    ft.Text("🔩 Parts Used (optional — वापरलेले पार्ट्स)", size=14, weight="bold", color="white"),
                    ft.Container(expand=True),
                    self.parts_toggle_icon,
                ]
            ),
            padding=ft.Padding.symmetric(vertical=8), ink=True,
            on_click=self._toggle_parts_section,
        )

        self.status_text = ft.Text("", size=13, visible=False)
        self.form_title = ft.Text("Customer Details", size=22, weight="bold", color="#00ffaa")

        self.type_dropdown = ft.Dropdown(
            label="🔄 Type",
            height=55,
            value="Given",
            options=[
                ft.dropdown.Option("Given", "दिलेले (Given)"),
                ft.dropdown.Option("Taken", "घेतलेले (Taken)"),
            ],
            **input_style
        )

        self.total_amt.on_change = self.recalc_due
        self.paid_amt.on_change = self.recalc_due

        # --- History पॉपअप (कस्टमरच्या जुन्या नोंदी दाखवण्यासाठी) ---
        self.history_list = ft.ListView(spacing=8, height=300)
        self.history_dialog = ft.AlertDialog(
            title=ft.Text("Customer History"),
            content=ft.Container(content=self.history_list, width=420),
            actions=[ft.TextButton("Close", on_click=self._close_history)],
        )

        # --- WhatsApp Reminder पॉपअप ---
        self.reminder_list = ft.ListView(spacing=8, height=350)
        self.reminder_dialog = ft.AlertDialog(
            title=ft.Text("💬 Due Customers — Reminder पाठवा"),
            content=ft.Container(content=self.reminder_list, width=440),
            actions=[ft.TextButton("Close", on_click=self._close_reminder_dialog)],
        )

        # --- Delete confirm dialog ---
        self.delete_dialog = ft.AlertDialog(
            title=ft.Text("नोंद डिलीट करायची?"),
            content=ft.Text("ही कृती परत होणार नाही. खात्री आहे का?"),
            actions=[
                ft.TextButton("नाही", on_click=self._close_delete_dialog),
                ft.TextButton("हो, डिलीट करा", on_click=self._confirm_delete,
                              style=ft.ButtonStyle(color="#ff4444")),
            ],
        )

        # --- बटण्स ---
        self.save_btn = ft.ElevatedButton(
            "Save", bgcolor="#00ffaa", color="black", height=50, expand=True,
            on_click=self.save_udhaari,
        )
        self.delete_btn = ft.OutlinedButton(
            "Delete", height=50, width=110, visible=False,
            style=ft.ButtonStyle(color="#ff4444"),
            on_click=self._open_delete_dialog,
        )
        self.export_btn = ft.OutlinedButton(
            "📊 Export Excel", height=50,
            on_click=self.handle_export,
        )
        self.reminder_btn = ft.OutlinedButton(
            "💬 WhatsApp Reminders", height=50,
            style=ft.ButtonStyle(color="#00ffaa"),
            on_click=self.handle_open_reminders,
        )
        self.paper_size = ft.Dropdown(
            label="Size", height=50, width=110, value="A5",
            options=[ft.dropdown.Option("A5", "A5"), ft.dropdown.Option("A4", "A4")],
            border_color="#00ffaa", focused_border_color="#00ffaa", border_radius=8,
            visible=False,
        )
        self.print_bill_btn = ft.OutlinedButton(
            "🖨️ Print Bill", height=50, visible=False,
            style=ft.ButtonStyle(color="#00ffaa"),
            on_click=self.handle_print_bill,
        )

        self.right_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row([self.form_title, ft.Container(expand=True), self.paper_size, self.print_bill_btn, self.reminder_btn, self.export_btn]),
                    self.status_text,
                    ft.Row([self.client_dropdown, self.quick_add_client_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([self.name, self.mobile]),
                    ft.Row([self.car_name, self.car_no]),
                    self.address,
                    ft.Text("Transaction Details", size=22, weight="bold", color="#00ffaa"),
                    ft.Row([self.date, self.due_date]),
                    ft.Row([self.total_amt, self.type_dropdown]),
                    ft.Row([self.paid_amt, self.due_amt]),
                    ft.Divider(color="#1a1a26"),
                    self.parts_section_header,
                    self.parts_section_body,
                    ft.Divider(color="#1a1a26"),
                    self.notes,
                    ft.Row(
                        [
                            ft.OutlinedButton("Cancel", height=50, width=110, on_click=self.clear_form),
                            self.delete_btn,
                            self.save_btn,
                        ]
                    ),
                ],
                scroll="auto",
            ),
            padding=20,
            expand=True,
        )

        self.controls = [self.right_panel]

    # ==================================================================
    # लाईफसायकल हुक — डायलॉग्स page वर add करण्यासाठी
    # ==================================================================
    def did_mount(self):
        if self.history_dialog not in self.page.overlay:
            self.page.overlay.append(self.history_dialog)
        if self.delete_dialog not in self.page.overlay:
            self.page.overlay.append(self.delete_dialog)
        if self.reminder_dialog not in self.page.overlay:
            self.page.overlay.append(self.reminder_dialog)
        if self.quick_add_dialog not in self.page.overlay:
            self.page.overlay.append(self.quick_add_dialog)
        self._load_client_options()
        self._load_part_options()
        self.page.update()

    # ==================================================================
    # 🔩 Parts Used — collapsible section, cart add/remove, save-time logic
    # ==================================================================
    def _load_part_options(self):
        parts = search_parts(None)
        opts = []
        for p in parts:
            stock = get_part_stock(p["id"])
            opts.append(ft.dropdown.Option(
                key=str(p["id"]),
                text=f"{p['product_name']}  (Stock: {stock:.0f}, ₹{p['sell_rate']:.0f})",
            ))
        self.part_dropdown.options = opts
        if self.page:
            self.part_dropdown.update()

    def _toggle_parts_section(self, e):
        self.parts_section_body.visible = not self.parts_section_body.visible
        self.parts_toggle_icon.name = (
            ft.Icons.EXPAND_LESS if self.parts_section_body.visible else ft.Icons.EXPAND_MORE
        )
        self.update()

    def handle_add_part(self, e):
        if not self.part_dropdown.value:
            self.show_status("⚠️ आधी एक Part निवडा.", "#ff4444")
            return
        try:
            qty = float(self.part_qty.value or 0)
            discount = float(self.part_discount.value or 0)
        except ValueError:
            self.show_status("⚠️ Qty/Discount फक्त नंबरमध्ये.", "#ff4444")
            return
        if qty <= 0:
            self.show_status("⚠️ Qty शून्यापेक्षा जास्त असावी.", "#ff4444")
            return

        part = get_part_by_id(int(self.part_dropdown.value))
        if not part:
            return

        gross = qty * (part["sell_rate"] or 0)
        net_amount = gross - (gross * discount / 100)

        self.cart.append({
            "part_id": part["id"],
            "product_name": part["product_name"],
            "part_number": part["part_number"] or "",
            "qty": qty,
            "buying_rate": part["buying_rate"] or 0,
            "sell_rate": part["sell_rate"] or 0,
            "discount_percent": discount,
            "net_amount": net_amount,
        })
        self._refresh_parts_cart_ui()

        self.part_qty.value = "1"
        self.part_discount.value = "0"
        self.status_text.visible = False
        self.page.update()

    def _remove_from_cart(self, index):
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
            self._refresh_parts_cart_ui()
            self.page.update()

    def _refresh_parts_cart_ui(self):
        self.parts_cart_list.controls.clear()
        for i, item in enumerate(self.cart):
            self.parts_cart_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(item["product_name"], size=12, weight="bold", color="white"),
                                    ft.Text(f"{item['qty']:.0f} x ₹{item['sell_rate']:.0f}"
                                            f"  (-{item['discount_percent']:.0f}%)",
                                            size=11, color="#94a3b8"),
                                ], spacing=1, expand=True,
                            ),
                            ft.Text(f"₹{item['net_amount']:.0f}", size=13, weight="bold", color="#00ffaa"),
                            ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, icon_color="#ff4444",
                                          on_click=lambda e, idx=i: self._remove_from_cart(idx)),
                        ],
                    ),
                    bgcolor="#161622", padding=8, border_radius=8,
                )
            )
        self.parts_total_text.value = f"₹{sum(item['net_amount'] for item in self.cart):.0f}"
        if self.page:
            self.update()

    # ==================================================================
    # Client Dropdown — options लोड करणे व quick-add
    # ==================================================================
    def _load_client_options(self, select_id=None):
        clients = get_clients()
        self.client_dropdown.options = [
            ft.dropdown.Option(key=str(row["id"]), text=row["garage_name"]) for row in clients
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
        self.quick_add_dialog.open = True
        self.page.update()

    def _close_quick_add_client(self, e):
        self.quick_add_dialog.open = False
        self.page.update()

    def _save_quick_add_client(self, e):
        garage = (self.qc_garage.value or "").strip()
        if not garage:
            self.qc_msg.value = "⚠️ Garage Name भरा."
            self.qc_msg.visible = True
            self.qc_msg.update()
            return

        new_id = add_client(
            garage_name=garage,
            owner_name=(self.qc_owner.value or "").strip(),
            mobile=(self.qc_mobile.value or "").strip(),
            location=(self.qc_location.value or "").strip(),
        )
        self.quick_add_dialog.open = False
        self._load_client_options(select_id=new_id)
        self.page.update()

    # ==================================================================
    # Due amount = Total - Paid
    # ==================================================================
    def recalc_due(self, e):
        try:
            total = float(self.total_amt.value or 0)
            paid = float(self.paid_amt.value or 0)
            due = max(total - paid, 0)
            self.due_amt.value = f"{due:.2f}"
        except ValueError:
            self.due_amt.value = ""
        self.due_amt.update()

    def show_status(self, message, color):
        self.status_text.value = message
        self.status_text.color = color
        self.status_text.visible = True
        self.status_text.update()

    # ==================================================================
    # नाव/मोबाईल/गाडी नंबरवरून जुना ग्राहक ओळखून बाकी माहिती आपोआप भरणे
    # ==================================================================
    def _maybe_show_history(self, e):
        name = (self.name.value or "").strip()
        if not name or self.editing_id is not None:
            return
        records = get_history_by_name(name)
        if records:
            self._autofill_from_row(records[0])  # आधी बाकी फील्ड्स आपोआप भर
            self._populate_history(name, records)
            self.history_dialog.open = True
            self.page.update()

    def _autofill_from_row(self, row):
        """नाव/मोबाईल/गाडी नंबर मधलं जे मिळालं त्यावरून, रिकाम्या फील्ड्स
        आपोआप भरतो — आधीच काही टाईप केलेलं असेल तर ओव्हरराईट करत नाही."""
        if not row:
            return
        if not (self.mobile.value or "").strip() and row["mobile"]:
            self.mobile.value = row["mobile"]
        if not (self.car_name.value or "").strip() and row["vehicle"]:
            self.car_name.value = row["vehicle"]
        if not (self.car_no.value or "").strip() and row["vehicle_no"]:
            self.car_no.value = row["vehicle_no"]
        if not (self.address.value or "").strip() and "address" in row.keys() and row["address"]:
            self.address.value = row["address"]
        if not (self.name.value or "").strip() and row["name"]:
            self.name.value = row["name"]
        if "client_id" in row.keys() and row["client_id"]:
            self._load_client_options(select_id=row["client_id"])
        if self.page:
            self.update()

    def _lookup_by_mobile(self, e):
        if self.editing_id is not None:
            return
        row = smart_customer_lookup(self.mobile.value)
        if row:
            self._autofill_from_row(row)
            self.show_status("ℹ️ जुना ग्राहक सापडला — माहिती आपोआप भरली.", "#00aaff")

    def _lookup_by_vehicle_no(self, e):
        if self.editing_id is not None:
            return
        row = smart_customer_lookup(self.car_no.value)
        if row:
            self._autofill_from_row(row)
            self.show_status("ℹ️ या गाडीची जुनी नोंद सापडली — माहिती आपोआप भरली.", "#00aaff")

    def _auto_cap(self, field):
        """नाव टाईप करताना स्पेस देऊन नवीन शब्द सुरू केला की त्याचं पहिलं
        अक्षर आपोआप Capital होतं (उरलेलं जसंच्या तसं राहतं)."""
        value = field.value or ""
        capitalized = auto_capitalize_words(value)
        if capitalized != value:
            field.value = capitalized
            if self.page:
                field.update()

    def _populate_history(self, name, records):
        self.history_list.controls.clear()
        self.history_dialog.title = ft.Text(f"{name} — मागील नोंदी ({len(records)})")
        total_due = sum((r["due_amt"] or 0) for r in records)

        self.history_list.controls.append(
            ft.Container(
                content=ft.Text(f"एकूण थकीत: ₹{total_due:.0f}", weight="bold", color="#ff8800"),
                padding=8,
            )
        )

        for r in records:
            icon = "📤" if (r["type"] or "Given") == "Given" else "📥"
            self.history_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(f"{icon} ₹{r['total_amt']:.0f} — {r['tx_date'] or ''}", weight="bold"),
                            ft.Text(f"Paid ₹{r['paid_amt']:.0f}  |  Due ₹{r['due_amt']:.0f}", size=12, color="#94a3b8"),
                            ft.Text(r["notes"] or "", size=11, italic=True, color="#64748b"),
                        ],
                        spacing=2,
                    ),
                    bgcolor="#161622",
                    padding=10,
                    border_radius=8,
                    on_click=lambda e, rid=r["id"]: self._edit_from_history(rid),
                    ink=True,
                )
            )

    def _edit_from_history(self, record_id):
        self._close_history(None)
        self.load_record(record_id)

    def _close_history(self, e):
        self.history_dialog.open = False
        self.page.update()

    # ==================================================================
    # विद्यमान रेकॉर्ड लोड करून फॉर्म एडिट-मोडमध्ये टाकणे
    # ==================================================================
    def load_record(self, record_id):
        row = get_by_id(record_id)
        if not row:
            self.show_status("⚠️ ती नोंद सापडली नाही.", "#ff4444")
            return

        self.editing_id = record_id
        self._load_client_options(select_id=row["client_id"] if "client_id" in row.keys() and row["client_id"] else None)
        self.name.value = row["name"] or ""
        self.mobile.value = row["mobile"] or ""
        self.car_name.value = row["vehicle"] or ""
        self.car_no.value = row["vehicle_no"] or ""
        self.address.value = row["address"] or ""
        self.date.value = row["tx_date"] or ""
        self.due_date.value = row["due_date"] or ""
        self.total_amt.value = str(row["total_amt"] or 0)
        self.paid_amt.value = str(row["paid_amt"] or 0)
        self.due_amt.value = str(row["due_amt"] or 0)
        self.notes.value = row["notes"] or ""
        self.type_dropdown.value = row["type"] or "Given"

        # आधी वापरलेले Parts (असल्यास) cart मध्ये परत भरतो — जेणेकरून Edit
        # करताना काय-काय parts आधीच जोडलेले होते ते दिसेल आणि हवं तर बदलता येईल
        self.cart = []
        existing_usage = get_part_usage_by_reference("udhaari", record_id)
        for u in existing_usage:
            self.cart.append({
                "part_id": u["part_id"],
                "product_name": u["product_name"],
                "part_number": u["part_number"] or "",
                "qty": u["qty"] or 0,
                "buying_rate": u["buying_rate"] or 0,
                "sell_rate": u["sell_rate"] or 0,
                "discount_percent": u["discount_percent"] or 0,
                "net_amount": u["net_amount"] or 0,
            })
        self._refresh_parts_cart_ui()
        self.parts_section_body.visible = bool(self.cart)
        self.parts_toggle_icon.name = (
            ft.Icons.EXPAND_LESS if self.parts_section_body.visible else ft.Icons.EXPAND_MORE
        )

        self.form_title.value = f"Edit: {row['name']}"
        self.save_btn.text = "Update"
        self.delete_btn.visible = True
        self.print_bill_btn.visible = True
        self.paper_size.visible = True
        self.status_text.visible = False

        if self.page:
            self.update()

    # ==================================================================
    # Save / Update
    # ==================================================================
    def save_udhaari(self, e):
        name = (self.name.value or "").strip()
        total_amt_raw = (self.total_amt.value or "").strip()

        if not name:
            self.show_status("⚠️ कृपया Customer Name भरा.", "#ff4444")
            return
        if not total_amt_raw:
            self.show_status("⚠️ कृपया Total Amount भरा.", "#ff4444")
            return

        try:
            total_amt = float(total_amt_raw)
        except ValueError:
            self.show_status("⚠️ Total Amount फक्त नंबरमध्ये असावी.", "#ff4444")
            return

        if total_amt <= 0:
            self.show_status("⚠️ Total Amount शून्यापेक्षा जास्त असावी.", "#ff4444")
            return

        try:
            paid_amt = float(self.paid_amt.value) if self.paid_amt.value else 0.0
        except ValueError:
            self.show_status("⚠️ Paid Amount फक्त नंबरमध्ये असावी.", "#ff4444")
            return

        due_amt = max(total_amt - paid_amt, 0)

        client_id = int(self.client_dropdown.value) if self.client_dropdown.value else None

        kwargs = dict(
            name=name,
            client_id=client_id,
            mobile=(self.mobile.value or "").strip(),
            vehicle=(self.car_name.value or "").strip(),
            vehicle_no=(self.car_no.value or "").strip(),
            address=(self.address.value or "").strip(),
            tx_date=(self.date.value or "").strip(),
            due_date=(self.due_date.value or "").strip(),
            total_amt=total_amt,
            paid_amt=paid_amt,
            due_amt=due_amt,
            notes=(self.notes.value or "").strip(),
            type=self.type_dropdown.value or "Given",
        )

        try:
            if self.editing_id is not None:
                update_udhaari(self.editing_id, **kwargs)
                record_id = self.editing_id
                # जुने parts-line-items आधी पूर्णपणे मागे घे (स्टॉक परत जमा),
                # मग cart मधले सध्याचे parts नव्याने टाक — यामुळे Parts कितीही
                # वेळा जोडले/काढले तरी स्टॉक/profit कधीही चुकीचा राहत नाही.
                clear_part_usage_for_reference("udhaari", record_id)
                for item in self.cart:
                    add_part_usage(
                        reference_table="udhaari", reference_id=record_id,
                        part_id=item["part_id"], product_name=item["product_name"],
                        part_number=item["part_number"], qty=item["qty"],
                        buying_rate=item["buying_rate"], sell_rate=item["sell_rate"],
                        discount_percent=item["discount_percent"],
                        tx_date=kwargs["tx_date"], notes="Udhaari",
                    )
                self.show_status("✅ नोंद यशस्वीरित्या अपडेट झाली.", "#00ffaa")
            else:
                record_id = add_udhaari(**kwargs)
                for item in self.cart:
                    add_part_usage(
                        reference_table="udhaari", reference_id=record_id,
                        part_id=item["part_id"], product_name=item["product_name"],
                        part_number=item["part_number"], qty=item["qty"],
                        buying_rate=item["buying_rate"], sell_rate=item["sell_rate"],
                        discount_percent=item["discount_percent"],
                        tx_date=kwargs["tx_date"], notes="Udhaari",
                    )
                self.show_status("✅ नोंद यशस्वीरित्या सेव्ह झाली.", "#00ffaa")
        except Exception as ex:
            self.show_status(f"❌ सेव्ह करताना एरर आली: {ex}", "#ff4444")
            return

        if self.refresh_callback:
            self.refresh_callback()

        self.clear_form(e)

    # ==================================================================
    # Delete
    # ==================================================================
    def _open_delete_dialog(self, e):
        if self.editing_id is None:
            return
        self.delete_dialog.open = True
        self.page.update()

    def _close_delete_dialog(self, e):
        self.delete_dialog.open = False
        self.page.update()

    def _confirm_delete(self, e):
        if self.editing_id is not None:
            try:
                clear_part_usage_for_reference("udhaari", self.editing_id)  # स्टॉक परत जमा
                delete_udhaari(self.editing_id)
                self.show_status("🗑️ नोंद डिलीट झाली.", "#ff8800")
            except Exception as ex:
                self.show_status(f"❌ डिलीट करताना एरर: {ex}", "#ff4444")

        self.delete_dialog.open = False
        self.page.update()

        if self.refresh_callback:
            self.refresh_callback()

        self.clear_form(e)

    # ==================================================================
    # Excel Export
    # ==================================================================
    def handle_export(self, e):
        try:
            downloads_dir = _get_output_dir()
            filepath = os.path.join(downloads_dir, "udhaari_export.xlsx")
            export_to_excel(filepath)
            self.show_status(f"📊 Excel सेव्ह झालं: {filepath}", "#00ffaa")
        except Exception as ex:
            self.show_status(f"❌ Export मध्ये एरर: {ex}", "#ff4444")

    # ==================================================================
    # Print Bill — सध्या एडिट होत असलेल्या नोंदीचं PDF इनव्हॉइस बनवणं
    # ==================================================================
    def handle_print_bill(self, e):
        if self.editing_id is None:
            return
        row = get_by_id(self.editing_id)
        if not row:
            self.show_status("⚠️ ती नोंद सापडली नाही.", "#ff4444")
            return

        try:
            downloads_dir = _get_output_dir()
            safe_name = "".join(ch if ch.isalnum() else "_" for ch in (row["name"] or "customer"))
            filepath = os.path.join(downloads_dir, f"Bill_{safe_name}_{row['id']}.pdf")
            generate_invoice(row, filepath, page_size=self.paper_size.value or "A5")
            self.show_status(f"🖨️ Bill तयार झालं: {filepath}", "#00ffaa")
        except Exception as ex:
            self.show_status(f"❌ Bill बनवताना एरर: {ex}", "#ff4444")

    # ==================================================================
    # WhatsApp Reminder — Due असलेल्या सर्व कस्टमरना एका क्लिकवर मेसेज
    # ==================================================================
    def handle_open_reminders(self, e):
        due_customers = get_due_customers()
        self.reminder_list.controls.clear()

        if not due_customers:
            self.reminder_list.controls.append(
                ft.Text("🎉 सध्या कोणाकडेही due नाही!", color="#00ffaa", italic=True)
            )
        else:
            for cust in due_customers:
                self.reminder_list.controls.append(self._build_reminder_row(cust))

        self.reminder_dialog.open = True
        self.page.update()

    def _build_reminder_row(self, cust):
        name = cust["name"]
        mobile = (cust["mobile"] or "").strip()
        due = cust["total_due"] or 0

        has_mobile = bool(mobile)

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(name, weight="bold", color="white"),
                            ft.Text(
                                f"Due ₹{due:.0f}" + ("" if has_mobile else "  (फोन नंबर नाही)"),
                                size=12,
                                color="#ff8800" if has_mobile else "#ff4444",
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.ElevatedButton(
                        "💬 Remind",
                        bgcolor="#00ffaa", color="black",
                        disabled=not has_mobile,
                        on_click=lambda e, n=name, m=mobile, d=due: self._send_whatsapp_reminder(n, m, d),
                    ),
                ]
            ),
            bgcolor="#161622",
            padding=10,
            border_radius=8,
        )

    def _send_whatsapp_reminder(self, name, mobile, due_amt):
        # भारतीय नंबर असेल आणि देश-कोड नसेल तर 91 जोडतो (WhatsApp ला तो हवा असतो)
        digits = "".join(ch for ch in mobile if ch.isdigit())
        if len(digits) == 10:
            digits = "91" + digits

        message = (
            f"नमस्कार {name}, आपली ₹{due_amt:.0f} रक्कम बाकी आहे. "
            f"कृपया लवकरात लवकर पूर्ण करा. धन्यवाद! — Bhagwati Garage"
        )
        encoded_message = urllib.parse.quote(message)
        url = f"https://wa.me/{digits}?text={encoded_message}"

        try:
            self.page.launch_url(url)
        except Exception as ex:
            self.show_status(f"❌ WhatsApp उघडताना एरर: {ex}", "#ff4444")

    def _close_reminder_dialog(self, e):
        self.reminder_dialog.open = False
        self.page.update()

    # ==================================================================
    # फॉर्म रिकामं करून नवीन-नोंद मोडवर परत येणे
    # ==================================================================
    def clear_form(self, e):
        for field in (
            self.name, self.mobile, self.car_name, self.car_no,
            self.address, self.date, self.due_date,
            self.total_amt, self.notes,
        ):
            field.value = ""
        self.paid_amt.value = "0"
        self.due_amt.value = ""
        self.type_dropdown.value = "Given"
        self.client_dropdown.value = None

        self.cart = []
        self._refresh_parts_cart_ui()
        self.parts_section_body.visible = False
        self.parts_toggle_icon.name = ft.Icons.EXPAND_MORE
        self._load_part_options()  # ताजा stock दाखवण्यासाठी

        self.editing_id = None
        self.form_title.value = "Customer Details"
        self.save_btn.text = "Save"
        self.delete_btn.visible = False
        self.print_bill_btn.visible = False
        self.paper_size.visible = False

        if self.page:
            self.update()
