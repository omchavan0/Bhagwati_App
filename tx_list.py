import flet as ft
from database import get_udhaari, search_udhaari, get_summary


class TransactionListPanel(ft.Container):
    """डावीकडची Recent Transactions लिस्ट: सर्च, समरी कार्ड्स आणि
    क्लिक करण्यायोग्य आयटम्स (क्लिक केल्यावर on_select_callback कॉल होतो)."""

    def __init__(self, on_select_callback=None):
        super().__init__(
            width=380,
            bgcolor="#0e0e16",
            padding=15,
            border=ft.Border(right=ft.BorderSide(1, "#1a1a26")),
        )

        self.on_select_callback = on_select_callback

        # ---------- समरी कार्ड्स (वरती) ----------
        self.given_due_text = ft.Text("₹0", size=15, weight="bold", color="#00ffaa")
        self.taken_due_text = ft.Text("₹0", size=15, weight="bold", color="#ff8800")
        self.records_text = ft.Text("0", size=15, weight="bold", color="white")

        def summary_card(title, value_control, icon):
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"{icon} {title}", size=10, color="#94a3b8"),
                        value_control,
                    ],
                    spacing=2,
                ),
                bgcolor="#161622",
                padding=10,
                border_radius=10,
                expand=True,
            )

        self.summary_row = ft.Row(
            [
                summary_card("देणे (Given)", self.given_due_text, "📤"),
                summary_card("घेणे (Taken)", self.taken_due_text, "📥"),
                summary_card("नोंदी", self.records_text, "📋"),
            ],
            spacing=8,
        )

        # ---------- सर्च बार ----------
        self.search_field = ft.TextField(
            hint_text="Search transactions...",
            bgcolor="#161622",
            height=40,
            border_color="#1a1a26",
            focused_border_color="#00ffaa",
            on_change=self.handle_search,
            prefix_icon=ft.Icons.SEARCH,
        )

        self.list_view = ft.ListView(expand=True, spacing=8)

        self.content = ft.Column(
            [
                ft.Text("Recent Transactions", size=16, weight="bold", color="white"),
                self.summary_row,
                self.search_field,
                self.list_view,
            ],
            spacing=10,
        )

    # ------------------------------------------------------------------
    def handle_search(self, e):
        self.load_data(query=self.search_field.value)

    # ------------------------------------------------------------------
    def _build_row(self, row):
        """एक रेकॉर्ड (sqlite3.Row) घेऊन क्लिक करण्यायोग्य Container बनवतं."""
        name = row["name"]
        total_amt = row["total_amt"] if row["total_amt"] is not None else 0
        due_amt = row["due_amt"] if row["due_amt"] is not None else 0
        tx_type = row["type"] or "Given"
        vehicle = row["vehicle"] or ""

        icon = "📤" if tx_type == "Given" else "📥"
        color = "#00ffaa" if tx_type == "Given" else "#ff8800"

        subtitle_parts = []
        if vehicle:
            subtitle_parts.append(vehicle)
        if due_amt and float(due_amt) > 0:
            subtitle_parts.append(f"Due ₹{due_amt:.0f}")
        subtitle = "  •  ".join(subtitle_parts)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"{icon} {name} | ₹{total_amt:.0f}", color=color, weight="bold", size=14),
                    ft.Text(subtitle, color="#64748b", size=11) if subtitle else ft.Container(height=0),
                ],
                spacing=2,
            ),
            bgcolor="#161622",
            padding=10,
            border_radius=10,
            ink=True,
            on_click=lambda e, rid=row["id"]: self._handle_click(rid),
        )

    def _handle_click(self, record_id):
        if self.on_select_callback:
            self.on_select_callback(record_id)

    # ------------------------------------------------------------------
    def load_data(self, query=None):
        if self.page is None:
            # control अजून page वर add झालेलं नाही, त्यामुळे update करू नका
            return

        self.list_view.controls.clear()

        records = search_udhaari(query) if query else get_udhaari()

        if not records:
            self.list_view.controls.append(
                ft.Text("कोणतीही नोंद नाही.", color="grey", italic=True)
            )
        else:
            for row in records:
                self.list_view.controls.append(self._build_row(row))

        # समरी कार्ड्स अपडेट (सर्च लागू असतानाही एकूण समरी कायम राहते)
        summary = get_summary()
        self.given_due_text.value = f"₹{summary['total_given_due']:.0f}"
        self.taken_due_text.value = f"₹{summary['total_taken_due']:.0f}"
        self.records_text.value = str(summary["total_records"])

        self.update()
