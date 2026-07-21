from importlib.resources import path
import os
import shutil
import flet as ft
from database import get_company_settings, update_company_settings


LOGO_DIR = "assets/logo"


class CompanySettingsView(ft.Container):
    """दुकानाची Business Profile — GSTIN, Bank, Logo, Terms इ.
    Singleton settings असल्यामुळे इथे List नाही, फक्त एकच फॉर्म — Save
    दाबल्यावर db_company.update_company_settings() कॉल होतो.

    टीप: ft.FilePicker हा control काही Flet client versions मध्ये
    "Unknown control: FilePicker" एरर देतो (pip मधलं flet आणि desktop
    client version वेगळे असतील तर). त्यामुळे Logo निवडण्यासाठी इथे
    FilePicker ऐवजी मॅन्युअली फाईल-पाथ टाईप करायची पद्धत वापरलीये —
    कमी सोयीस्कर, पण कधीही क्रॅश होणार नाही (fail-safe)."""

    def __init__(self):
        super().__init__(expand=True, padding=25, bgcolor="#050508")

        S = {"border_color": "#00ffaa", "focused_border_color": "#00ffaa", "border_radius": 8}
        self.logo_path = None

        # ---------------- Logo (FilePicker ऐवजी मॅन्युअल Path) ----------------
        self.logo_preview = ft.Container(
            width=90, height=90, border_radius=10, bgcolor="#161622",
            alignment=ft.Alignment(0, 0),
            content=ft.Text("🏢", size=32),
        )
        self.logo_path_field = ft.TextField(
            label="🖼️ Logo फाईलचा पूर्ण Path (उदा. C:\\Users\\dell\\Pictures\\logo.png)",
            height=52, expand=True, on_blur=self._logo_path_typed, **S,
        )

        # ---------------- Basic Details ----------------
        self.f_company_name = ft.TextField(label="🏢 Company Name *", height=52, **S)
        self.f_proprietor = ft.TextField(label="👤 Proprietor Name", height=52, **S)
        self.f_gstin = ft.TextField(label="🧾 GSTIN (रिकामं ठेवलं तर Unregistered)", height=52, **S)
        self.f_pan = ft.TextField(label="🪪 PAN", height=52, **S)
        self.f_mobile = ft.TextField(label="📱 Mobile", height=52, **S)
        self.f_email = ft.TextField(label="📧 Email", height=52, **S)
        self.f_website = ft.TextField(label="🌐 Website", height=52, **S)

        # ---------------- Address ----------------
        self.f_address = ft.TextField(label="📍 Address", height=52, **S)
        self.f_city = ft.TextField(label="🏙️ City", height=52, **S)
        self.f_state = ft.Dropdown(
            label="राज्य (State)", height=52, value="Maharashtra",
            options=[ft.dropdown.Option("Maharashtra"), ft.dropdown.Option("Other State")],
            **S,
        )
        self.f_state.on_change = self._on_state_change
        self.f_state_code = ft.TextField(label="State Code", height=52, value="27", **S)
        self.f_pin_code = ft.TextField(label="PIN Code", height=52, **S)

        # ---------------- Bank Details ----------------
        self.f_bank_name = ft.TextField(label="🏦 Bank Name", height=52, **S)
        self.f_account_number = ft.TextField(label="🔢 Account Number", height=52, **S)
        self.f_ifsc = ft.TextField(label="IFSC Code", height=52, **S)
        self.f_upi_id = ft.TextField(label="📲 UPI ID", height=52, **S)

        # ---------------- Invoice Settings ----------------
        self.f_invoice_prefix = ft.TextField(label="🔖 Invoice Prefix (उदा. INV)", height=52, value="INV", **S)
        self.f_fy_start_month = ft.Dropdown(
            label="Financial Year सुरू होणारा महिना", height=52, value="4",
            options=[ft.dropdown.Option(str(m), text=name) for m, name in [
                (1, "January"), (4, "April (भारतीय FY)"), (7, "July"), (10, "October"),
            ]], **S,
        )

        # ---------------- Terms / Declaration ----------------
        self.f_terms = ft.TextField(label="📜 Terms & Conditions", multiline=True, height=90, **S)
        self.f_declaration = ft.TextField(
            label="✅ Declaration (बिलावर छापली जाणारी ओळ)", multiline=True, height=70,
            value="We declare that this invoice shows the actual price of the goods described "
                  "and that all particulars are true and correct.", **S,
        )

        self.status_text = ft.Text("", size=13, visible=False)
        self.save_btn = ft.ElevatedButton(
            "💾 Save Company Settings", bgcolor="#00ffaa", color="black",
            height=52, expand=True, on_click=self.handle_save,
        )

        self.content = ft.Column(
            [
                ft.Text("⚙️ Company Settings / Business Profile", size=24, weight="bold", color="#00ffaa"),
                ft.Text("इथली माहिती सगळ्या GST Invoice, Estimate आणि Reports वर आपोआप दिसेल.",
                        size=12, color="#94a3b8"),
                self.status_text,
                ft.Container(height=8),

                ft.Row([self.logo_preview, self.logo_path_field], spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=6),

                ft.Text("मूळ माहिती", size=14, weight="bold", color="white"),
                ft.Row([self.f_company_name, self.f_proprietor], spacing=10),
                ft.Row([self.f_gstin, self.f_pan], spacing=10),
                ft.Row([self.f_mobile, self.f_email], spacing=10),
                self.f_website,

                ft.Divider(color="#1a1a26"),
                ft.Text("पत्ता (Address)", size=14, weight="bold", color="white"),
                self.f_address,
                ft.Row([self.f_city, self.f_state], spacing=10),
                ft.Row([self.f_state_code, self.f_pin_code], spacing=10),

                ft.Divider(color="#1a1a26"),
                ft.Text("Bank Details", size=14, weight="bold", color="white"),
                ft.Row([self.f_bank_name, self.f_account_number], spacing=10),
                ft.Row([self.f_ifsc, self.f_upi_id], spacing=10),

                ft.Divider(color="#1a1a26"),
                ft.Text("Invoice Settings", size=14, weight="bold", color="white"),
                ft.Row([self.f_invoice_prefix, self.f_fy_start_month], spacing=10),

                ft.Divider(color="#1a1a26"),
                ft.Text("Terms / Declaration", size=14, weight="bold", color="white"),
                self.f_terms,
                self.f_declaration,

                ft.Container(height=10),
                self.save_btn,
                ft.Container(height=20),
            ],
            spacing=12, scroll="auto", expand=True,
        )

    # ==================================================================
    def did_mount(self):
        # टीप: FilePicker overlay-append करायची गरजच उरली नाही (काढून टाकलं) —
        # त्यामुळे "Unknown control: FilePicker" एरर आता कधीही येणार नाही.
        self.refresh()

    def _on_state_change(self, e):
        # Maharashtra निवडलं की state_code आपोआप 27 भरतो; Other असेल तर
        # user स्वतः टाकू शकतो (rigid ठेवत नाही, कारण "Other State" कुठलंही असू शकतं)
        if self.f_state.value == "Maharashtra":
            self.f_state_code.value = "27"
            if self.page:
                self.f_state_code.update()

    def refresh(self):
        row = get_company_settings()
        if not row:
            self.update()
            return

        self.f_company_name.value = row["company_name"] or ""
        self.f_proprietor.value = row["proprietor_name"] or ""
        self.f_gstin.value = row["gstin"] or ""
        self.f_pan.value = row["pan"] or ""
        self.f_mobile.value = row["mobile"] or ""
        self.f_email.value = row["email"] or ""
        self.f_website.value = row["website"] or ""
        self.f_address.value = row["address"] or ""
        self.f_city.value = row["city"] or ""
        self.f_state.value = row["state"] or "Maharashtra"
        self.f_state_code.value = row["state_code"] or "27"
        self.f_pin_code.value = row["pin_code"] or ""
        self.f_bank_name.value = row["bank_name"] or ""
        self.f_account_number.value = row["account_number"] or ""
        self.f_ifsc.value = row["ifsc"] or ""
        self.f_upi_id.value = row["upi_id"] or ""
        self.f_invoice_prefix.value = row["invoice_prefix"] or "INV"
        self.f_fy_start_month.value = str(row["financial_year_start_month"] or 4)
        self.f_terms.value = row["terms_conditions"] or ""
        self.f_declaration.value = row["declaration"] or self.f_declaration.value

        self.logo_path = row["logo_path"] if "logo_path" in row.keys() else None
        self.logo_path_field.value = self.logo_path or ""
        self._refresh_logo_preview()

        self.update()

    def _refresh_logo_preview(self):
        if self.logo_path and os.path.exists(self.logo_path):
           try:
            fit_value = ft.ImageFit.COVER
           except AttributeError:
            fit_value = "cover"   # जुन्या/वेगळ्या Flet version मध्ये enum ऐवजी plain string चालतं
           try:
            self.logo_preview.content = ft.Image(
                src=self.logo_path, width=90, height=90, fit=fit_value,
                border_radius=10,
            )
           except Exception:
            # Image control कुठल्याही कारणाने चुकलं तरी app crash न होता 🏢 दाखवत राहील
            self.logo_preview.content = ft.Text("🏢", size=32)
        else:
           self.logo_preview.content = ft.Text("🏢", size=32)

    # ==================================================================
    def _logo_path_typed(self, e):
        path = (self.logo_path_field.value or "").strip().strip('"')
        if not path:
            # 👈 यूजरने Path डिलीट केला -> Logo पूर्णपणे काढून टाकायचं
            self.logo_path = None
            self._refresh_logo_preview()
            self._show_status("🗑️ Logo काढलं — Save दाबून पक्कं कर.", "#ff8800")
            if self.page:
                self.update()
            return

        if not os.path.exists(path):
            self._show_status("⚠️ ती फाईल सापडली नाही — Path तपासा.", "#ff8800")
            return

        try:
            os.makedirs(LOGO_DIR, exist_ok=True)
            ext = os.path.splitext(path)[1] or ".png"
            dest_path = os.path.join(LOGO_DIR, f"company_logo{ext}")
            shutil.copy2(path, dest_path)
            self.logo_path = dest_path
            self._refresh_logo_preview()
            self._show_status("✅ Logo अपडेट झालं.", "#00ffaa")
            if self.page:
                self.update()
        except Exception as ex:
            self._show_status(f"❌ Logo अपलोड एरर: {ex}", "#ff4444")

    # ==================================================================
    def _show_status(self, msg, color):
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        if self.page:
            self.status_text.update()

    def handle_save(self, e):
        name = (self.f_company_name.value or "").strip()
        if not name:
            self._show_status("⚠️ Company Name भरा.", "#ff4444")
            return

        try:
            fy_month = int(self.f_fy_start_month.value or 4)
        except ValueError:
            fy_month = 4

        update_company_settings(
            company_name=name,
            proprietor_name=(self.f_proprietor.value or "").strip(),
            gstin=(self.f_gstin.value or "").strip().upper(),
            pan=(self.f_pan.value or "").strip().upper(),
            mobile=(self.f_mobile.value or "").strip(),
            email=(self.f_email.value or "").strip(),
            website=(self.f_website.value or "").strip(),
            address=(self.f_address.value or "").strip(),
            city=(self.f_city.value or "").strip(),
            state=self.f_state.value or "Maharashtra",
            state_code=(self.f_state_code.value or "27").strip(),
            pin_code=(self.f_pin_code.value or "").strip(),
            bank_name=(self.f_bank_name.value or "").strip(),
            account_number=(self.f_account_number.value or "").strip(),
            ifsc=(self.f_ifsc.value or "").strip().upper(),
            upi_id=(self.f_upi_id.value or "").strip(),
            invoice_prefix=(self.f_invoice_prefix.value or "INV").strip().upper(),
            financial_year_start_month=fy_month,
            terms_conditions=(self.f_terms.value or "").strip(),
            declaration=(self.f_declaration.value or "").strip(),
            logo_path=self.logo_path,
        )

        self._show_status("✅ Company Settings सेव्ह झालं.", "#00ffaa")