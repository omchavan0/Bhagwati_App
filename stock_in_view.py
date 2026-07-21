"""
============================================================================
STOCK IN VIEW — Part टाईप करताच Live Suggestions + Master मधून Auto-Fetch
+ Reverse-GST गणित
============================================================================
जुना ft.Dropdown काढून टाकलाय — त्यात टाईप करता येत नव्हतं, त्यामुळे on_change
कधी fire होत नव्हता आणि Part निवडूनही selected_part रिकामाच राहत होता (Save
वर "आधी Part निवडा" एरर याच कारणामुळे येत होती).

आता TextField + खाली live-filtered suggestions list — टाईप करताच जुळणारे
Parts दिसतात, त्यातल्या एकावर क्लिक केलं की तोच selected_part म्हणून पक्का
सेट होतो (guaranteed) आणि Description/HSN/GST%/Location cलगेच autofill होतात.

Discount% <-> Buy Rate दोन्ही बाजूने काम करतं (आधीसारखंच):
  - Discount% टाकलं  -> Buy Rate आपोआप त्यातून calculate होतो
  - Buy Rate टाकलं    -> Discount% आपोआप उलट (reverse) calculate होतो
============================================================================
"""
import flet as ft
from database import search_parts, get_part_by_id, get_part_stock, add_stock_in_entry


