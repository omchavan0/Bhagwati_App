"""
============================================================================
PROFIT & LOSS DASHBOARD — "Liquid Glass" (iOS/Apple-style) डिझाइन
============================================================================
काय दाखवतं:
  - Revenue (Udhaari "Given" प्रकारच्या सगळ्या sales चा एकूण business)
  - Parts Profit (Sell - Buying margin, db_inventory च्या ledger मधून)
  - अंदाजे Labour Income (Revenue - Parts Net Amount)
  - Total Expenses (दुकानाचा खर्च)
  - Net Profit = (Parts Profit + Labour Income) - Expenses
  - Outstanding Due (अजून ग्राहकांकडून यायचे)
  - गेल्या 6 महिन्यांचा Revenue vs Expense vs Profit trend (bar chart)

डिझाइन — "Liquid Glass":
  गडद gradient बॅकग्राऊंडवर मोठे, blurred, रंगीत "glow blobs" ठेवले आहेत
  (जसं iOS 18/19 च्या Liquid Glass मध्ये दिसतं), आणि त्यावर अर्ध-पारदर्शक
  (translucent), gentle-border, soft-shadow असलेले "glass cards" तरंगतात.
  Flet च्या नवीन आवृत्तीत खरा backdrop-blur (ft.Blur) हवा असल्यास कार्ड्सना
  `blur=ft.Blur(18, 18)` जोडता येईल — इथे जुन्या Flet आवृत्त्यांशीही सुसंगत
  राहावं म्हणून translucent-gradient + shadow नेच glass-look दिलाय.
============================================================================
"""
from datetime import datetime, timedelta

import flet as ft

from database import get_udhaari, get_expenses, get_total_expenses, get_profit_summary
from db_core import _parse_date

# ---------------- Palette — Liquid Glass ----------------
BG_TOP = "#0b0f2e"       # खोल इंडिगो
BG_BOTTOM = "#050510"    # जवळपास काळा
GLOW_1 = "#7c5cff"       # जांभळा glow
GLOW_2 = "#00e6c3"       # टील/एक्वा glow (existing #00ffaa शी सुसंगत)
GLOW_3 = "#ff5c9e"       # गुलाबी glow
GLASS_BG = "#ffffff"     # पारदर्शकतेसाठी पांढरा (with_opacity वापरून)
TEXT_MUTED = "#a8b0c8"


def _glow_blob(color, size, top=None, left=None, right=None, bottom=None):
    """मोठा, अंधुक, रंगीत गोल — 'Liquid Glass' मागचा glow तयार करण्यासाठी.
    टीप: brightness मुद्दाम कमी ठेवलाय (0.12 fill + मऊ shadow) जेणेकरून वरचा
    मजकूर वाचायला त्रास होऊ नये — आधीचं व्हर्जन खूप 'चमकत' होतं."""
    return ft.Container(
        width=size, height=size, border_radius=size,
        bgcolor=ft.Colors.with_opacity(0.12, color),
        top=top, left=left, right=right, bottom=bottom,
        shadow=ft.BoxShadow(blur_radius=size * 0.5, color=ft.Colors.with_opacity(0.20, color),
                             spread_radius=size * 0.03),
    )


def _glass_card(content, width=None, expand=None, padding=20):
    """मुख्य 'Glass Card' — अर्ध-पारदर्शक पांढरा थर + मऊ बॉर्डर + खोल shadow."""
    return ft.Container(
        content=content,
        width=width, expand=expand, padding=padding,
        bgcolor=ft.Colors.with_opacity(0.06, GLASS_BG),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.14, GLASS_BG)),
        border_radius=22,
        shadow=ft.BoxShadow(blur_radius=30, spread_radius=-4,
                             color=ft.Colors.with_opacity(0.45, "#000000"),
                             offset=ft.Offset(0, 12)),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1), end=ft.Alignment(1, 1),
            colors=[ft.Colors.with_opacity(0.10, GLASS_BG), ft.Colors.with_opacity(0.02, GLASS_BG)],
        ),
    )


def _kpi_card(icon, title, value, sub=None, accent="#00e6c3"):
    return _glass_card(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(icon, size=18),
                            bgcolor=ft.Colors.with_opacity(0.18, accent),
                            border_radius=12, width=40, height=40,
                            alignment=ft.Alignment(0, 0),
                        ),
                        ft.Container(expand=True),
                    ]
                ),
                ft.Container(height=10),
                ft.Text(title, size=12, color=TEXT_MUTED),
                ft.Text(value, size=24, weight="bold", color="white"),
                ft.Text(sub, size=11, color=accent) if sub else ft.Container(height=0),
            ],
            spacing=2,
        ),
        expand=True,
    )


