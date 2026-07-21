import flet as ft
from database import set_pin, verify_pin, is_pin_set, remove_pin


class PinLockScreen(ft.Container):
    """ॲप उघडल्यावर सगळ्यात आधी दिसणारी PIN-एंट्री स्क्रीन.
    योग्य PIN टाकल्यावर on_success() कॉल होतं, जे मुख्य ॲप दाखवतं."""

    def __init__(self, on_success):
        super().__init__(
            expand=True,
            bgcolor="#050508",
            alignment=ft.Alignment(0, 0),
        )
        self.on_success = on_success
        self.pin_input = ft.TextField(
            label="PIN टाका",
            password=True,
            can_reveal_password=True,
            width=260,
            height=55,
            text_align=ft.TextAlign.CENTER,
            border_color="#00ffaa",
            focused_border_color="#00ffaa",
            on_submit=self.check_pin,
            autofocus=True,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.error_text = ft.Text("", color="#ff4444", size=13, visible=False)

        self.content = ft.Column(
            [
                ft.Text("🔒", size=50),
                ft.Text("Bhagwati Udhaari Hisaab", size=18, weight="bold", color="#00ffaa"),
                ft.Text("ॲप उघडण्यासाठी PIN टाका", size=13, color="#94a3b8"),
                ft.Container(height=10),
                self.pin_input,
                self.error_text,
                ft.ElevatedButton(
                    "Unlock", bgcolor="#00ffaa", color="black", width=260, height=50,
                    on_click=self.check_pin,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )

    def check_pin(self, e):
        entered = (self.pin_input.value or "").strip()
        if verify_pin(entered):
            self.on_success()
        else:
            self.error_text.value = "❌ चुकीचा PIN. परत प्रयत्न करा."
            self.error_text.visible = True
            self.pin_input.value = ""
            self.update()


class PinSettingsDialog:
    """Sidebar च्या profile icon वरून उघडणारा PIN सेट / बदल / रिमूव्ह डायलॉग.
    वापर: dialog = PinSettingsDialog(page); dialog.open()"""

    def __init__(self, page):
        self.page = page

        self.current_pin_field = ft.TextField(
            label="सध्याचा PIN", password=True, can_reveal_password=True, visible=False
        )
        self.new_pin_field = ft.TextField(label="नवीन PIN (4-6 आकडे)", password=True, can_reveal_password=True)
        self.confirm_pin_field = ft.TextField(label="नवीन PIN परत टाका", password=True, can_reveal_password=True)
        self.msg_text = ft.Text("", size=12, visible=False)

        self.remove_btn = ft.TextButton(
            "PIN Lock बंद करा", style=ft.ButtonStyle(color="#ff4444"),
            on_click=self.handle_remove, visible=is_pin_set(),
        )

        self.dialog = ft.AlertDialog(
            title=ft.Text("🔒 PIN Lock Settings"),
            content=ft.Column(
                [
                    ft.Text(
                        "PIN सेट केलं तर ॲप उघडताना ते टाकावं लागेल." if not is_pin_set()
                        else "PIN आधीच सेट आहे. बदलण्यासाठी सध्याचा PIN टाका.",
                        size=12, color="#94a3b8",
                    ),
                    self.current_pin_field,
                    self.new_pin_field,
                    self.confirm_pin_field,
                    self.msg_text,
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                self.remove_btn,
                ft.TextButton("Close", on_click=self.close),
                ft.ElevatedButton("Save", bgcolor="#00ffaa", color="black", on_click=self.handle_save),
            ],
        )
        self.current_pin_field.visible = is_pin_set()

    def open(self):
        if self.dialog not in self.page.overlay:
            self.page.overlay.append(self.dialog)
        self.dialog.open = True
        self.page.update()

    def close(self, e=None):
        self.dialog.open = False
        self.page.update()

    def _show_msg(self, text, color):
        self.msg_text.value = text
        self.msg_text.color = color
        self.msg_text.visible = True
        self.dialog.update()

    def handle_save(self, e):
        if is_pin_set():
            if not verify_pin((self.current_pin_field.value or "").strip()):
                self._show_msg("⚠️ सध्याचा PIN चुकीचा आहे.", "#ff4444")
                return

        new_pin = (self.new_pin_field.value or "").strip()
        confirm_pin = (self.confirm_pin_field.value or "").strip()

        if not new_pin.isdigit() or not (4 <= len(new_pin) <= 6):
            self._show_msg("⚠️ PIN फक्त 4-6 आकड्यांचा असावा.", "#ff4444")
            return
        if new_pin != confirm_pin:
            self._show_msg("⚠️ दोन्ही PIN जुळत नाहीत.", "#ff4444")
            return

        set_pin(new_pin)
        self._show_msg("✅ PIN यशस्वीरित्या सेव्ह झाला.", "#00ffaa")
        self.current_pin_field.visible = True
        self.remove_btn.visible = True
        self.new_pin_field.value = ""
        self.confirm_pin_field.value = ""
        self.dialog.update()

    def handle_remove(self, e):
        if is_pin_set() and not verify_pin((self.current_pin_field.value or "").strip()):
            self._show_msg("⚠️ PIN काढण्यासाठी आधी सध्याचा बरोबर PIN टाका.", "#ff4444")
            return
        remove_pin()
        self._show_msg("🔓 PIN Lock बंद केलं.", "#00ffaa")
        self.remove_btn.visible = False
        self.current_pin_field.visible = False
        self.dialog.update()
