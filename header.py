import flet as ft

SHOP_NAME = "भगवती ऑटो इलेक्ट्रिकल्स"
SHOP_LOCATION = "वाळूज, छ. संभाजीनगर"
SHOP_PHONE1 = "8010999654"
SHOP_PHONE2 = "9860010083"


def build_header(page_title="", on_backup_click=None):
    """सगळ्या views च्या वरती दाखवायचा shop header.
    वेगळी फाईल असल्यामुळे header मध्ये error आली तरी बाकी app crash होणार नाही."""

    try:
        title_col = ft.Column(
            [
                ft.Text(SHOP_NAME, size=20, weight="bold", color="#00ffaa"),
                ft.Text(SHOP_LOCATION, size=11, color="#94a3b8"),
            ],
            spacing=2,
        )

        phone_col = ft.Column(
            [
                ft.Row([
                    ft.Text("📞", size=12),
                    ft.Text(SHOP_PHONE1, size=13, weight="bold", color="white"),
                ], spacing=4),
                ft.Row([
                    ft.Text("📞", size=12),
                    ft.Text(SHOP_PHONE2, size=13, color="#94a3b8"),
                ], spacing=4),
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.END,
        )

        center_col = ft.Column(
            [
                ft.Text(
                    "Auto Electricals | Service & Repair | Rewinding",
                    size=11, color="#64748b", italic=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

        backup_btn = ft.Container()
        if on_backup_click:
            backup_btn = ft.IconButton(
                icon=ft.Icons.BACKUP_OUTLINED,
                icon_color="#00ffaa",
                tooltip="Backup Now",
                on_click=on_backup_click,
            )

        return ft.Container(
            content=ft.Row(
                [
                    title_col,
                    center_col,
                    ft.Row([backup_btn, phone_col], spacing=8),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor="#0e0e16",
            padding=ft.Padding.symmetric(horizontal=20, vertical=12),
            border=ft.Border(bottom=ft.BorderSide(1, "#1a1a26")),
        )

    except Exception:
        # Header मध्ये काहीही चुकलं तरी app चालू राहावं म्हणून fallback
        return ft.Container(
            content=ft.Text(SHOP_NAME, size=16, color="#00ffaa"),
            padding=10, bgcolor="#0e0e16",
        )
