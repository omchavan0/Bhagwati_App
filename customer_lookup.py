"""
============================================================================
CUSTOMER LOOKUP + SMART SEARCH + AUTO-CAPITALIZE
============================================================================
तीन गोष्टी इथे एकत्र आहेत (एकमेकांशी संबंधित असल्यामुळे एकाच फाईलमध्ये):

1. AUTO-FILL: एकदा customer/vehicle ची माहिती Udhaari मध्ये सेव्ह झाली की,
   पुढच्या वेळी फक्त नाव / मोबाईल / गाडी नंबर यापैकी कुठलंही एक टाकलं तरी
   बाकीची माहिती (मोबाईल, गाडी, पत्ता) आपोआप भरली जाते — टाईप करायची गरज
   उरत नाही, वेळ वाचतो.

2. SMART SEARCH: "MH20AB1234 चा हिशोब दाखव" असं नैसर्गिक वाक्य टाकलं तरी
   त्यातला खरा शोध-शब्द (गाडी नंबर/मोबाईल/नाव) ओळखून योग्य शोध आपोआप चालतो.

3. AUTO-CAPITALIZE: Customer Name सारख्या फील्डमध्ये टाईप करताना, स्पेस
   देऊन नवीन शब्द सुरू केला की त्या शब्दाचं पहिलं अक्षर आपोआप Capital होतं
   (उरलेली अक्षरं जशीच्या तशी राहतात — जबरदस्तीने लोअरकेस होत नाहीत).

वापर (कुठल्याही view मध्ये):
    from customer_lookup import smart_customer_lookup, smart_search, auto_capitalize_words
============================================================================
"""
import re

from database import get_history_by_name, get_vehicle_history, get_udhaari


# ==========================================================================
# PATTERN DETECTION — दिलेला मजकूर गाडी नंबर आहे की मोबाईल आहे की नाव आहे
# ==========================================================================
def _looks_like_vehicle_no(text):
    """MH20AB1234 / MH-20-AB-1234 सारखा pattern (अक्षरं + आकडे मिश्रित) ओळखतो."""
    t = (text or "").strip().upper().replace(" ", "").replace("-", "")
    if not t:
        return False
    if re.match(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{3,4}$", t):
        return True
    # ढोबळ नियम: 6+ अक्षरं, आकडे आणि letters दोन्ही असतील तर गाडी नंबर गृहीत धरतो
    return len(t) >= 6 and any(c.isdigit() for c in t) and any(c.isalpha() for c in t)


def _looks_like_mobile(text):
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    return len(digits) >= 10 and len(digits) == len(re.sub(r"\D", "", (text or "").strip()))


def _digits_only(text):
    return "".join(ch for ch in (text or "") if ch.isdigit())


# ==========================================================================
# LOOKUP — एक-एक पद्धतीने
# ==========================================================================
def find_by_name(name):
    records = get_history_by_name((name or "").strip())
    return records[0] if records else None  # सगळ्यात अलीकडची नोंद (id DESC)


def find_by_vehicle_no(vehicle_no):
    records = get_vehicle_history(vehicle_no)
    return records[0] if records else None


def find_by_mobile(mobile):
    digits = _digits_only(mobile)
    if len(digits) < 4:
        return None
    matches = [r for r in get_udhaari() if r["mobile"] and digits in _digits_only(r["mobile"])]
    return matches[0] if matches else None  # get_udhaari() आधीच id DESC क्रमाने आहे


def smart_customer_lookup(value):
    """नाव/मोबाईल/गाडी नंबर यापैकी कुठलंही value असू शकेल — आपोआप ओळखून
    सगळ्यात अलीकडची जुळणारी नोंद (sqlite3.Row) परत देतो, नाहीतर None."""
    value = (value or "").strip()
    if not value:
        return None

    if _looks_like_vehicle_no(value):
        row = find_by_vehicle_no(value)
        if row:
            return row
    if _looks_like_mobile(value):
        row = find_by_mobile(value)
        if row:
            return row
    return find_by_name(value)


# ==========================================================================
# SMART SEARCH — नैसर्गिक वाक्यातून खरा शोध-शब्द वेगळा काढणे
# ==========================================================================
STOPWORDS = {
    "चा", "ची", "चे", "चं", "हिशोब", "दाखव", "दाखवा", "बघ", "बघा",
    "माहिती", "बद्दल", "काढ", "history", "show", "search", "find", "of",
}


def smart_search(query):
    """Natural-language क्वेरी (उदा. 'MH20AB1234 चा हिशोब दाखव') घेऊन,
    त्यातला खरा शोध-शब्द ओळखून योग्य प्रकारे शोधतो.
    Returns: {"type": "vehicle"|"mobile"|"name"|"none", "query": str, "records": [...]}"""
    raw = (query or "").strip()
    if not raw:
        return {"type": "none", "query": "", "records": []}

    tokens = [t.strip(".,!?") for t in re.split(r"\s+", raw) if t.strip(".,!?")]
    meaningful = [t for t in tokens if t.lower() not in STOPWORDS] or tokens

    # 1) टोकन्समध्ये गाडी नंबर किंवा मोबाईल आहे का ते आधी तपासतो
    for t in meaningful:
        if _looks_like_vehicle_no(t):
            records = get_vehicle_history(t)
            if records:
                return {"type": "vehicle", "query": t, "records": records}
        if _looks_like_mobile(t):
            digits = _digits_only(t)
            matches = [r for r in get_udhaari() if r["mobile"] and digits in _digits_only(r["mobile"])]
            if matches:
                return {"type": "mobile", "query": t, "records": matches}

    # 2) नाहीतर उरलेला भाग नाव समजून शोधतो
    cleaned = " ".join(meaningful).strip()
    records = get_history_by_name(cleaned)
    if not records:
        # exact match नसेल तर सगळ्या नावांमध्ये partial (contains) match बघतो
        all_names = sorted({r["name"] for r in get_udhaari() if r["name"]})
        best_match = next((n for n in all_names if cleaned.lower() in n.lower()), None)
        if best_match:
            records = get_history_by_name(best_match)
            cleaned = best_match

    return {"type": "name", "query": cleaned, "records": records}


# ==========================================================================
# AUTO-CAPITALIZE — प्रत्येक शब्दाचं फक्त पहिलं अक्षर Capital
# ==========================================================================
def auto_capitalize_words(text):
    """'ramesh patil' -> 'Ramesh Patil' — पण उरलेली अक्षरं जबरदस्तीने
    lowercase करत नाही (user ने जसं टाईप केलं तसंच राहतं, फक्त पहिलं अक्षर बदलतं)."""
    if not text:
        return text
    words = text.split(" ")
    return " ".join((w[0].upper() + w[1:]) if w else w for w in words)
