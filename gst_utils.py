"""
============================================================================
GST_UTILS — केंद्रीय GST गणित (Registered/Unregistered + Intra/Inter State)
============================================================================
हे मॉड्यूल कुठलंही टेबल हाताळत नाही — फक्त शुद्ध गणिती/लॉजिक फंक्शन्स आहेत,
जेणेकरून Billing Screen, GST Returns, Reports — सगळीकडे तेच एकसमान लॉजिक
वापरलं जाईल (कुठेही वेगळं गणित लिहिलं तर विसंगती येऊ शकते).
============================================================================
"""
import re

GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z0-9]{10}[A-Z0-9]{3}$")


def is_valid_gstin_format(gstin):
    """GSTIN चा फॉरमॅट (15 अक्षरं, ठराविक पॅटर्न) तपासतो — सरकारी validation
    नाही (त्यासाठी सरकारी API लागतं), फक्त टायपिंग चूक पकडण्यासाठी."""
    gstin = (gstin or "").strip().upper()
    return bool(GSTIN_PATTERN.match(gstin))


def get_state_code_from_gstin(gstin):
    """GSTIN च्या पहिल्या 2 अंकांमधून State Code काढतो (उदा. 27 = Maharashtra)."""
    gstin = (gstin or "").strip()
    if len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return None


def is_registered_customer(gstin):
    """GSTIN असेल (आणि फॉरमॅट बरोबर असेल) तर Registered, नाहीतर Unregistered."""
    return is_valid_gstin_format(gstin)


def get_customer_type_label(gstin):
    return "Registered" if is_registered_customer(gstin) else "Unregistered"


def determine_tax_mode(company_state_code, customer_state_code):
    """दोन्ही राज्य कोड सारखे असतील -> Intra-state (CGST+SGST),
    वेगळे असतील -> Inter-state (IGST). दोन्हींपैकी एक रिकामा असेल तर
    सुरक्षित डिफॉल्ट म्हणून Intra-state (Maharashtra local ग्राहक) गृहीत धरतो."""
    company_state_code = (company_state_code or "").strip()
    customer_state_code = (customer_state_code or "").strip()
    if not company_state_code or not customer_state_code:
        return "intra"
    return "intra" if company_state_code == customer_state_code else "inter"


def split_tax(amount, gst_rate, tax_mode, price_includes_gst=True):
    """दिलेल्या amount (आणि GST%) वरून Taxable/CGST/SGST/IGST काढतो.

    price_includes_gst=True (डिफॉल्ट) -> 'amount' आधीच ग्राहकाला सांगितलेली
    अंतिम रक्कम आहे, GST मागच्या बाजूने (÷ 1+GST%) काढला जातो (Total बदलत नाही).
    price_includes_gst=False -> 'amount' ही taxable (GST आधीची) रक्कम आहे,
    त्यावर GST वर लावला जातो (Total वाढतो).

    Returns: {"taxable", "cgst", "sgst", "igst", "total_tax", "final_amount"}
    """
    amount = float(amount or 0)
    gst_rate = float(gst_rate or 0)

    if price_includes_gst:
        taxable = amount / (1 + gst_rate / 100) if gst_rate else amount
        final_amount = amount
    else:
        taxable = amount
        final_amount = amount * (1 + gst_rate / 100)

    total_tax = final_amount - taxable

    if tax_mode == "intra":
        cgst = total_tax / 2
        sgst = total_tax / 2
        igst = 0.0
    else:
        cgst = 0.0
        sgst = 0.0
        igst = total_tax

    return {
        "taxable": taxable, "cgst": cgst, "sgst": sgst, "igst": igst,
        "total_tax": total_tax, "final_amount": final_amount,
    }


STATE_CODE_MAP = {
    "Maharashtra": "27", "Gujarat": "24", "Karnataka": "29", "Tamil Nadu": "33",
    "Telangana": "36", "Andhra Pradesh": "37", "Delhi": "07", "Uttar Pradesh": "09",
    "Madhya Pradesh": "23", "Rajasthan": "08", "West Bengal": "19", "Punjab": "03",
    "Haryana": "06", "Kerala": "32", "Bihar": "10", "Goa": "30", "Other State": "",
}


def get_state_code_from_name(state_name):
    return STATE_CODE_MAP.get((state_name or "").strip(), "")