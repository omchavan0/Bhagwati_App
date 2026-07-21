import flet as ft
import auth_service


class AuthView(ft.Container):
    """ॲप उघडल्यावर PIN च्याही आधी दिसणारी Login/Signup स्क्रीन (Cloud Auth
    सेट-अप असेल तरच दिसते — नसेल तर main.py थेट पुढे जातो, local-only mode)."""

    def __init__(self, on_success):
        super().__init__(expand=True, bgcolor="#050508", alignment=ft.Alignment(0, 0))
        self.on_success = on_success
        self.mode = "login"  # "login" | "signup" | "reset"

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa",
             "border_radius": 8, "width": 320, "height": 52}

        self.email = ft.TextField(label="📧 Email", **S)
        self.password = ft.TextField(label="🔒 Password", password=True, can_reveal_password=True, **S)
        self.confirm_password = ft.TextField(label="🔒 Password पुन्हा टाका", password=True,
                                              can_reveal_password=True, visible=False, **S)
        self.display_name = ft.TextField(label="👤 तुमचं नाव", visible=False, **S)
        self.mobile = ft.TextField(label="📱 Mobile Number", visible=False, **S)

        self.msg_text = ft.Text("", size=13, visible=False, text_align=ft.TextAlign.CENTER, width=320)

        self.primary_btn = ft.ElevatedButton(
            "Login", bgcolor="#00ffaa", color="black", width=320, height=52,
            on_click=self.handle_primary_action,
        )
        self.switch_text = ft.TextButton(
            "नवीन अकाउंट बनवा", style=ft.ButtonStyle(color="#00aaff"),
            on_click=lambda e: self.switch_mode("signup"),
        )
        self.forgot_text = ft.TextButton(
            "Password विसरलात?", style=ft.ButtonStyle(color="#94a3b8"),
            on_click=lambda e: self.switch_mode("reset"),
        )
        self.back_to_login = ft.TextButton(
            "← Login कडे परत जा", style=ft.ButtonStyle(color="#00aaff"),
            visible=False, on_click=lambda e: self.switch_mode("login"),
        )

        self.form_column = ft.Column(
            [
                ft.Text("🔐", size=44),
                ft.Text("Bhagwati Auto App", size=20, weight="bold", color="#00ffaa"),
                ft.Text("Login करून पुढे चला", size=12, color="#94a3b8"),
                ft.Container(height=10),
                self.display_name,
                self.email,
                self.mobile,
                self.password,
                self.confirm_password,
                self.msg_text,
                self.primary_btn,
                ft.Row([self.switch_text, self.forgot_text], alignment=ft.MainAxisAlignment.CENTER),
                self.back_to_login,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )

        self.content = self.form_column

    # ======================================================================
    def _show_msg(self, text, color):
        self.msg_text.value = text
        self.msg_text.color = color
        self.msg_text.visible = True
        if self.page:
            self.msg_text.update()

    def switch_mode(self, mode):
        self.mode = mode
        self.msg_text.visible = False

        if mode == "login":
            self.display_name.visible = False
            self.mobile.visible = False
            self.confirm_password.visible = False
            self.password.visible = True
            self.primary_btn.text = "Login"
            self.switch_text.text = "नवीन अकाउंट बनवा"
            self.switch_text.visible = True
            self.forgot_text.visible = True
            self.back_to_login.visible = False
        elif mode == "signup":
            self.display_name.visible = True
            self.mobile.visible = True
            self.confirm_password.visible = True
            self.password.visible = True
            self.primary_btn.text = "Sign Up"
            self.switch_text.text = "आधीच अकाउंट आहे? Login करा"
            self.switch_text.visible = True
            self.switch_text.on_click = lambda e: self.switch_mode("login")
            self.forgot_text.visible = False
            self.back_to_login.visible = False
        elif mode == "reset":
            self.display_name.visible = False
            self.mobile.visible = False
            self.password.visible = False
            self.confirm_password.visible = False
            self.primary_btn.text = "Reset Link पाठवा"
            self.switch_text.visible = False
            self.forgot_text.visible = False
            self.back_to_login.visible = True

        if self.page:
            self.update()

    # ======================================================================
    def handle_primary_action(self, e):
        if self.mode == "login":
            self._do_login()
        elif self.mode == "signup":
            self._do_signup()
        elif self.mode == "reset":
            self._do_reset()

    def _do_login(self):
        email = (self.email.value or "").strip()
        password = self.password.value or ""
        ok, msg = auth_service.login(email, password)
        self._show_msg(msg, "#00ffaa" if ok else "#ff4444")
        if ok:
            self.on_success()

    def _do_signup(self):
        email = (self.email.value or "").strip()
        password = self.password.value or ""
        confirm = self.confirm_password.value or ""
        name = (self.display_name.value or "").strip()
        mobile = (self.mobile.value or "").strip()

        if password != confirm:
            self._show_msg("⚠️ दोन्ही Password जुळत नाहीत.", "#ff4444")
            return

        ok, msg = auth_service.sign_up(email, password, display_name=name, mobile=mobile)
        self._show_msg(msg, "#00ffaa" if ok else "#ff4444")
        if ok:
            self.on_success()

    def _do_reset(self):
        email = (self.email.value or "").strip()
        ok, msg = auth_service.send_password_reset(email)
        self._show_msg(msg, "#00ffaa" if ok else "#ff4444")
