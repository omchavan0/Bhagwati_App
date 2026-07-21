"""
============================================================================
INVENTORY SHEET VIEW — Excel-style, Stock-In डेटावर आधारित
============================================================================
Wide table -> horizontal + vertical दोन्ही स्क्रोल. Low Stock/Out of Stock
फिल्टर चिप्स, MRP/Stock-Value/Reorder Level सह प्रोफेशनल Inventory Sheet.
============================================================================
"""
import os
import flet as ft
from database import (
    get_inventory_sheet_rows, get_inventory_sheet_totals,
    search_inventory_sheet_rows, export_inventory_sheet_to_excel,
)

CARD_SPECS = [
    ("Qty", "total_qty", "{:.0f}", "#00aaff"),
    ("Total MRP", "total_mrp", "₹{:,.0f}", "#aa88ff"),
    ("Total Buy Rate", "total_buy_rate", "₹{:,.0f}", "#ff8800"),
    ("Avg Dis.%", "avg_dis_percent", "{:.1f}%", "#ffb020"),
    ("Total Profit/Unit", "total_profit_per_unit", "₹{:,.0f}", "#00ffaa"),
    ("Avg Margin %", "avg_margin_percent", "{:.1f}%", "#ff5c9e"),
    ("Stock Value (Buy)", "total_amount", "₹{:,.0f}", "#2dd4bf"),
    ("Stock Value (MRP)", "total_mrp_value", "₹{:,.0f}", "#818cf8"),
]

FILTERS = [("all", "सर्व"), ("low_stock", "⚠️ Low Stock"), ("out_of_stock", "🔴 Out of Stock")]


def _get_output_dir():
    try:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads, exist_ok=True)
        return downloads
    except Exception:
        fallback = os.path.join(os.getcwd(), "exports")
        os.makedirs(fallback, exist_ok=True)
        return fallback


