"""
============================================================================
GST RETURNS VIEW — GSTR-1 (B2B/B2C) + GSTR-3B + HSN Summary — एका स्क्रीनवर
============================================================================
"""
import os
import flet as ft

from database import get_gstr1_b2b, get_gstr1_b2c, get_gstr3b_summary, export_gstr1_to_excel
from database import get_purchase_gst_register  # वरचं नवीन फंक्शन


def _get_output_dir():
    try:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads, exist_ok=True)
        return downloads
    except Exception:
        fallback = os.path.join(os.getcwd(), "exports")
        os.makedirs(fallback, exist_ok=True)
        return fallback


class GSTReturnsView(ft.Container):
    """CA कडे पाठवायला किंवा GST पोर्टलवर मॅन्युअली एंट्री करायला लागणारी
    सगळी GSTR-1/3B माहिती — Date range निवडून, टॅबमध्ये बघता येते."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.mode = "b2b"

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}
        self.date_from = ft.TextField(label="📅 From (DD.MM.YYYY, रिकामं = सुरुवातीपासून)", height=48, width=260, **S)
        self.date_to = ft.TextField(label="📅 To (DD.MM.YYYY, रिकामं = आजपर्यंत)", height=48, width=260, **S)
        self.refresh_btn = ft.ElevatedButton("🔍 Load करा", bgcolor="#00ffaa", color="black",
                                              height=48, on_click=lambda e: self.refresh())
        self.export_btn = ft.OutlinedButton("📊 Excel Export (B2B+B2C+3B)", height=48,
                                             on_click=self.handle_export)

        self.b2b_btn = ft.ElevatedButton("B2B", bgcolor="#00ffaa", color="black",
                                          on_click=lambda e: self.switch_mode("b2b"))
        self.b2c_btn = ft.OutlinedButton("B2C Summary", on_click=lambda e: self.switch_mode("b2c"))
        self.gstr3b_btn = ft.OutlinedButton("GSTR-3B", on_click=lambda e: self.switch_mode("gstr3b"))
        self.purchase_btn = ft.OutlinedButton("📥 Purchase Register", on_click=lambda e: self.switch_mode("purchase"))
        ft.Row([self.b2b_btn, self.b2c_btn, self.gstr3b_btn, self.purchase_btn], spacing=10),
        self.body_holder = ft.Container(expand=True)
        self.status_text = ft.Text("", size=12, color="#94a3b8")

        self.content = ft.Column(
            [
                ft.Text("📑 GST Returns — GSTR-1 / GSTR-3B", size=24, weight="bold", color="#00ffaa"),
                ft.Text("फक्त GST Billing Screen वरून झालेल्या sales इथे मोजल्या जातात.",
                        size=12, color="#94a3b8"),
                ft.Row([self.date_from, self.date_to, self.refresh_btn, self.export_btn], spacing=10),
                ft.Row([self.b2b_btn, self.b2c_btn, self.gstr3b_btn], spacing=10),
                self.status_text,
                ft.Container(height=8),
                self.body_holder,
            ],
            spacing=12, expand=True,
        )

    def did_mount(self):
        self.refresh()

    def switch_mode(self, mode):
        self.mode = mode

        def _btn(label, key):
            if self.mode == key:
                return ft.ElevatedButton(label, bgcolor="#00ffaa", color="black",
                                          on_click=lambda e, k=key: self.switch_mode(k))
            else:
                return ft.OutlinedButton(label, on_click=lambda e, k=key: self.switch_mode(k))

        self.b2b_btn = _btn("B2B", "b2b")
        self.b2c_btn = _btn("B2C Summary", "b2c")
        self.gstr3b_btn = _btn("GSTR-3B", "gstr3b")
        self.purchase_btn = _btn("📥 Purchase Register", "purchase")
        # replace the row of mode buttons (it's the 4th control in content)
        self.content.controls[3] = ft.Row([
            self.b2b_btn, self.b2c_btn, self.gstr3b_btn, self.purchase_btn
        ], spacing=10)
        self.refresh()
    def _dates(self):
        return (self.date_from.value or "").strip() or None, (self.date_to.value or "").strip() or None

    def refresh(self):
        d1, d2 = self._dates()
        if self.mode == "b2b":
            self.body_holder.content = self._build_b2b(d1, d2)
        elif self.mode == "b2c":
            self.body_holder.content = self._build_b2c(d1, d2)
        elif self.mode == "purchase":                              # 👈 नवीन
            self.body_holder.content = self._build_purchase_register(d1, d2)
        else:
            self.body_holder.content = self._build_gstr3b(d1, d2)
        if getattr(self, 'page', None):
            self.update()

    # ==================================================================
    def _build_b2b(self, d1, d2):
        rows_data = get_gstr1_b2b(d1, d2)
        if not rows_data:
            return ft.Text("या कालावधीत कोणतीही B2B (GSTIN सह) विक्री सापडली नाही.",
                            color="grey", italic=True)

        rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(r["invoice_no"], size=12, color="white")),
                ft.DataCell(ft.Text(r["invoice_date"] or "-", size=12, color="#94a3b8")),
                ft.DataCell(ft.Text(r["customer_name"], size=12, color="white")),
                ft.DataCell(ft.Text(r["gstin"], size=12, color="#94a3b8")),
                ft.DataCell(ft.Text(f"₹{r['taxable_value']:,.2f}", size=12, color="white")),
                ft.DataCell(ft.Text(f"₹{r['cgst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['sgst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['igst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['total_value']:,.2f}", size=12, weight="bold", color="#00ffaa")),
            ]) for r in rows_data
        ]
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h, size=11, color="#94a3b8")) for h in
                     ("Invoice No", "Date", "Customer", "GSTIN", "Taxable", "CGST", "SGST", "IGST", "Total")],
            rows=rows, heading_row_color="#161622", column_spacing=18,
        )
        return ft.Column([ft.Container(content=table, bgcolor="#0e0e16", border_radius=12, padding=14)],
                          scroll="auto", expand=True)

    def _build_b2c(self, d1, d2):
        rows_data = get_gstr1_b2c(d1, d2)
        if not rows_data:
            return ft.Text("या कालावधीत कोणतीही B2C (Unregistered) विक्री सापडली नाही.",
                            color="grey", italic=True)

        rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(r["state_code"], size=12, color="white")),
                ft.DataCell(ft.Text(f"₹{r['taxable']:,.2f}", size=12, color="white")),
                ft.DataCell(ft.Text(f"₹{r['cgst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['sgst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['igst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(str(r["count"]), size=12, color="#94a3b8")),
            ]) for r in rows_data
        ]
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h, size=11, color="#94a3b8")) for h in
                     ("State Code", "Taxable", "CGST", "SGST", "IGST", "Invoices")],
            rows=rows, heading_row_color="#161622", column_spacing=20,
        )
        return ft.Container(content=table, bgcolor="#0e0e16", border_radius=12, padding=14)

    def _build_gstr3b(self, d1, d2):
        s = get_gstr3b_summary(d1, d2)

        def card(title, value, color="white"):
            return ft.Container(
                content=ft.Column([ft.Text(title, size=11, color="#94a3b8"),
                                    ft.Text(value, size=18, weight="bold", color=color)], spacing=4),
                bgcolor="#161622", padding=16, border_radius=12, expand=True,
            )

        return ft.Column(
            [
                ft.Text("Table 3.1 — Outward Taxable Supplies", size=14, weight="bold", color="white"),
                ft.Row([
                    card("Taxable Value", f"₹{s['total_taxable']:,.0f}", "#00ffaa"),
                    card("CGST", f"₹{s['total_cgst']:,.0f}", "#00aaff"),
                    card("SGST", f"₹{s['total_sgst']:,.0f}", "#00aaff"),
                ], spacing=10),
                ft.Row([
                    card("IGST", f"₹{s['total_igst']:,.0f}", "#00aaff"),
                    card("Total Tax", f"₹{s['total_tax']:,.0f}", "#ff8800"),
                    card("Invoice Count", str(s["invoice_count"]), "white"),
                ], spacing=10),
                ft.Container(height=6),
                card("Total Invoice Value (Sub-total + Tax)", f"₹{s['total_invoice_value']:,.0f}", "#00ffaa"),
            ],
            spacing=12,
        )

    # ==================================================================
    def handle_export(self, e):
        try:
            d1, d2 = self._dates()
            filepath = os.path.join(_get_output_dir(), "GSTR1_GSTR3B_Export.xlsx")
            export_gstr1_to_excel(filepath, d1, d2)
            self.status_text.value = f"✅ Excel सेव्ह झालं: {filepath}"
            self.status_text.color = "#00ffaa"
        except Exception as ex:
            self.status_text.value = f"❌ Export Error: {ex}"
            self.status_text.color = "#ff4444"
        if self.page:
            self.status_text.update()



    def _build_purchase_register(self, d1, d2):
        rows_data = get_purchase_gst_register(d1, d2)
        if not rows_data:
            return ft.Text("या कालावधीत कोणतीही Purchase नोंद सापडली नाही.",
                            color="grey", italic=True)

        rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(r["bill_no"], size=12, color="white")),
                ft.DataCell(ft.Text(r["bill_date"], size=12, color="#94a3b8")),
                ft.DataCell(ft.Text(r["supplier_name"], size=12, color="white")),
                ft.DataCell(ft.Text(r["supplier_gstin"], size=12, color="#94a3b8")),
                ft.DataCell(ft.Text(f"₹{r['taxable_value']:,.2f}", size=12, color="white")),
                ft.DataCell(ft.Text(f"₹{r['cgst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['sgst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['igst']:,.2f}", size=12, color="#00aaff")),
                ft.DataCell(ft.Text(f"₹{r['grand_total']:,.2f}", size=12, weight="bold", color="#00ffaa")),
            ]) for r in rows_data
        ]
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h, size=11, color="#94a3b8")) for h in
                     ("Bill No", "Date", "Supplier", "GSTIN", "Taxable", "CGST", "SGST", "IGST", "Total")],
            rows=rows, heading_row_color="#161622", column_spacing=18,
        )
        return ft.Column([ft.Container(content=table, bgcolor="#0e0e16", border_radius=12, padding=14)],
                          scroll="auto", expand=True)