class PnLDashboardView(ft.Container):
    """Profit & Loss Dashboard — Liquid Glass style."""

    def __init__(self):
        super().__init__(expand=True, padding=0)
        self.body_holder = ft.Container(expand=True, padding=28)

        background = ft.Stack(
            [
                ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1),
                        colors=[BG_TOP, BG_BOTTOM],
                    ),
                ),
                # blobs आता कोपऱ्यांमध्ये लांब ढकलले आहेत आणि आकाराने लहान —
                # जेणेकरून वरचा "Profit & Loss" मथळा त्यांच्यामागे झाकोळला जाणार नाही
                _glow_blob(GLOW_1, 300, top=-220, left=-180),
                _glow_blob(GLOW_2, 280, top=160, right=-200),
                _glow_blob(GLOW_3, 240, bottom=-160, left=260),
                # हलका गडद पडदा (scrim) — glow आणखी सौम्य दिसण्यासाठी, मजकूर वाचनीय राहतो
                ft.Container(expand=True, bgcolor=ft.Colors.with_opacity(0.28, "#000000")),
                self.body_holder,
            ],
            expand=True,
        )
        self.content = background

    # ======================================================================
    def did_mount(self):
        self.refresh()

    def refresh(self):
        data = self._compute_pnl()

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Profit & Loss", size=26, weight="bold", color="white"),
                        ft.Text("Live overview — आत्तापर्यंतचा संपूर्ण हिशोब", size=12, color=TEXT_MUTED),
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Text(datetime.now().strftime("%d %b %Y, %I:%M %p"), size=12, color=TEXT_MUTED),
                    bgcolor=ft.Colors.with_opacity(0.08, GLASS_BG),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.14, GLASS_BG)),
                    border_radius=999, padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                ),
            ]
        )

        kpi_row = ft.Row(
            [
                _kpi_card("💵", "Total Revenue", f"₹{data['revenue']:,.0f}", accent="#00e6c3"),
                _kpi_card("🧾", "Total Expenses", f"₹{data['expenses']:,.0f}", accent="#ff5c9e"),
                _kpi_card(
                    "📈" if data["net_profit"] >= 0 else "📉",
                    "Net Profit", f"₹{data['net_profit']:,.0f}",
                    sub=("Profitable ✅" if data["net_profit"] >= 0 else "Loss ⚠️"),
                    accent="#7c5cff",
                ),
                _kpi_card("⏳", "Outstanding Due", f"₹{data['due']:,.0f}", accent="#ffb020"),
            ],
            spacing=16,
        )

        breakdown = _glass_card(
            ft.Column(
                [
                    ft.Text("Profit Breakdown", size=15, weight="bold", color="white"),
                    ft.Container(height=8),
                    self._breakdown_bar("🔩 Parts Profit (Margin)", data["parts_profit"], data["max_component"], "#00e6c3"),
                    self._breakdown_bar("👷 Labour Income (अंदाजे)", data["labour_income"], data["max_component"], "#7c5cff"),
                    self._breakdown_bar("🧾 Expenses", -data["expenses"], data["max_component"], "#ff5c9e"),
                ],
                spacing=14,
            ),
            expand=True,
        )

        trend = _glass_card(self._build_trend_chart(data["monthly"]), expand=True)

        self.body_holder.content = ft.Column(
            [
                header,
                ft.Container(height=18),
                kpi_row,
                ft.Container(height=18),
                ft.Row([breakdown, trend], spacing=16, expand=True),
            ],
            expand=True, scroll="auto",
        )
        if self.page:
            self.update()

    # ======================================================================
    def _breakdown_bar(self, label, value, max_value, color):
        """Progress-bar: Flet मध्ये अचूक % रुंदी दाखवायला दोन flex-Container चा
        Row वापरतो (filled + उरलेला रिकामा भाग) — हाच पॅटर्न सगळीकडे वापरतात."""
        max_value = max(max_value, 1)
        pct = min(abs(value) / max_value, 1.0)
        filled_flex = max(int(pct * 100), 1)
        empty_flex = max(100 - filled_flex, 0)
        bar_color = color if value >= 0 else "#ff4444"

        bar_row_children = [
            ft.Container(bgcolor=bar_color, border_radius=999, height=10, expand=filled_flex),
        ]
        if empty_flex > 0:
            bar_row_children.append(
                ft.Container(bgcolor=ft.Colors.with_opacity(0.10, GLASS_BG),
                             border_radius=999, height=10, expand=empty_flex)
            )

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(label, size=12, color=TEXT_MUTED),
                        ft.Container(expand=True),
                        ft.Text(f"₹{value:,.0f}", size=12, weight="bold", color="white"),
                    ]
                ),
                ft.Row(bar_row_children, spacing=2),
            ],
            spacing=6,
        )

    def _build_trend_chart(self, monthly):
        if not monthly["labels"]:
            return ft.Column(
                [ft.Text("Trend Chart", size=15, weight="bold", color="white"),
                 ft.Container(height=10),
                 ft.Text("अजून पुरेसा डेटा नाही.", color=TEXT_MUTED, italic=True)],
                expand=True,
            )

        max_val = max(max(monthly["revenue"], default=0), max(monthly["expenses"], default=0), 1)
        max_h = 150
        cols = []
        for i, label in enumerate(monthly["labels"]):
            rev_h = max((monthly["revenue"][i] / max_val) * max_h, 3)
            exp_h = max((monthly["expenses"][i] / max_val) * max_h, 3)
            cols.append(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(width=12, height=rev_h, border_radius=6, bgcolor="#00e6c3"),
                                ft.Container(width=12, height=exp_h, border_radius=6, bgcolor="#ff5c9e"),
                            ],
                            spacing=4, alignment=ft.MainAxisAlignment.CENTER,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        ft.Text(label, size=10, color=TEXT_MUTED),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6,
                )
            )

        legend = ft.Row(
            [
                ft.Row([ft.Container(width=10, height=10, bgcolor="#00e6c3", border_radius=3),
                        ft.Text("Revenue", size=11, color=TEXT_MUTED)], spacing=6),
                ft.Row([ft.Container(width=10, height=10, bgcolor="#ff5c9e", border_radius=3),
                        ft.Text("Expenses", size=11, color=TEXT_MUTED)], spacing=6),
            ],
            spacing=18,
        )

        return ft.Column(
            [
                ft.Text("6-Month Trend", size=15, weight="bold", color="white"),
                legend,
                ft.Container(height=8),
                ft.Row(cols, spacing=16, vertical_alignment=ft.CrossAxisAlignment.END,
                       alignment=ft.MainAxisAlignment.START, scroll="auto"),
            ],
            expand=True,
        )

    # ======================================================================
    # DATA — सगळे आकडे इथे मोजले जातात
    # ======================================================================
    def _compute_pnl(self):
        udhaari_records = get_udhaari()
        given = [r for r in udhaari_records if (r["type"] or "Given") == "Given"]

        revenue = sum((r["total_amt"] or 0) for r in given)
        due = sum((r["due_amt"] or 0) for r in given)

        expenses = get_total_expenses()
        profit_summary = get_profit_summary()  # {"total_net_amount", "total_profit", "line_items"}
        parts_net = profit_summary["total_net_amount"]
        parts_profit = profit_summary["total_profit"]

        # Labour Income चा अंदाज: एकूण revenue मधून parts चा वाटा वजा करून
        labour_income = max(revenue - parts_net, 0)

        gross_profit = parts_profit + labour_income
        net_profit = gross_profit - expenses

        max_component = max(parts_profit, labour_income, expenses, 1)

        monthly = self._monthly_trend(given)

        return {
            "revenue": revenue, "expenses": expenses, "due": due,
            "parts_profit": parts_profit, "labour_income": labour_income,
            "net_profit": net_profit, "max_component": max_component,
            "monthly": monthly,
        }

    def _monthly_trend(self, given_records, months=6):
        """गेल्या N महिन्यांचा Revenue vs Expense — साध्या bar chart साठी."""
        rev_by_month, exp_by_month = {}, {}

        for r in given_records:
            parsed = _parse_date(r["tx_date"])
            if not parsed:
                continue
            key = parsed.strftime("%Y-%m")
            rev_by_month[key] = rev_by_month.get(key, 0) + (r["total_amt"] or 0)

        for r in get_expenses():
            parsed = _parse_date(r["exp_date"])
            if not parsed:
                continue
            key = parsed.strftime("%Y-%m")
            exp_by_month[key] = exp_by_month.get(key, 0) + (r["amount"] or 0)

        all_keys = sorted(set(rev_by_month) | set(exp_by_month))[-months:]
        labels = [datetime.strptime(k, "%Y-%m").strftime("%b %y") for k in all_keys]
        revenue = [rev_by_month.get(k, 0) for k in all_keys]
        expenses = [exp_by_month.get(k, 0) for k in all_keys]

        return {"labels": labels, "revenue": revenue, "expenses": expenses}
