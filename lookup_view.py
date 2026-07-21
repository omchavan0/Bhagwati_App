import flet as ft
from database import (
    get_all_customer_names,
    get_customer_profile,
    get_all_vehicle_numbers,
    get_vehicle_history,
    search_udhaari,
)
from customer_lookup import smart_search


# ==================================================================
# LookupView — ग्राहकाचं नाव किंवा गाडी नंबर टाकून जुना हिशोब/history
# शोधण्यासाठीची स्क्रीन. database.py (facade) मधल्या functions वापरते.
# ==================================================================
class LookupView(ft.Column):
    def __init__(self, on_edit_record=None):
        # टीप: scroll=AUTO जोडलंय — आधी हा पूर्ण Column स्थिर (fixed) होता,
        # त्यामुळे Smart Search चा निकाल तळाशी गेला की mouse ने वर-खाली
        # सरकवताच येत नव्हता. आता संपूर्ण Lookup स्क्रीन mouse-wheel ने
        # स्क्रोल करता येईल.
        super().__init__(expand=True, spacing=0, scroll=ft.ScrollMode.AUTO)
        self.on_edit_record = on_edit_record
        self.search_mode = "name"  # "name" किंवा "vehicle"

        # ---------------- 🧠 Smart Search (नैसर्गिक भाषेत शोध) ----------------
        # उदा. "MH20AB1234 चा हिशोब दाखव" किंवा "9876543210" किंवा नुसतं नाव
        # टाईप केलं तरी आपोआप ओळखून योग्य शोध चालवतो — वेगळा मोड निवडायची गरज नाही.
        self.smart_search_field = ft.TextField(
            label="🧠 Smart Search — नाव/मोबाईल/गाडी नंबर, कशाही भाषेत टाईप करा",
            hint_text="उदा. 'MH20AB1234 चा हिशोब दाखव' किंवा 'Ramesh Patil'",
            border_color="#00ffaa",
            focused_border_color="#00ffaa",
            color="white",
            bgcolor="#0d0d14",
            on_submit=lambda e: self.handle_smart_search(e),
        )
        self.smart_search_btn = ft.ElevatedButton(
            "🔍 शोध", bgcolor="#00ffaa", color="black",
            on_click=self.handle_smart_search,
        )
        self.smart_search_msg = ft.Text("", size=12, color="#ff8800", visible=False)

        self.search_field = ft.TextField(
            label="ग्राहकाचं नाव टाइप करा...",
            hint_text="उदा. Ramesh Patil",
            border_color="#2a2a3a",
            focused_border_color="#00ffaa",
            color="white",
            bgcolor="#0d0d14",
            on_change=self.handle_search_change,
            autofocus=True,
        )

        self.name_btn = ft.ElevatedButton(
            "👤 नावाने शोधा",
            bgcolor="#00ffaa",
            color="black",
            on_click=lambda e: self.switch_mode("name"),
        )
        self.vehicle_btn = ft.OutlinedButton(
            "🚗 गाडी नंबरने शोधा",
            on_click=lambda e: self.switch_mode("vehicle"),
        )

        self.suggestions_list = ft.ListView(spacing=4, height=200)

        self.profile_area = ft.Container(
            content=ft.Text(
                "वरती नाव किंवा गाडी नंबर टाइप करून शोधा.",
                color="#94a3b8",
                size=14,
            ),
            padding=20,
            expand=True,
        )

        self.controls = [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("🔍 Lookup — जुना हिशोब शोधा", size=22, weight="bold", color="white"),
                        ft.Row([self.smart_search_field, self.smart_search_btn], spacing=10),
                        self.smart_search_msg,
                        ft.Divider(color="#1e1e2a", height=1),
                        ft.Text("किंवा नाव/गाडी नंबरने सुचवणुका बघून शोधा:", size=12, color="#94a3b8"),
                        ft.Row([self.name_btn, self.vehicle_btn], spacing=10),
                        self.search_field,
                        self.suggestions_list,
                    ],
                    spacing=12,
                ),
                padding=20,
                bgcolor="#0a0a12",
            ),
            ft.Divider(color="#1e1e2a", height=1),
            self.profile_area,
        ]

    # --------------------------------------------------------------
    # 🧠 SMART SEARCH — "MH20AB1234 चा हिशोब दाखव" सारखं नैसर्गिक वाक्य
    # घेऊन आपोआप गाडी नंबर/मोबाईल/नाव ओळखून शोध चालवतो
    # --------------------------------------------------------------
    def handle_smart_search(self, e):
        query = (self.smart_search_field.value or "").strip()
        self.smart_search_msg.visible = False
        self.suggestions_list.controls.clear()  # जुन्या सुचवणुका साफ — निकाल आणखी वर दिसतील

        if not query:
            self.smart_search_msg.value = "⚠️ आधी काहीतरी टाईप कर."
            self.smart_search_msg.color = "#ff4444"
            self.smart_search_msg.visible = True
            self.update()
            return

        result = smart_search(query)
        records = result["records"]

        if not records:
            self.profile_area.content = ft.Text(
                f"'{query}' साठी काहीच सापडलं नाही.", color="#ff4444", size=14,
            )
            self.update()
            return

        type_label = {"vehicle": "🚗 गाडी नंबर", "mobile": "📱 मोबाईल", "name": "👤 नाव"}.get(
            result["type"], "🔎 शोध"
        )
        total_due = sum((r["due_amt"] or 0) for r in records)

        records_list = ft.Column(
            [self._record_row(r) for r in records],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        self.profile_area.content = ft.Column(
            [
                ft.Text(f"{type_label}: {result['query']}", size=20, weight="bold", color="white"),
                ft.Text(
                    f"एकूण नोंदी: {len(records)}   |   थकीत: ₹{total_due:.0f}",
                    color="#94a3b8", size=13,
                ),
                ft.Divider(color="#1e1e2a"),
                records_list,
            ],
            spacing=12, expand=True, scroll=ft.ScrollMode.AUTO,
        )
        self.update()

    # --------------------------------------------------------------
    def switch_mode(self, mode):
        self.search_mode = mode
        self.search_field.value = ""
        self.suggestions_list.controls.clear()

        if mode == "name":
            self.search_field.label = "ग्राहकाचं नाव टाइप करा..."
            self.search_field.hint_text = "उदा. Ramesh Patil"
            self.name_btn.bgcolor = "#00ffaa"
            self.name_btn.color = "black"
            self.name_btn.style = None
            self.vehicle_btn.style = ft.ButtonStyle()
        else:
            self.search_field.label = "गाडी नंबर टाइप करा..."
            self.search_field.hint_text = "उदा. MH12AB1234"
            self.name_btn.bgcolor = None
            self.name_btn.color = None

        self.profile_area.content = ft.Text(
            "वरती नाव किंवा गाडी नंबर टाइप करून शोधा.",
            color="#94a3b8",
            size=14,
        )
        self.update()

    # --------------------------------------------------------------
    def handle_search_change(self, e):
        query = (self.search_field.value or "").strip().lower()
        self.suggestions_list.controls.clear()

        if not query:
            self.update()
            return

        if self.search_mode == "name":
            all_names = get_all_customer_names()
            matches = [n for n in all_names if query in n.lower()][:15]
            for name in matches:
                self.suggestions_list.controls.append(
                    ft.ListTile(
                        title=ft.Text(name, color="white"),
                        leading=ft.Icon(ft.Icons.PERSON, color="#00ffaa"),
                        bgcolor="#161622",
                        on_click=lambda e, n=name: self.load_customer_profile(n),
                    )
                )
        else:
            all_vehicles = get_all_vehicle_numbers()
            matches = [v for v in all_vehicles if query in v.lower()][:15]
            for veh in matches:
                self.suggestions_list.controls.append(
                    ft.ListTile(
                        title=ft.Text(veh, color="white"),
                        leading=ft.Icon(ft.Icons.DIRECTIONS_CAR, color="#00ffaa"),
                        bgcolor="#161622",
                        on_click=lambda e, v=veh: self.load_vehicle_history(v),
                    )
                )

        self.update()

    # --------------------------------------------------------------
    def _stat_box(self, label, value, color="white"):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(label, size=12, color="#94a3b8"),
                    ft.Text(f"₹{value:.0f}", size=18, weight="bold", color=color),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor="#161622",
            padding=12,
            border_radius=8,
            expand=True,
        )

    def _record_row(self, r):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                f"{r['name']} — {r['vehicle'] or ''} {('(' + r['vehicle_no'] + ')') if r['vehicle_no'] else ''}",
                                color="white",
                                weight="bold",
                                size=13,
                            ),
                            ft.Text(
                                f"दिनांक: {r['tx_date'] or '-'}   |   Total: ₹{(r['total_amt'] or 0):.0f}   |   Paid: ₹{(r['paid_amt'] or 0):.0f}   |   Due: ₹{(r['due_amt'] or 0):.0f}",
                                color="#94a3b8",
                                size=12,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.EDIT,
                        icon_color="#00ffaa",
                        tooltip="एडिट करा",
                        on_click=lambda e, rid=r["id"]: self.handle_edit_click(rid),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            bgcolor="#0d0d14",
            padding=10,
            border_radius=8,
        )

    def handle_edit_click(self, record_id):
        if self.on_edit_record:
            self.on_edit_record(record_id)

    # --------------------------------------------------------------
    def load_customer_profile(self, name):
        profile = get_customer_profile(name)
        if not profile:
            self.profile_area.content = ft.Text("रेकॉर्ड सापडला नाही.", color="#ff4444")
            self.update()
            return

        records_list = ft.Column(
            [self._record_row(r) for r in profile["records"]],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        self.profile_area.content = ft.Column(
            [
                ft.Text(profile["name"], size=20, weight="bold", color="white"),
                ft.Text(
                    f"📱 {profile['mobile'] or '-'}    📍 {profile['address'] or '-'}",
                    color="#94a3b8",
                    size=13,
                ),
                ft.Text(
                    "🚗 गाड्या: " + (", ".join(profile["vehicles"]) if profile["vehicles"] else "-"),
                    color="#94a3b8",
                    size=13,
                ),
                ft.Row(
                    [
                        self._stat_box("दिलेले (Given)", profile["total_given"], "#00ffaa"),
                        self._stat_box("घेतलेले (Taken)", profile["total_taken"], "#3399ff"),
                        self._stat_box("भरलेले (Paid)", profile["total_paid"], "white"),
                        self._stat_box("थकीत (Due)", profile["total_due"], "#ff4444"),
                    ],
                    spacing=10,
                ),
                ft.Divider(color="#1e1e2a"),
                ft.Text(f"सर्व नोंदी ({profile['record_count']})", color="white", weight="bold"),
                records_list,
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self.update()

    # --------------------------------------------------------------
    def load_vehicle_history(self, vehicle_no):
        records = get_vehicle_history(vehicle_no)
        if not records:
            self.profile_area.content = ft.Text("या गाडी नंबरवर कोणतीही नोंद सापडली नाही.", color="#ff4444")
            self.update()
            return

        total_due = sum((r["due_amt"] or 0) for r in records)

        records_list = ft.Column(
            [self._record_row(r) for r in records],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        self.profile_area.content = ft.Column(
            [
                ft.Text(f"🚗 {vehicle_no}", size=20, weight="bold", color="white"),
                ft.Text(f"एकूण नोंदी: {len(records)}   |   थकीत: ₹{total_due:.0f}", color="#94a3b8", size=13),
                ft.Divider(color="#1e1e2a"),
                records_list,
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self.update()
