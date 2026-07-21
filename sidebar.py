import flet as ft

class SideBarMenu(ft.Container):
    def __init__(self, on_menu_change, on_settings_click=None):
        super().__init__(
            width=80, # 👈 नाव बसण्यासाठी थोडी रुंदी वाढवली
            expand=False,
            bgcolor="#0b0b12",
            padding=ft.Padding.only(top=20, bottom=15),
            border=ft.Border(right=ft.BorderSide(1, "#1a1a26"))
        )
        self.on_menu_change = on_menu_change
        self.on_settings_click = on_settings_click

        def sidebar_item(icon_text, label, selected=False):
            return ft.Container(
                content=ft.Column([ 
                    ft.Text(icon_text, size=22, color="#00ffaa" if selected else "#64748b", text_align=ft.TextAlign.CENTER),
                    ft.Text(label, size=10, color="#00ffaa" if selected else "#64748b", weight="bold", text_align=ft.TextAlign.CENTER),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                width=70, 
                height=70, # 👈 आयकॉन आणि नाव व्यवस्थित दिसण्यासाठी जागा दिली
                border_radius=12,
                bgcolor="#12251e" if selected else "transparent",
                border=ft.Border.all(1.5, "#00ffaa" if selected else "transparent"),
                on_click=lambda e: self.menu_clicked(e.control, label),
                data=label
            )

        self.menu_items_column = ft.Column([
            sidebar_item("🤝", "Udhaari", selected=True),
            sidebar_item("📉", "Expenses"),
            sidebar_item("📝", "DailyWork"),
            sidebar_item("🏢", "Clients"),
            sidebar_item("📦", "Inventory"),
            sidebar_item("📊", "InventorySheet"),
            sidebar_item("💰", "Finance"),
            sidebar_item("🧮", "GSTBilling"),
            sidebar_item("📑", "GSTReturns"),
            sidebar_item("📥", "Purchase"),
            sidebar_item("💎", "P&L"),
            sidebar_item("🔍", "Lookup"),
            sidebar_item("📊", "Reports"),
            sidebar_item("👥", "Customers"), 
            sidebar_item("🔧", "LabourMaster"),
            sidebar_item("⚙️", "CompanySettings"),
        ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
           scroll=ft.ScrollMode.AUTO, expand=True)

        profile_icon = ft.Container(
            content=ft.Text("👤", size=18, color="#00ffaa"),
            bgcolor="#161622",
            width=50,
            height=50,
            border_radius=25,
            alignment=ft.Alignment(0, 0),
            border=ft.Border.all(1, "#1a1a26"),
            on_click=lambda e: self.on_settings_click() if self.on_settings_click else None,
            tooltip="Settings / PIN Lock",
        )

        self.content = ft.Column([
            self.menu_items_column,
            profile_icon
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)

    def menu_clicked(self, clicked_container, selected_label):
        for item in self.menu_items_column.controls:
            if isinstance(item, ft.Container):
                is_selected = item.data == selected_label
                item.bgcolor = "#12251e" if is_selected else "transparent"
                item.Border = ft.Border.all(1.5, "#00ffaa" if is_selected else "transparent")
                # आयकॉन आणि नाव दोन्हीचा कलर बदलण्यासाठी:
                item.content.controls[0].color = "#00ffaa" if is_selected else "#64748b"
                item.content.controls[1].color = "#00ffaa" if is_selected else "#64748b"
                item.update()
        
        self.on_menu_change(selected_label)
