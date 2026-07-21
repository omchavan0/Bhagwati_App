import flet as ft
from database import init_db, is_pin_set, get_due_soon, manual_backup
from inventory_workspace_view import InventoryWorkspaceView
from sidebar import SideBarMenu
from tx_list import TransactionListPanel
from udhaari_view import UdhaariView
from report_view import ReportView
from expense_view import ExpenseView
from work_view import WorkView
from lookup_view import LookupView
from pnl_dashboard_view import PnLDashboardView
from clients_view import ClientsView
from company_settings_view import CompanySettingsView
from customer_master_view import CustomerMasterView
from labour_master_view import LabourMasterView 
from gst_billing_view import GSTBillingView
from purchase_view import PurchaseView
from finance_view import FinanceView
from inventory_view import InventoryView
from pin_lock import PinLockScreen, PinSettingsDialog
from header import build_header
from gst_returns_view import GSTReturnsView   # 👈 नवीन
import auth_service
from auth_view import AuthView
import sync_engine
import cloud_backup 
cloud_backup.start_background_backup()
from inventory_master_view import InventoryMasterView
from stock_in_view import StockInView
from inventory_sheet_view import InventorySheetView
import os, sys, certifi

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

try:
    from header import build_header
except Exception:
    def build_header():
        return ft.Container(height=0)

init_db()


