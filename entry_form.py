import flet as ft

class DetailEntryForm(ft.Container):
    def __init__(self):
        super().__init__(
            expand=True,
            bgcolor="#09090f",
            padding=25, #     
        )

        def custom_input(lbl, hint="", icon=None, expand=False):
            return ft.TextField(
                label=lbl,
                hint_text=hint,
                prefix_icon=icon,
                border_color="#161622",
                focused_border_color="#00ffaa", #    
                bgcolor="#11111a",
                text_size=14,
                height=48,
                expand=expand,
                label_style=ft.TextStyle(size=12, color="#64748b"),
                text_style=ft.TextStyle(color="white")
            )

        self.c_name = custom_input("Customer Name *", icon=ft.Icons.PERSON)
        self.c_phone = custom_input("Phone Number *", icon=ft.Icons.PHONE)
        self.c_veh = custom_input("Vehicle", icon=ft.Icons.DIRECTIONS_CAR, expand=True)
        self.c_vno = custom_input("Vehicle Number", icon=ft.Icons.PIN, expand=True)
        
        self.amount = custom_input("Amount () *", icon=ft.Icons.ATTACH_MONEY, expand=True)
        self.status = ft.Dropdown(
            label="Payment Status",
            options=[ft.dropdown.Option("Full Paid"), ft.dropdown.Option("Partial"), ft.dropdown.Option("Unpaid")],
            bgcolor="#11111a", border_color="#161622", height=48, expand=True,
            label_style=ft.TextStyle(size=12, color="#64748b"), text_style=ft.TextStyle(color="white")
        )
        
        self.address = custom_input("Address", icon=ft.Icons.LOCATION_ON)
        self.tx_date = custom_input("Transaction Date", icon=ft.Icons.CALENDAR_TODAY, expand=True)
        self.due_date = custom_input("Due Date", icon=ft.Icons.CALENDAR_MONTH, expand=True)
        self.notes = custom_input("Notes", hint="Add a note...")

        def mini_summary_box(title, val, color="white"):
            return ft.Container(
                expand=True, padding=12, bgcolor="#11111a", border_radius=10,
                border=ft.Border.all(1, "#161622"),
                content=ft.Column([
                    ft.Text(title, color="#64748b", size=11),
                    ft.Text(val, color=color, size=14, weight="bold")
                ], spacing=2)
            )

        self.summary_row = ft.Row([
            mini_summary_box("Total Amount", " can 32,45,000"),
            mini_summary_box("Paid Amount", " can 15,00,000", "#00ffaa"),
            mini_summary_box("Due Amount", " can 17,45,000", "#ef4444"),
        ], spacing=12)

        form_content = ft.Column([
            ft.Text("Customer Details", color="white", size=20, weight="bold"),
            ft.Text("Add or edit customer information", color="#64748b", size=12),
            ft.Container(height=10),
            
            self.c_name,
            self.c_phone,
            ft.Row([self.c_veh, self.c_vno], spacing=15),
            ft.Row([self.amount, self.status], spacing=15),
            self.address,
            ft.Row([self.tx_date, self.due_date], spacing=15),
            self.notes,
            
            ft.Divider(height=20, color="#161622"),
            ft.Text("Payment Summary", color="#00ffaa", size=13, weight="bold"),
            self.summary_row,
            
            ft.Container(height=10),
            ft.Row([
                ft.TextButton("Cancel", style=ft.ButtonStyle(color="white"), width=100, height=45),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.SAVE, size=18), ft.Text("Save Customer", weight="bold", size=14)], spacing=8),
                    bgcolor="#00ffaa", color="#09090f", height=45, expand=True,
                    #    
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                )
            ], alignment=ft.MainAxisAlignment.END, spacing=15)
            
        ], scroll=ft.ScrollMode.ALWAYS, spacing=15, expand=True)

        self.content = form_content