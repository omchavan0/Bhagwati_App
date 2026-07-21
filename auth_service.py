"""
============================================================================
AUTH SERVICE — Firebase Authentication (Email/Password + Password Reset)
============================================================================
का Email/Password आणि नुसता Mobile Number OTP का नाही?
Phone-OTP verification (SMS) साठी Google चं मोबाईल/वेब SDK लागतं — डेस्कटॉप
Python ॲपमध्ये ते थेट चालत नाही (त्याला reCAPTCHA + एक backend सर्व्हर लागतो).
त्यामुळे इथे भक्कम आणि प्रत्यक्षात काम करणारा मार्ग वापरलाय:
  - Login/Signup: Email + Password (यूजरचं Gmail ॲड्रेस चालेल)
  - Password Reset: Firebase आपोआप यूजरच्या email वर reset-link पाठवतं
  - Mobile Number: प्रोफाइलमध्ये फक्त माहिती म्हणून साठवला जातो (contact/recovery साठी)

--------------------------------------------------------------------------
SETUP (एकदाच):
1. pip install pyrebase4 --break-system-packages

2. Firebase Console -> Build -> Authentication -> "Get started"
   -> Sign-in method -> "Email/Password" Enable करा

3. Project Settings (⚙️) -> "General" टॅब -> खाली "Your apps" ->
   "</>" (Web app) आयकॉनने एक Web App ॲड करा (नाव काहीही, उदा. "Desktop Client")
   -> तिथे मिळणारा "firebaseConfig" ऑब्जेक्ट कॉपी करा.

4. खालच्या FIREBASE_CONFIG dict मध्ये ती व्हॅल्यूज पेस्ट करा.

5. यासाठी वेगळी credentials.json लागत नाही — फक्त वरचा config पुरेसा आहे.
--------------------------------------------------------------------------
"""

from datetime import datetime
import re
import database
from db_core import _get_connection, get_current_owner_uid, get_device_id, log_login_event

# 👇 इथे तुझ्या Firebase प्रोजेक्टचा Web-App config पेस्ट कर
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyC8PQm0KTp2RudtJEiaNPwkJ2hCeIeCd_w",
    "authDomain": "bhagwati-auto-app.firebaseapp.com",
    "projectId": "bhagwati-auto-app",
    "storageBucket": "bhagwati-auto-app.firebasestorage.app",
    "messagingSenderId": "232656970696",
    "appId": "1:232656970696:web:fed2ebf57138c9ce2116fd",
    "measurementId": "G-BFDBF764QQ",
    "databaseURL": "https://bhagwati-auto-app-default-rtdb.firebaseio.com/"
}

_firebase_app = None
_available = None
_current_user = None  # लॉगिन झाल्यावर इथे session माहिती साठते


def is_auth_available():
    global _available
    # जर आधीच चेक केले असेल तर पुन्हा चेक करू नको
    if _available is not None:
        return _available
        
    # फक्त config मधील apiKey आहे का ते तपासा
    if FIREBASE_CONFIG and FIREBASE_CONFIG.get("apiKey"):
        _available = True
    else:
        _available = False
        
    return _available



def _get_auth():
    APP = _ensure_firebase_app()  # आधी खात्री कर की ॲप आहे
    return APP.auth()              # आता इथे एरर येणार नाही

# हे फंक्शन ॲप इनिशिअलाईज झाले नसल्यास ते करेल
def _ensure_firebase_app():
    global _firebase_app
    if _firebase_app is None:
        import pyrebase
        _firebase_app = pyrebase.initialize_app(FIREBASE_CONFIG)
    return _firebase_app