class StockInView(ft.Row):
    """Part Number/Name टाईप करा -> live suggestions दिसतात -> क्लिक करताच
    Description/HSN/GST%/Location आपोआप भरतं. MRP + Qty + (Discount% किंवा
    Buy Rate) टाकताच खालचं संपूर्ण गणित (Base Rate, Buying%, Taxable Value,
    CGST/SGST, Total) लाईव्ह दिसतं."""

    def __init__(self, refresh_callback=None):
        super().__init__(expand=True)
        self.refresh_callback = refresh_callback
        self.selected_part = None
        self._all_parts = []     # सगळे parts cache (search suggestions साठी)
        self._syncing = False    # Discount%<->Buy Rate मधला infinite-loop टाळण्यासाठी

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}

        # ---------------- Part Search + Live Suggestions ----------------
        self.part_search = ft.TextField(
            label="🔩 Part Number/Name टाईप करा *", height=52,
            on_change=self._on_part_search_change, **S,
        )
        self.part_suggestions_list = ft.ListView(spacing=2, height=170)
        self.part_suggestions_box = ft.Container(
            content=self.part_suggestions_list, bgcolor="#161622",
            border_radius=8, border=ft.Border.all(1, "#1a1a26"),
            padding=4, visible=False,
        )

        self.f_description = ft.TextField(label="Description", height=52, read_only=True, **S)
        self.f_hsn = ft.TextField(label="HSN/SAC", height=52, read_only=True, **S)
        self.f_gst_rate = ft.TextField(label="GST %", height=52, read_only=True, **S)
        self.f_location = ft.TextField(label="Location (auto)", height=52, read_only=True, visible=False, **S)
        self.f_location_manual = ft.TextField(label="📍 Rack/Location", height=52, **S)
        
        # ---------------- Manual Inputs ----------------
        self.f_mrp = ft.TextField(label="🏷️ MRP *", height=52, prefix=ft.Text("₹ "),
                                   keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.f_qty = ft.TextField(label="📦 Quantity *", height=52, value="1",
                                   keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.f_discount_percent = ft.TextField(
            label="💸 Purchase Discount % (टाकलं तर Buy Rate आपोआप येईल)", height=52,
            keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.f_buy_rate = ft.TextField(
            label="💰 Buy Rate * (माहीत असेल तर थेट टाक — Discount% आपोआप दिसेल)", height=52,
            prefix=ft.Text("₹ "), keyboard_type=ft.KeyboardType.NUMBER, **S)
        self.f_supplier = ft.TextField(label="🏭 Supplier/Vendor Name", height=52, **S)
        self.f_location_manual = ft.TextField(label="📍 Rack/Location (हवं असेल तर बदला)", height=52, **S)
        self.f_date = ft.TextField(label="📅 Date (DD.MM.YYYY)", height=52, **S)

        self.f_mrp.on_change = lambda e: self._recalc()
        self.f_qty.on_change = lambda e: self._recalc()
        self.f_discount_percent.on_change = self._on_discount_changed
        self.f_buy_rate.on_change = self._on_buy_rate_changed

        # ---------------- Enter दाबताच पुढच्या फील्डवर उडी (Auto-Focus Chain) ----------------
        self.f_mrp.on_submit = lambda e: self._focus_next(self.f_qty)
        self.f_qty.on_submit = lambda e: self._focus_next(self.f_discount_percent)
        self.f_discount_percent.on_submit = lambda e: self._focus_next(self.f_buy_rate)
        self.f_buy_rate.on_submit = lambda e: self._focus_next(self.f_supplier)
        self.f_supplier.on_submit = lambda e: self._focus_next(self.f_date)
        self.f_date.on_submit = lambda e: self.handle_save(e)

        # ---------------- Live Calculated Fields (Read-only) ----------------
        self.r_base_rate = ft.Text("₹0.00", size=15, weight="bold", color="white")
        self.r_total_base = ft.Text("₹0.00", size=15, weight="bold", color="white")
        self.r_taxable = ft.Text("₹0.00", size=15, weight="bold", color="white")
        self.r_cgst = ft.Text("₹0.00", size=14, color="#00aaff")
        self.r_sgst = ft.Text("₹0.00", size=14, color="#00aaff")
        self.r_total_amt = ft.Text("₹0.00", size=22, weight="bold", color="#00ffaa")
        self.r_profit_per_unit = ft.Text("₹0.00", size=15, weight="bold", color="#00ffaa")
        self.r_profit_pct = ft.Text("0.00%", size=15, weight="bold", color="#00ffaa")

        self.status_text = ft.Text("", size=13, visible=False)
        self.save_btn = ft.ElevatedButton(
            "💾 Stock-In Save करा", bgcolor="#00ffaa", color="black",
            height=52, expand=True, on_click=self.handle_save,
        )

        def _calc_row(label, ctrl):
            return ft.Row([ft.Text(label, size=12, color="#94a3b8"), ft.Container(expand=True), ctrl])

        calc_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text("🧮 Auto-Calculated (Government-Compliant Reverse GST)", size=14, weight="bold", color="white"),
                    ft.Divider(color="#1a1a26"),
                    _calc_row("Base Rate (Excl. GST)", self.r_base_rate),
                    _calc_row("Total Base Amount", self.r_total_base),
                    ft.Divider(color="#1a1a26"),
                    _calc_row("Taxable Value", self.r_taxable),
                    _calc_row("CGST", self.r_cgst),
                    _calc_row("SGST", self.r_sgst),
                    ft.Divider(color="#1a1a26"),
                    _calc_row("Total Purchase Amount", self.r_total_amt),
                    ft.Container(height=6),
                    ft.Text("📈 Profit Margin Tracker (MRP vs Buy Rate)", size=13, weight="bold", color="white"),
                    _calc_row("Profit Per Unit", self.r_profit_per_unit),
                    _calc_row("Profit Margin %", self.r_profit_pct),
                ],
                spacing=8,
            ),
            bgcolor="#161622", padding=16, border_radius=12,
        )

        left = ft.Container(
            content=ft.Column(
                [
                    ft.Text("📥 Inventory In — Stock-In Entry", size=20, weight="bold", color="#00ffaa"),
                    self.status_text,
                    self.part_search,
                    self.part_suggestions_box,
                    ft.Row([self.f_description, self.f_hsn], spacing=10),
                    self.f_gst_rate,
                    ft.Divider(color="#1a1a26"),
                    ft.Text("Manual Entry", size=13, weight="bold", color="white"),
                    ft.Row([self.f_mrp, self.f_qty], spacing=10),
                    ft.Row([self.f_discount_percent, self.f_buy_rate], spacing=10),
                    self.f_location_manual,
                    self.f_supplier,
                    self.f_date,
                ],
                scroll="auto", spacing=10,
            ),
            padding=20, expand=True, bgcolor="#0e0e16",
        )

        right = ft.Container(
            content=ft.Column([calc_box, ft.Container(height=10), self.save_btn], spacing=10, scroll="auto"),
            padding=20, width=380, bgcolor="#0e0e16",
        )

        self.controls = [left, ft.VerticalDivider(width=1, color="#1a1a26"), right]

    # ======================================================================
    def did_mount(self):
        from datetime import datetime
        self.f_date.value = datetime.now().strftime("%d.%m.%Y")
        self._load_all_parts()
        self._recalc()

    def _load_all_parts(self):
        """सगळे Parts (ज्यांना Part Number आहे) एकदाच cache करतो — प्रत्येक
        keystroke वर पुन्हा DB query करण्याऐवजी इथूनच फिल्टर करतो, जलद वाटावं म्हणून."""
        self._all_parts = [p for p in search_parts(None) if p["part_number"]]

    def _focus_next(self, field):
        """Enter दाबताच पुढच्या फील्डवर cursor नेतो."""
        if self.page:
            field.focus()
            self.page.update()

    # ======================================================================
    # PART SEARCH — टाईप करताच Live Suggestions
    # ======================================================================
    def _on_part_search_change(self, e):
        query = (self.part_search.value or "").strip().lower()

        # यूजर आता टाईप करतोय म्हणजे आधी निवडलेला Part अजून valid नाही —
        # जोपर्यंत एका suggestion वर क्लिक करत नाही तोपर्यंत selected_part
        # None च ठेवतो, जेणेकरून चुकीच्या/जुन्या Part वर Save होणार नाही.
        self.selected_part = None
        self._clear_autofill_fields()

        if not query:
            self.part_suggestions_box.visible = False
            if self.page:
                self.update()
            return

        matches = [
            p for p in self._all_parts
            if query in (p["part_number"] or "").lower() or query in (p["product_name"] or "").lower()
        ][:10]

        self.part_suggestions_list.controls.clear()
        if not matches:
            self.part_suggestions_list.controls.append(
                ft.Text("कोणताही जुळणारा Part सापडला नाही.", size=12, color="#94a3b8", italic=True)
            )
        else:
            for p in matches:
                stock = get_part_stock(p["id"])
                self.part_suggestions_list.controls.append(
                    ft.Container(
                        content=ft.Text(
                            f"{p['part_number']} — {p['product_name']}  (Stock: {stock:.0f})",
                            size=13, color="white",
                        ),
                        padding=8, bgcolor="#1a1a26", border_radius=6, ink=True,
                        on_click=lambda e, part=p: self._select_part(part),
                    )
                )

        self.part_suggestions_box.visible = True
        if self.page:
            self.update()

    def _select_part(self, part):
        """Suggestions मधल्या एका Part वर क्लिक केला की तोच पक्का selected_part
        म्हणून सेट होतो — इथून पुढे Save वर याच Part वर एन्ट्री जाईल."""
        self.selected_part = part
        self.part_search.value = f"{part['part_number']} — {part['product_name']}"
        self.part_suggestions_box.visible = False

        self.f_description.value = part["product_name"] or ""
        self.f_hsn.value = part["hsn_sac"] if "hsn_sac" in part.keys() and part["hsn_sac"] else ""
        self.f_gst_rate.value = str(part["gst_rate"]) if "gst_rate" in part.keys() and part["gst_rate"] is not None else "18"
        self.f_location.value = part["location"] if "location" in part.keys() and part["location"] else ""
        self.f_location_manual.value = self.f_location.value

        if not (self.f_mrp.value or "").strip() and "mrp" in part.keys() and part["mrp"]:
            self.f_mrp.value = str(part["mrp"])
        if not (self.f_buy_rate.value or "").strip() and part["buying_rate"]:
            self.f_buy_rate.value = str(part["buying_rate"])

        self.status_text.visible = False
        if self.page:
            self.update()

        self._recalc()
        self._focus_next(self.f_mrp)   # 👈 Part निवडताच थेट MRP वर उडी

    def _clear_autofill_fields(self):
        self.f_description.value = ""
        self.f_hsn.value = ""
        self.f_gst_rate.value = ""
        self.f_location.value = ""

    # ======================================================================
    # Discount% <-> Buy Rate — दोन्ही बाजूने sync (loop-safe)
    # ======================================================================
    def _current_base_rate(self):
        try:
            mrp = float(self.f_mrp.value or 0)
        except ValueError:
            mrp = 0
        gst_rate = float(self.f_gst_rate.value or 0) if self.f_gst_rate.value else 0
        return (mrp / (1 + gst_rate / 100)) if gst_rate else mrp

    def _on_discount_changed(self, e):
        """Purchase Discount% टाकलं की Buy Rate आपोआप त्यातून काढतो."""
        if self._syncing:
            return
        try:
            disc = float(self.f_discount_percent.value or 0)
        except ValueError:
            return

        base_rate = self._current_base_rate()
        if base_rate <= 0:
            self._show_status("⚠️ आधी MRP आणि Part (GST%) भरा, मगच Discount% वापरता येईल.", "#ff8800")
            return

        self._syncing = True
        new_buy_rate = base_rate * (1 - disc / 100)
        self.f_buy_rate.value = f"{new_buy_rate:.2f}"
        if self.page:
            self.f_buy_rate.update()
        self._syncing = False
        self._recalc()

    def _on_buy_rate_changed(self, e):
        """Buy Rate थेट टाकलं (किंवा auto-filled) की Discount% उलट काढून दाखवतो."""
        if self._syncing:
            self._recalc()
            return
        try:
            buy_rate = float(self.f_buy_rate.value or 0)
        except ValueError:
            self._recalc()
            return

        base_rate = self._current_base_rate()
        self._syncing = True
        if base_rate > 0:
            disc = (base_rate - buy_rate) / base_rate * 100
            self.f_discount_percent.value = f"{disc:.2f}"
            if self.page:
                self.f_discount_percent.update()
        self._syncing = False
        self._recalc()

    # ======================================================================
    def _recalc(self):
        from database import calculate_stock_in

        try:
            mrp = float(self.f_mrp.value or 0)
            qty = float(self.f_qty.value or 0)
            buy_rate = float(self.f_buy_rate.value or 0)
        except ValueError:
            mrp = qty = buy_rate = 0

        gst_rate = float(self.f_gst_rate.value or 0) if self.f_gst_rate.value else 0
        calc = calculate_stock_in(mrp, qty, buy_rate, gst_rate)

        self.r_base_rate.value = f"₹{calc['base_rate']:,.2f}"
        self.r_total_base.value = f"₹{calc['total_base']:,.2f}"
        self.r_taxable.value = f"₹{calc['taxable_value']:,.2f}"
        self.r_cgst.value = f"₹{calc['cgst']:,.2f}"
        self.r_sgst.value = f"₹{calc['sgst']:,.2f}"
        self.r_total_amt.value = f"₹{calc['total_amount']:,.2f}"
        self.r_profit_per_unit.value = f"₹{calc['profit_per_unit']:,.2f}"
        self.r_profit_pct.value = f"{calc['profit_margin_percent']:.2f}%"

        self.r_profit_pct.color = "#00ffaa" if calc["profit_margin_percent"] >= 0 else "#ff4444"

        if self.page:
            self.update()

    # ======================================================================
    def handle_save(self, e):
        if not self.selected_part:
            self._show_status("⚠️ आधी वरती टाईप करून Part निवडा (suggestions मधून क्लिक करा).", "#ff4444")
            return
        try:
            mrp = float(self.f_mrp.value or 0)
            qty = float(self.f_qty.value or 0)
            buy_rate = float(self.f_buy_rate.value or 0)
        except ValueError:
            self._show_status("⚠️ MRP/Qty/Buy Rate फक्त नंबरमध्ये.", "#ff4444")
            return

        if mrp <= 0 or qty <= 0 or buy_rate <= 0:
            self._show_status("⚠️ MRP, Qty, Buy Rate शून्यापेक्षा जास्त असावेत.", "#ff4444")
            return

        gst_rate = float(self.f_gst_rate.value or 0) if self.f_gst_rate.value else 0

        try:
            add_stock_in_entry(
                part_id=self.selected_part["id"],
                part_number=self.selected_part["part_number"],
                description=self.selected_part["product_name"],
                hsn_sac=self.f_hsn.value or "",
                gst_rate=gst_rate,
                location=(self.f_location_manual.value or self.f_location.value or ""),
                mrp=mrp, qty=qty, buy_rate=buy_rate,
                supplier_name=(self.f_supplier.value or "").strip(),
                tx_date=(self.f_date.value or "").strip(),
            )
        except Exception as ex:
            self._show_status(f"❌ एरर: {ex}", "#ff4444")
            return

        self._show_status("✅ Stock-In सेव्ह झालं! स्टॉक आपोआप वाढला.", "#00ffaa")
        if self.refresh_callback:
            self.refresh_callback()
        self._clear_form()

    def _show_status(self, msg, color):
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        if self.page:
            self.status_text.update()

    def _clear_form(self):
        from datetime import datetime
        self.part_search.value = ""
        self.part_suggestions_box.visible = False
        self.selected_part = None
        for f in (self.f_description, self.f_hsn, self.f_gst_rate, self.f_location,
                  self.f_location_manual, self.f_mrp, self.f_discount_percent,
                  self.f_supplier):
            f.value = ""
        self.f_qty.value = "1"
        self.f_buy_rate.value = ""
        self.f_date.value = datetime.now().strftime("%d.%m.%Y")
        self._load_all_parts()
        self._recalc()