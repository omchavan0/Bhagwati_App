"""
============================================================================
WHATSAPP AUTOMATION — Auto Invoice Send + Bulk Due Reminders
============================================================================
दोन पद्धती दिल्या आहेत:

1) "One-Tap Auto" (डिफॉल्ट, कुठलीही extra library न लागता):
   पूर्ण मेसेज + नंबर आधीच भरून WhatsApp चॅट उघडतो (wa.me लिंकने).
   स्टाफला फक्त एकदा "Send" बटण दाबायचं — टाईप काहीच करायला लागत नाही.
   हे सगळ्यात भरवशाचं आहे (WhatsApp Web logged-in नसेल तरी मोबाईल app वरही
   चालतं) आणि Flet च्या page.launch_url() ने चालतं — जुन्या udhaari_view.py
   मधल्या WhatsApp Reminder बटणासारखंच, फक्त आता Invoice साठीही वापरता येतं.

2) "Fully-Auto" (Advanced, ऐच्छिक — pywhatkit लागतं):
   कुठलंही क्लिक न करता आपोआप मेसेज पाठवतो — पण यासाठी:
     - pip install pywhatkit --break-system-packages
     - Chrome/Browser मध्ये WhatsApp Web आधीच Login असणं गरजेचं
     - चालू असताना संगणकाचा माउस/कीबोर्ड touch करू नये (हे कीबोर्ड सिम्युलेट
       करून पाठवतं) — त्यामुळे शॉप क्लोज झाल्यावर/रात्री bulk reminders साठी
       जास्त उपयोगी, दिवसा बिलिंग करताना नाही.

--------------------------------------------------------------------------
वापर:
    from whatsapp_automation import build_invoice_message, send_via_browser

    msg = build_invoice_message(sale_row, pdf_path="Bill_Ramesh_INV-0007.pdf")
    send_via_browser(page, mobile, msg)     # Flet चा page ऑब्जेक्ट लागतो
--------------------------------------------------------------------------
"""
import time
import urllib.parse

SHOP_NAME = "Bhagwati Auto Electricals"


# ==========================================================================
# HELPERS — नंबर स्वच्छ करणे (भारतीय नंबरला आपोआप 91 कोड जोडणे)
# ==========================================================================
def _clean_mobile(mobile):
    digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return digits


# ==========================================================================
# MESSAGE BUILDERS
# ==========================================================================
def build_invoice_message(sale_row, pdf_path=None):
    """Sale झाल्यावर लगेच कस्टमरला पाठवायचा Invoice मेसेज तयार करतो.
    sale_row मध्ये असावं: name, total_amt, paid_amt, due_amt, vehicle,
    vehicle_no, id (किंवा invoice_no असल्यास तेही चालेल)."""
    name = sale_row["name"] if "name" in sale_row.keys() else sale_row.get("customer_name", "")
    total = sale_row["total_amt"] if "total_amt" in sale_row.keys() else sale_row.get("total_amount", 0)
    paid = sale_row["paid_amt"] if "paid_amt" in sale_row.keys() else sale_row.get("paid_amount", 0)
    due = sale_row["due_amt"] if "due_amt" in sale_row.keys() else sale_row.get("due_amount", 0)
    invoice_no = sale_row["id"] if "id" in sale_row.keys() else sale_row.get("invoice_no", "")

    lines = [
        f"🔧 *{SHOP_NAME}*",
        f"नमस्कार {name},",
        f"आपलं बिल तयार झालं आहे (Invoice #{invoice_no}).",
        "",
        f"💰 एकूण रक्कम: ₹{float(total):.0f}",
        f"✅ भरलेली रक्कम: ₹{float(paid):.0f}",
    ]
    if float(due) > 0:
        lines.append(f"⏳ बाकी रक्कम: ₹{float(due):.0f}")
    else:
        lines.append("🎉 पूर्ण पेमेंट मिळालं आहे, धन्यवाद!")

    if pdf_path:
        lines.append("")
        lines.append("📄 PDF बिल शॉपमधून/या मेसेजसोबत मिळेल.")

    lines.append("")
    lines.append(f"धन्यवाद! — {SHOP_NAME}")
    return "\n".join(lines)


def build_reminder_message(customer_name, due_amount):
    """अजून पैसे न भरलेल्या ग्राहकाला Reminder मेसेज."""
    return (
        f"🔧 *{SHOP_NAME}*\n"
        f"नमस्कार {customer_name}, आपली ₹{float(due_amount):.0f} रक्कम बाकी आहे. "
        f"कृपया लवकरात लवकर पूर्ण करा.\n"
        f"धन्यवाद! — {SHOP_NAME}"
    )