# ==========================================================================
# Validation Helpers
# ==========================================================================
def is_valid_email(email):
    return bool(re.match(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$", (email or "").strip()))


def is_valid_password(password):
    return bool(password) and len(password) >= 6


# ==========================================================================
# Sign Up — नवीन यूजर तयार करणे
# ==========================================================================
def _touch_sync_fields(record_id, table):
    conn = _get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET updated_at=?, device_id=?, owner_uid=? WHERE id=?",
              (datetime.now().isoformat(), get_device_id(), get_current_owner_uid(), record_id))
    conn.commit()
    conn.close()
    
    
def sign_up(email, password, display_name="", mobile=""):
    if not is_valid_email(email):
        return False, "⚠️ योग्य Email टाका."
    if not is_valid_password(password):
        return False, "⚠️ Password किमान 6 अक्षरी असावा."
    if not is_auth_available():
        return False, "☁️ Cloud Auth सेट-अप झालेला नाही."

    try:
        auth = _get_auth()
        user = auth.create_user_with_email_and_password(email, password)
        database.save_local_session(user["localId"], email, display_name, mobile)
        global _current_user
        _current_user = user
        log_login_event(email, "success", reason="Sign Up", uid=user["localId"])
        return True, "✅ अकाउंट तयार झालं!"
    except Exception as ex:
        msg = str(ex)
        if "EMAIL_EXISTS" in msg:
            # 👇 आधीच account आहे — नवीन बनवण्याऐवजी थेट login करून टाकतो
            ok, login_msg = login(email, password)
            if ok:
                return True, "ℹ️ हा Email आधीच नोंदणीकृत आहे — त्याच अकाउंटमध्ये Login केलं."
            return False, "⚠️ हा Email आधीच वापरात आहे, पण Password चुकीचा आहे. Login करा."
        log_login_event(email, "failed", reason=f"Sign Up: {msg}")
        return False, f"❌ एरर: {msg}"


# ==========================================================================
# Login
# ============================================================================
# टीप (बग-फिक्स): आधी login() हे function इथे दोनदा defined होतं —
# पहिलं (validation/logging शिवाय, फक्त 2 ओळींचं) पूर्णपणे dead code होतं,
# कारण Python मध्ये खालचं (दुसरं) definition वरच्यालाच override करतं.
# आता फक्त एकच, पूर्ण (validation + login_history सह) व्हर्जन ठेवलंय.
# ==========================================================================
def login(email, password):
    if not is_valid_email(email):
        return False, "⚠️ योग्य Email टाका."
    if not password:
        return False, "⚠️ Password टाका."
    if not is_auth_available():
        return False, "☁️ Cloud Auth सेट-अप झालेला नाही (firebase_config तपासा)."

    try:
        auth = _get_auth()
        user = auth.sign_in_with_email_and_password(email, password)
        database.save_local_session(user["localId"], email, "", "")
        global _current_user
        _current_user = user
        log_login_event(email, "success", reason="Login", uid=user["localId"])
        return True, "✅ Login यशस्वी!"
    except Exception as ex:
        msg = str(ex)
        if "INVALID_PASSWORD" in msg or "INVALID_LOGIN_CREDENTIALS" in msg:
            log_login_event(email, "failed", reason="चुकीचा Password")
            return False, "❌ Email किंवा Password चुकीचा आहे."
        if "EMAIL_NOT_FOUND" in msg:
            log_login_event(email, "failed", reason="Email नोंदणीकृत नाही")
            return False, "❌ हा Email नोंदणीकृत नाही. आधी Sign Up करा."
        log_login_event(email, "failed", reason=msg)
        return False, f"❌ एरर: {msg}"


# ==========================================================================
# Password Reset — Firebase आपोआप यूजरच्या email वर reset-link पाठवतं
# ==========================================================================
def send_password_reset(email):
    if not is_valid_email(email):
        return False, "⚠️ योग्य Email टाका."
    if not is_auth_available():
        return False, "☁️ Cloud Auth सेट-अप झालेला नाही."

    try:
        auth = _get_auth()
        auth.send_password_reset_email(email)
        return True, f"📧 Password reset लिंक {email} वर पाठवली आहे. Inbox तपासा."
    except Exception as ex:
        msg = str(ex)
        if "EMAIL_NOT_FOUND" in msg:
            return False, "❌ हा Email नोंदणीकृत नाही."
        return False, f"❌ एरर: {msg}"


# ==========================================================================
# Session — लॉगिन स्टेट लक्षात ठेवणे (जेणेकरून प्रत्येक वेळी लॉगिन करावं लागू नये)
# ==========================================================================
def get_saved_session():
    """आधीच लॉगिन केलेलं असेल तर local settings मधून session परत देतं."""
    return database.get_local_session()


def logout():
    global _current_user
    _current_user = None
    database.clear_local_session()


def get_current_user():
    return _current_user