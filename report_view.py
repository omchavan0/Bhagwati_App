import flet as ft
from database import get_daily_summary, get_monthly_summary, get_summary, get_gst_summary_report


class ReportView(ft.Container):
    """Daily आणि Monthly हिसाब ग्राफ — किती काम झालं, किती due आहे."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")

        self.mode = "daily"  # "daily" किंवा "monthly"

        self.chart_holder = ft.Container(expand=True)

        self.daily_btn = ft.ElevatedButton(
            "Daily", bgcolor="#00ffaa", color="black",
            on_click=lambda e: self.switch_mode("daily"),
        )
        self.monthly_btn = ft.OutlinedButton(
            "Monthly",
            on_click=lambda e: self.switch_mode("monthly"),
        )
        self.gst_btn = ft.OutlinedButton(
            "GST Summary",
            on_click=lambda e: self.switch_mode("gst"),
        )

        # समरी कार्ड्स
        self.total_work_text = ft.Text("₹0", size=22, weight="bold", color="white")
        self.total_due_text = ft.Text("₹0", size=22, weight="bold", color="#ff8800")
        self.total_records_text = ft.Text("0", size=22, weight="bold", color="#00ffaa")

        def stat_card(title, value_control):
            return ft.Container(
                content=ft.Column(
                    [ft.Text(title, size=12, color="#94a3b8"), value_control],
                    spacing=4,
                ),
                bgcolor="#161622",
                padding=18,
                border_radius=12,
                expand=True,
            )

        self.stats_row = ft.Row(
            [
                stat_card("एकूण काम (Total Business)", self.total_work_text),
                stat_card("एकूण थकीत (Total Due)", self.total_due_text),
                stat_card("एकूण नोंदी", self.total_records_text),
            ],
            spacing=12,
        )

        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("📊 हिसाब रिपोर्ट", size=24, weight="bold", color="#00ffaa"),
                        ft.Container(expand=True),
                        self.daily_btn,
                        self.monthly_btn,
                        self.gst_btn,
                    ]
                ),
                self.stats_row,
                ft.Container(height=10),
                self.chart_holder,
            ],
            spacing=15,
            expand=True,
        )

    def did_mount(self):
        self.refresh()

    def switch_mode(self, mode):
        self.mode = mode

        def _btn(label, key):
            return ft.ElevatedButton(
                label,
                bgcolor="#00ffaa" if mode == key else "#161622",
                color="black" if mode == key else "white",
                on_click=lambda e, k=key: self.switch_mode(k),
            )

        self.daily_btn = _btn("Daily", "daily")
        self.monthly_btn = _btn("Monthly", "monthly")
        self.gst_btn = _btn("GST Summary", "gst")
        self.content.controls[0].controls[2] = self.daily_btn
        self.content.controls[0].controls[3] = self.monthly_btn
        self.content.controls[0].controls[4] = self.gst_btn

        self.refresh()

    def refresh(self):
        summary = get_summary()
        self.total_work_text.value = f"₹{summary['total_business']:.0f}"
        self.total_due_text.value = f"₹{(summary['total_given_due'] + summary['total_taken_due']):.0f}"
        self.total_records_text.value = str(summary["total_records"])

        if self.mode == "daily":
            data = get_daily_summary(days=14)
            title = "गेल्या 14 दिवसांचा हिसाब"
            self.chart_holder.content = self._build_chart(data, title)
        elif self.mode == "monthly":
            data = get_monthly_summary(months=6)
            title = "गेल्या 6 महिन्यांचा हिसाब"
            self.chart_holder.content = self._build_chart(data, title)
        else:  # gst
            self.chart_holder.content = self._build_gst_summary()

        if self.page:
            self.update()

    def _build_gst_summary(self):
        """GSTR-1 / GSTR-3B भरताना लागणारा HSN-wise Taxable/CGST/SGST breakup.
        टीप: सगळी विक्री Maharashtra (Intra-state) गृहीत धरलीये — CGST+SGST."""
        gst = get_gst_summary_report()

        def card(title, value, color="white"):
            return ft.Container(
                content=ft.Column(
                    [ft.Text(title, size=11, color="#94a3b8"), ft.Text(f"₹{value:,.0f}", size=18, weight="bold", color=color)],
                    spacing=4,
                ),
                bgcolor="#161622", padding=14, border_radius=10, expand=True,
            )

        cards_row = ft.Row(
            [
                card("Taxable Value", gst["total_taxable"], "#00ffaa"),
                card("CGST", gst["total_cgst"], "#00aaff"),
                card("SGST", gst["total_sgst"], "#00aaff"),
                card("Total Tax", gst["total_tax"], "#ff8800"),
            ],
            spacing=10,
        )

        rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(r["hsn_sac"], size=12, color="white")),
                ft.DataCell(ft.Text(f"{r['gst_rate']:.0f}%", size=12, color="#94a3b8")),
                ft.DataCell(ft.Text(f"₹{r['taxable']:,.2f}", size=12, color="white")),
                ft.DataCell(ft.Text(f"₹{r['cgst']:,.2f}", size=12, color="#94a3b8")),
                ft.DataCell(ft.Text(f"₹{r['sgst']:,.2f}", size=12, color="#94a3b8")),
                ft.DataCell(ft.Text(f"₹{r['amount']:,.2f}", size=12, weight="bold", color="#00ffaa")),
            ])
            for r in gst["hsn_rows"]
        ]

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("HSN/SAC", size=12, color="#94a3b8")),
                ft.DataColumn(ft.Text("GST%", size=12, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Taxable Value", size=12, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("CGST", size=12, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("SGST", size=12, color="#94a3b8"), numeric=True),
                ft.DataColumn(ft.Text("Amount", size=12, color="#94a3b8"), numeric=True),
            ],
            rows=rows,
            heading_row_color="#161622", column_spacing=20,
        )

        if not rows:
            body = ft.Text("अजून GST-सकट कुठलीही विक्री (Parts Used सह) नोंदलेली नाही.",
                            color="grey", italic=True, size=13)
        else:
            body = ft.Column([table], scroll="auto")

        return ft.Column(
            [
                cards_row,
                ft.Container(height=10),
                ft.Text("📋 HSN-wise Summary (GSTR-1 / GSTR-3B साठी)", size=14, weight="bold", color="white"),
                ft.Container(content=body, bgcolor="#0e0e16", border_radius=12, padding=14, expand=True),
            ],
            spacing=10, expand=True,
        )

    def _build_chart(self, data, title):
        labels = data["labels"]

        if not labels:
            return ft.Container(
                content=ft.Column(
                    [ft.Text("अजून पुरेसा डेटा नाही (Trans. Date भरून नोंदी जोडा).",
                             color="grey", italic=True, size=14)],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                ),
                expand=True,
            )

        max_val = max(max(data["totals"], default=0), max(data["dues"], default=0), 1)
        max_bar_height = 220  # पिक्सेल — सगळ्यात मोठ्या bar ची कमाल उंची

        bar_columns = []
        for i, label in enumerate(labels):
            total_val = data["totals"][i]
            due_val = data["dues"][i]

            total_h = max((total_val / max_val) * max_bar_height, 2) if total_val > 0 else 2
            due_h = max((due_val / max_val) * max_bar_height, 2) if due_val > 0 else 2

            bar_pair = ft.Row(
                [
                    ft.Container(
                        content=ft.Container(
                            width=14, height=total_h, bgcolor="#00ffaa", border_radius=4,
                        ),
                        alignment=ft.Alignment(0, 1),
                        height=max_bar_height,
                        tooltip=f"Total ₹{total_val:.0f}",
                    ),
                    ft.Container(
                        content=ft.Container(
                            width=14, height=due_h, bgcolor="#ff8800", border_radius=4,
                        ),
                        alignment=ft.Alignment(0, 1),
                        height=max_bar_height,
                        tooltip=f"Due ₹{due_val:.0f}",
                    ),
                ],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
            )

            bar_columns.append(
                ft.Column(
                    [
                        bar_pair,
                        ft.Container(height=4),
                        ft.Text(label, size=10, color="#94a3b8"),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                )
            )

        chart = ft.Row(
            bar_columns,
            spacing=18,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.END,
            scroll="auto",
        )

        legend = ft.Row(
            [
                ft.Row([ft.Container(width=12, height=12, bgcolor="#00ffaa", border_radius=3),
                        ft.Text("Total काम", size=12, color="#94a3b8")], spacing=6),
                ft.Row([ft.Container(width=12, height=12, bgcolor="#ff8800", border_radius=3),
                        ft.Text("Due रक्कम", size=12, color="#94a3b8")], spacing=6),
            ],
            spacing=20,
        )

        return ft.Column(
            [
                ft.Text(title, size=14, color="white", weight="bold"),
                legend,
                ft.Container(
                    content=chart,
                    expand=True,
                    padding=ft.Padding.only(top=20),
                    bgcolor="#0e0e16",
                    border_radius=12,
                ),
            ],
            expand=True,
        )