def main(page: ft.Page):
    page.title = "Bhagwati Udhaari Hisaab"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#050508"
    page.window_maximized = True
    page.padding = 0

    # ==================================================================
    # मुख्य ॲप तयार करून दाखवणारं फंक्शन (PIN बरोबर असल्यावरच कॉल होतं)
    # ==================================================================
    def show_main_app():
        page.controls.clear()

        udhaari_view_holder = {"view": None}

        def refresh_list():
            list_panel.load_data()

        def handle_record_select(record_id):
            if udhaari_view_holder["view"] is None:
                handle_menu_switch("Udhaari")
            udhaari_view_holder["view"].load_record(record_id)
            page.update()

        def handle_backup_click(e):
            try:
                path = manual_backup()
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"✅ Backup सेव्ह झाला: {path}", color="black"),
                    bgcolor="#00ffaa",
                )
                page.snack_bar.open = True
                page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"❌ Backup Error: {ex}", color="white"),
                    bgcolor="#ff4444",
                )
                page.snack_bar.open = True
                page.update()

        list_panel = TransactionListPanel(on_select_callback=handle_record_select)
        right_container = ft.Container(expand=True)

        def handle_menu_switch(label):

            
            if label == "GSTBilling":              # 👈 नवीन ब्लॉक
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = GSTBillingView(refresh_callback=refresh_list)
            elif label == "GSTReturns":               # 👈 नवीन ब्लॉक
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = GSTReturnsView()  
            elif label == "InventoryMaster":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = InventoryMasterView()
            elif label == "StockIn":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = StockInView(refresh_callback=refresh_list)
            elif label == "InventorySheet":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = InventorySheetView()  
            elif label == "Inventory":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = InventoryWorkspaceView()        
            elif label == "Purchase":              # 👈 नवीन ब्लॉक
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = PurchaseView(refresh_callback=refresh_list)       
            elif label == "P&L":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = PnLDashboardView()    
            elif label == "Udhaari":
                list_panel.visible = True
                new_view = UdhaariView(refresh_callback=refresh_list)
                udhaari_view_holder["view"] = new_view
                right_container.content = new_view
            elif label == "Reports":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = ReportView()
            elif label == "Expenses":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = ExpenseView()
            elif label == "DailyWork":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = WorkView()
            elif label == "Clients":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = ClientsView(on_edit_record=handle_record_select)
            elif label == "CompanySettings":          # 👈 नवीन ब्लॉक
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = CompanySettingsView()   
            elif label == "Customers":              # 👈 नवीन ब्लॉक
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = CustomerMasterView()  
            elif label == "LabourMaster":            # 👈 नवीन ब्लॉक
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = LabourMasterView()        
            elif label == "Finance":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = FinanceView()
            elif label == "Lookup":
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = LookupView(on_edit_record=handle_record_select)
            else:
                list_panel.visible = False
                udhaari_view_holder["view"] = None
                right_container.content = ft.Container(
                    content=ft.Column(
                        [ft.Text(f"{label} Section", color="white", size=20)],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        expand=True,
                    ),
                    expand=True,
                )

            page.update()

        def handle_settings_click():
            dialog = PinSettingsDialog(page)
            dialog.open()

        # सुरुवातीला Udhaari व्ह्यू लोड कर
        initial_view = UdhaariView(refresh_callback=refresh_list)
        udhaari_view_holder["view"] = initial_view
        right_container.content = initial_view

        sidebar = SideBarMenu(on_menu_change=handle_menu_switch, on_settings_click=handle_settings_click)

        try:
            app_header = build_header(on_backup_click=handle_backup_click)
        except Exception:
            app_header = ft.Container(height=0)

        page.add(
            ft.Column(
                [
                    app_header,
                    ft.Row(
                        [
                            sidebar,
                            list_panel,
                            right_container,
                        ],
                        expand=True,
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                ],
                spacing=0,
                expand=True,
            )
        )
        page.update()

        list_panel.load_data()
        show_due_alerts_if_any()

    # ==================================================================
    # Due Date Alert — app उघडताच, ज्यांची due date जवळ आली/उलटली अशा
    # नोंदी असतील तर एक पॉपअप दाखवतो
    # ==================================================================
    def show_due_alerts_if_any():
        due_soon = get_due_soon(within_days=3)
        if not due_soon:
            return

        alert_list = ft.ListView(spacing=8, height=300)
        for item in due_soon:
            row = item["row"]
            days_left = item["days_left"]
            if item["is_overdue"]:
                tag = f"⚠️ {abs(days_left)} दिवस उलटले"
                tag_color = "#ff4444"
            elif days_left == 0:
                tag = "🔴 आजच Due आहे"
                tag_color = "#ff8800"
            else:
                tag = f"🟡 {days_left} दिवसांत Due"
                tag_color = "#ff8800"

            alert_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(f"{row['name']} — ₹{row['due_amt']:.0f}", weight="bold", color="white"),
                            ft.Text(f"Due Date: {row['due_date']}", size=12, color="#94a3b8"),
                            ft.Text(tag, size=12, color=tag_color, weight="bold"),
                        ],
                        spacing=2,
                    ),
                    bgcolor="#161622", padding=10, border_radius=8,
                )
            )

        def close_alert(e):
            alert_dialog.open = False
            page.update()

        alert_dialog = ft.AlertDialog(
            title=ft.Text(f"⏰ {len(due_soon)} नोंदींची Due Date जवळ आली आहे"),
            content=ft.Container(content=alert_list, width=420),
            actions=[ft.TextButton("Close", on_click=close_alert)],
        )

        page.overlay.append(alert_dialog)
        alert_dialog.open = True
        page.update()

    # ==================================================================
    # ॲप सुरू होण्याचा क्रम:
    # 1. Cloud Auth सेट-अप असेल आणि आधीचं session नसेल -> Login/Signup दाखव
    # 2. Login झाल्यावर (किंवा Auth सेट-अपच नसेल तर लगेच) -> Background
    #    Cloud Sync सुरू कर
    # 3. PIN लॉक असेल तर PIN स्क्रीन, नाहीतर थेट मुख्य ॲप
    # ==================================================================
    def start_local_flow():
        if is_pin_set():
            def on_pin_success():
                page.controls.clear()
                show_main_app()

            page.add(PinLockScreen(on_success=on_pin_success))
            page.update()
        else:
            show_main_app()

    def after_auth():
        sync_engine.start_background_sync()  # इंटरनेट/credentials नसतील तरी silently skip होतं
        start_local_flow()

    if auth_service.is_auth_available():
        saved_session = auth_service.get_saved_session()
        if saved_session:
            after_auth()
        else:
            def on_auth_success():
                page.controls.clear()
                after_auth()

            page.add(AuthView(on_success=on_auth_success))
            page.update()
    else:
        # Cloud Auth कॉन्फिगर केलेलं नाहीये -> ॲप नेहमीसारखं local-only चालेल
        after_auth()


ft.app(target=main)