# ==========================================================================
# METHOD 1 — One-Tap Auto (Flet page.launch_url वापरून) — शिफारसीय
# ==========================================================================
def send_via_browser(page, mobile, message):
    """WhatsApp चॅट, मेसेज आधीच टाईप केलेला उघडतो — स्टाफ फक्त 'Send' दाबतो.
    page = Flet चा page ऑब्जेक्ट (उदा. self.page)."""
    digits = _clean_mobile(mobile)
    if not digits:
        raise ValueError("⚠️ मोबाईल नंबर चुकीचा/रिकामा आहे.")
    encoded = urllib.parse.quote(message)
    url = f"https://wa.me/{digits}?text={encoded}"
    page.launch_url(url)
    return url


def send_invoice_now(page, sale_row, pdf_path=None):
    """Sale save झाल्या झाल्या एका कॉलमध्ये Invoice WhatsApp वर पाठवायला उघडतं."""
    mobile = sale_row["mobile"] if "mobile" in sale_row.keys() else sale_row.get("mobile", "")
    if not mobile:
        return None  # मोबाईल नंबर नसेल तर शांतपणे skip
    message = build_invoice_message(sale_row, pdf_path)
    return send_via_browser(page, mobile, message)


def send_bulk_reminders_via_browser(page, due_customers, delay_seconds=1.5):
    """Due Amount > 0 असलेल्या सगळ्या ग्राहकांसाठी एका-मागोमाग-एक WhatsApp चॅट
    उघडतो (प्रत्येकात मेसेज आधीच भरलेला). due_customers = [{"customer_name",
    "mobile", "total_due"}, ...] — udhaari_payment_manager.get_due_customers()
    किंवा database.get_due_customers() मधून मिळतं.
    टीप: प्रत्येक टॅबमध्ये स्टाफला 'Send' दाबावं लागेल — WhatsApp स्पॅम/ब्लॉक
    टाळण्यासाठी हे मुद्दाम manual-confirm ठेवलंय."""
    opened = []
    for cust in due_customers:
        mobile = cust.get("mobile")
        due = cust.get("total_due", 0)
        name = cust.get("customer_name", "")
        if not mobile or due <= 0:
            continue
        message = build_reminder_message(name, due)
        url = send_via_browser(page, mobile, message)
        opened.append({"customer_name": name, "mobile": mobile, "url": url})
        time.sleep(delay_seconds)  # ब्राउझर टॅब्स एकदम गर्दी करून उघडू नयेत म्हणून
    return opened


# ==========================================================================
# METHOD 2 — Fully-Auto (pywhatkit, कुठलाही क्लिक न लागता) — Advanced/Optional
# ==========================================================================
def send_fully_auto(mobile, message, wait_seconds=15, tab_close=True):
    """क्लिक न करता आपोआप पाठवतो. आवश्यकता:
       - pip install pywhatkit --break-system-packages
       - Browser मध्ये WhatsApp Web आधीच लॉगिन असावं
       - चालू असताना माउस/कीबोर्ड वापरू नये (keyboard automation आहे)
    रात्री/शॉप बंद झाल्यावर सगळ्या due reminders एकदम पाठवायला उत्तम."""
    try:
        import pywhatkit
    except ImportError:
        raise ImportError(
            "⚠️ pywhatkit इन्स्टॉल नाहीये. चालवा: "
            "pip install pywhatkit --break-system-packages"
        )

    digits = "+" + _clean_mobile(mobile)
    pywhatkit.sendwhatmsg_instantly(
        phone_no=digits, message=message,
        wait_time=wait_seconds, tab_close=tab_close,
    )


def send_fully_auto_bulk(due_customers, wait_seconds=15, gap_seconds=20):
    """सगळ्या Due ग्राहकांना, एकदम, क्लिकशिवाय Reminder पाठवतो.
    ⚠️ हे रात्री/शॉप बंद झाल्यावर चालवा — चालू असताना संगणकाला हात लावू नका."""
    results = []
    for cust in due_customers:
        mobile = cust.get("mobile")
        due = cust.get("total_due", 0)
        name = cust.get("customer_name", "")
        if not mobile or due <= 0:
            continue
        message = build_reminder_message(name, due)
        try:
            send_fully_auto(mobile, message, wait_seconds=wait_seconds)
            results.append({"customer_name": name, "mobile": mobile, "status": "sent"})
        except Exception as ex:
            results.append({"customer_name": name, "mobile": mobile, "status": f"failed: {ex}"})
        time.sleep(gap_seconds)
    return results