class InventorySheetView(ft.Container):
    """Excel-style Inventory Sheet — रुंद टेबल, दोन्ही बाजूने scroll,
    summary cards, Low/Out-of-Stock फिल्टर, Excel Export."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")
        self.filter_mode = "all"

        self.search_field = ft.TextField(
            hint_text="Part Number / Description शोधा...",
            bgcolor="#161622", height=42, width=280,
            border_color="#1a1a26", focused_border_color="#00ffaa",
            prefix_icon=ft.Icons.SEARCH, on_change=self.handle_search,
        )
        self.export_btn = ft.OutlinedButton(
            content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD, size=16), ft.Text("Export Excel", size=12)], spacing=6),
            on_click=self.handle_export,
        )

        self.filter_chips = ft.Row(spacing=8)
        self.cards_row = ft.Row(spacing=10, scroll="auto")

        self.table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Sr.No", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Part No", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Description", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("HSN/SAC", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("GST%", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("MRP", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Buy Rate", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Qty", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Dis.%", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Amount", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Value@MRP", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Profit/Unit", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Margin%", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Reorder Lvl", size=11, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Brand", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Category", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Unit", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Barcode", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Vendor", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Location", size=11, color="#94a3b8")),
                ft.DataColumn(ft.Text("Last Stock-In", size=11, color="#94a3b8")),
            ],
            rows=[], column_spacing=18, data_row_min_height=38, data_row_max_height=44,
            heading_row_color="#161622", heading_row_height=36,
        )

        # टीप: आतला Row (horizontal scroll) + बाहेरचा Column (vertical scroll)
        # असे दोन्ही स्क्रोल मोड — त्यामुळे रुंद टेबल असूनही height fixed राहते
        # आणि दोन्ही दिशेने आरामात scroll करता येतं (Excel सारखं).
        self.table_holder = ft.Container(
            content=ft.Row(
                [ft.Column([self.table], scroll=ft.ScrollMode.ALWAYS, expand=True)],
                scroll=ft.ScrollMode.ALWAYS,
            ),
            bgcolor="#0e0e16", border_radius=10,
            border=ft.Border.all(1, "#1a1a26"), padding=8, expand=True,
        )

        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("📊 Inventory Sheet — Excel View", size=22, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True),
                        self.search_field,
                        self.export_btn,
                    ]
                ),
                ft.Container(height=8),
                self.filter_chips,
                ft.Container(height=8),
                self.cards_row,
                ft.Container(height=12),
                self.table_holder,
            ],
            spacing=6, expand=True,
        )

    # ==================================================================
    def did_mount(self):
        self._build_filter_chips()
        self.refresh()

    def _build_filter_chips(self):
        chips = []
        for key, label in FILTERS:
            selected = key == self.filter_mode
            chips.append(
                ft.Container(
                    content=ft.Text(label, size=12, color="black" if selected else "white", weight="bold" if selected else None),
                    bgcolor="#00ffaa" if selected else "#161622",
                    padding=ft.Padding(left=14, right=14, top=6, bottom=6),
                    border_radius=999, ink=True,
                    on_click=lambda e, k=key: self._set_filter(k),
                )
            )
        self.filter_chips.controls = chips

    def _set_filter(self, key):
        self.filter_mode = key
        self._build_filter_chips()
        self.refresh(query=self.search_field.value)

    def handle_search(self, e):
        self.refresh(query=self.search_field.value)

    def handle_export(self, e):
        try:
            path = os.path.join(_get_output_dir(), "inventory_sheet_export.xlsx")
            export_inventory_sheet_to_excel(path)
            self.page.snack_bar = ft.SnackBar(ft.Text(f"✅ Export झालं: {path}", color="black"), bgcolor="#00ffaa", open=True)
        except Exception as ex:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"❌ एरर: {ex}", color="white"), bgcolor="#ff4444", open=True)
        self.page.update()

    # ==================================================================
    def _build_cards(self, totals):
        cards = []
        for title, key, fmt, color in CARD_SPECS:
            cards.append(
                ft.Container(
                    content=ft.Column(
                        [ft.Text(title, size=10, color="#94a3b8"), ft.Text(fmt.format(totals[key]), size=15, weight="bold", color=color)],
                        spacing=2,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.10, color),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.30, color)),
                    border_radius=10, padding=ft.Padding(left=12, right=12, top=8, bottom=8),
                )
            )
        if totals["low_stock_count"] or totals["out_of_stock_count"]:
            cards.append(
                ft.Container(
                    content=ft.Column(
                        [ft.Text("Alerts", size=10, color="#94a3b8"),
                         ft.Text(f"⚠️ {totals['low_stock_count']} Low  •  🔴 {totals['out_of_stock_count']} Out",
                                 size=13, weight="bold", color="#ff4444")],
                        spacing=2,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.10, "#ff4444"),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.30, "#ff4444")),
                    border_radius=10, padding=ft.Padding(left=12, right=12, top=8, bottom=8),
                )
            )
        return cards

    def _build_rows(self, records):
        rows = []
        for i, r in enumerate(records):
            if r["is_out_of_stock"]:
                qty_color = "#ff4444"
            elif r["is_low_stock"]:
                qty_color = "#ffb020"
            else:
                qty_color = "white"
            zebra = ft.Colors.with_opacity(0.035, "#ffffff") if i % 2 else None
            rows.append(ft.DataRow(
                color=zebra,
                cells=[
                    ft.DataCell(ft.Text(str(i + 1), size=11, color="white")),
                    ft.DataCell(ft.Text(r["part_number"] or "-", size=11, color="white")),
                    ft.DataCell(ft.Text(r["description"], size=11, color="white")),
                    ft.DataCell(ft.Text(r["hsn_sac"] or "-", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(f"{r['gst_rate']:.0f}%", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(f"₹{r['mrp']:.0f}", size=11, color="#aa88ff")),
                    ft.DataCell(ft.Text(f"₹{r['buy_rate']:.2f}", size=11, color="white")),
                    ft.DataCell(ft.Text(f"{r['qty']:.0f}", size=11, weight="bold", color=qty_color)),
                    ft.DataCell(ft.Text(f"{r['buy_dis_percent']:.1f}%", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(f"₹{r['total_amount']:,.2f}", size=11, weight="bold", color="#00ffaa")),
                    ft.DataCell(ft.Text(f"₹{r['total_mrp_value']:,.2f}", size=11, color="#818cf8")),
                    ft.DataCell(ft.Text(f"₹{r['profit_per_unit']:.2f}", size=11, color="#00ffaa")),
                    ft.DataCell(ft.Text(f"{r['margin_percent']:.1f}%", size=11, color="#00ffaa")),
                    ft.DataCell(ft.Text(f"{r['reorder_level']:.0f}", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(r["brand"] or "-", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(r["category"] or "-", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(r["unit"] or "Nos", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(r["barcode"] or "-", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(r["vendor"] or "-", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(r["location"] or "-", size=11, color="#94a3b8")),
                    ft.DataCell(ft.Text(r["last_stock_in_date"] or "-", size=11, color="#64748b")),
                ],
            ))
        return rows

    # ==================================================================
    def refresh(self, query=None):
        if self.page is None:
            return
        records = search_inventory_sheet_rows(query, filter_mode=self.filter_mode)
        totals = get_inventory_sheet_totals(records) if records else get_inventory_sheet_totals([])

        self.cards_row.controls = self._build_cards(totals)
        self.table.rows = self._build_rows(records)

        self.update()