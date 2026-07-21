"""
============================================================================
INVENTORY WORKSPACE — Part Master + Stock-In एकाच Page वर, Tabs ने
============================================================================
Flet 0.85 फिक्स: जुन्या ft.Tab(content=...) ऐवजी आता Tabs चं API बदललंय —
Tab फक्त label/icon साठी, content TabBarView मध्ये वेगळं द्यावं लागतं.
============================================================================
"""
import flet as ft
from inventory_master_view import InventoryMasterView
from stock_in_view import StockInView


class InventoryWorkspaceView(ft.Container):
    def __init__(self):
        super().__init__(expand=True, bgcolor="#050508")

        self.master_view = InventoryMasterView()
        self.stock_in_view = StockInView()

        self.tabs = ft.Tabs(
            length=2,
            selected_index=0,
            animation_duration=200,
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="📦 Part Master"),
                            ft.Tab(label="📥 Stock-In"),
                        ],
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            self.master_view,
                            self.stock_in_view,
                        ],
                    ),
                ],
            ),
        )
        self.content = self.tabs