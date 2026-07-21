"""
============================================================================
CLOUD SYNC ENGINE — Offline-first, Multi-device sync (Firebase Firestore)
============================================================================
कसं काम करतं (सोप्या भाषेत):

1. यूजर नेहमीप्रमाणे local SQLite (bhagwati.db) मध्ये data सेव्ह करतो —
   इंटरनेट असो वा नसो, ॲप नेहमी लगेच, वेगात काम करतं (Offline-first).
2. database.py मधला प्रत्येक add/update/delete आपोआप एका "sync_outbox"
   रांगेत नोंद टाकतो.
3. हा मॉड्यूल Background thread मध्ये दर 15 सेकंदांनी:
     a. Outbox मधले pending बदल Firestore (Google Cloud) वर पाठवतो (PUSH)
     b. दुसऱ्या डिव्हाइसवरून आलेले नवीन बदल डाउनलोड करून local मध्ये
        merge करतो (PULL) — यासाठी "last-write-wins" वापरतो: ज्या रेकॉर्डचा
        updated_at सगळ्यात नवीन, तोच अंतिम मानला जातो. यामुळे Udhaari आणि
        पैशांचा हिशोब कधीही विसंगत (corrupt/duplicate) होत नाही.
4. इंटरनेट नसेल, credentials file नसेल, किंवा library install नसेल — तरी
   हे सगळं silently थांबतं. मुख्य ॲप कधीही crash होत नाही (गुगल शीट सिंक
   सारखाच "fail-safe" pattern).

--------------------------------------------------------------------------
SETUP (एकदाच, प्रत्येक डिव्हाइसवर):

1. pip install firebase-admin --break-system-packages

2. https://console.firebase.google.com वर जा
   - नवीन प्रोजेक्ट बनवा (उदा. "bhagwati-auto-app")
   - डावीकडे "Build" -> "Firestore Database" -> "Create database"
     -> Production mode -> जवळचा region (उदा. asia-south1 Mumbai) निवडा

3. प्रोजेक्ट सेटिंग्स (⚙️ आयकॉन) -> "Service accounts" टॅब ->
   "Generate new private key" दाबा — एक JSON फाईल डाउनलोड होईल.

4. ती फाईल याच फोल्डरमध्ये (जिथे main.py आहे) "firebase_credentials.json"
   या नावाने ठेवा.

5. **महत्त्वाचं:** हीच JSON फाईल तुझ्या सगळ्या डिव्हाइसेसवर (Desktop,
   Laptop, इ.) कॉपी कर — तरच सगळी डिव्हाइसेस एकाच Firestore प्रोजेक्टला
   जोडली जातील आणि डेटा शेअर होईल.

6. ⚠️ ही फाईल गुप्त ठेव — कुणाला शेअर करू नकोस, GitHub वर public repo मध्ये
   अपलोड करू नकोस (ती संपूर्ण डेटाबेसचा मास्टर-key आहे).

7. main.py मध्ये आधीच वायरिंग केलेली आहे — वेगळं काही करावं लागणार नाही.
   Credentials file सापडली नाही तर ॲप नेहमीसारखं local-only चालेल.
--------------------------------------------------------------------------
"""

import os
import threading
import socket
from datetime import datetime

import database

CREDENTIALS_FILE = "firebase_credentials.json"
SYNC_INTERVAL_SECONDS = 15

_app_initialized = False
_available = None
_sync_thread = None
_stop_flag = threading.Event()
_status = {"state": "idle", "last_sync": None, "last_error": None}


# ==========================================================================
# उपलब्धता तपासणे — library + credentials दोन्ही असतील तरच sync चालू होतो
# ==========================================================================
def is_sync_available():
    global _available, _app_initialized
    if _available is not None:
        return _available

    try:
        if not os.path.exists(CREDENTIALS_FILE):
            _available = False
            return False

        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(CREDENTIALS_FILE)
            firebase_admin.initialize_app(cred)
        _app_initialized = True
        _available = True
        return True
    except Exception as ex:
        _status["last_error"] = str(ex)
        _available = False
        return False


def _get_firestore():
    from firebase_admin import firestore
    return firestore.client()


def _has_internet(timeout=2.5):
    """हलकी internet-check — भारी API कॉल करण्याआधी वेळ वाचवण्यासाठी."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


def get_status():
    """UI मध्ये दाखवण्यासाठी (उदा. header मध्ये '☁️ Synced' / '⚠️ Offline')."""
    return dict(_status)


# ==========================================================================
# PUSH — Local outbox मधले बदल Firestore वर पाठवणे
# ==========================================================================
def _push_pending():
    db = _get_firestore()
    pending = database.get_pending_outbox(limit=200)

    for entry in pending:
        table = entry["table_name"]
        record_id = entry["record_id"]
        operation = entry["operation"]
        doc_ref = db.collection(table).document(str(record_id))

        try:
            if operation == "delete":
                # सॉफ्ट-डिलीट: डॉक्युमेंट Firestore वरही is_deleted=1 सह ठेवतो,
                # जेणेकरून दुसऱ्या डिव्हाइसला "हे डिलीट झालंय" हे कळेल.
                row = database.get_row_as_dict(table, record_id)
                if row:
                    doc_ref.set(row, merge=True)
                else:
                    doc_ref.set({"id": record_id, "is_deleted": 1,
                                 "updated_at": datetime.now().isoformat()}, merge=True)
            else:
                row = database.get_row_as_dict(table, record_id)
                if row:
                    doc_ref.set(row, merge=True)

            database.clear_outbox_entry(entry["id"])
        except Exception as ex:
            _status["last_error"] = f"Push error ({table}#{record_id}): {ex}"
            # ही एक एन्ट्री फेल झाली तरी बाकीच्या पुढे चालू ठेवतो; पुढच्या
            # सायकलमध्ये परत प्रयत्न होईल (outbox मधून काढलं नाही)
            continue


# ==========================================================================
# PULL — दुसऱ्या डिव्हाइसवरचे बदल डाउनलोड करून local मध्ये merge करणे
# ==========================================================================
def _pull_remote_changes():
    db = _get_firestore()
    last_sync = database.get_last_sync_time() or "1970-01-01T00:00:00"
    newest_seen = last_sync

    for table in database.SYNCED_TABLES:
        try:
            docs = (
                db.collection(table)
                .where("updated_at", ">", last_sync)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict()
                if not data:
                    continue
                database.apply_remote_change(table, data)
                if data.get("updated_at", "") > newest_seen:
                    newest_seen = data["updated_at"]
        except Exception as ex:
            _status["last_error"] = f"Pull error ({table}): {ex}"
            continue

    database.set_last_sync_time(newest_seen)


# ==========================================================================
# एक पूर्ण sync सायकल (push + pull) — मॅन्युअली किंवा background मधून कॉल होतं
# ==========================================================================
def run_sync_once():
    if not is_sync_available():
        _status["state"] = "unavailable"
        return False
    if not _has_internet():
        _status["state"] = "offline"
        return False

    try:
        _status["state"] = "syncing"
        _push_pending()
        _pull_remote_changes()
        _status["state"] = "synced"
        _status["last_sync"] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        _status["last_error"] = None
        return True
    except Exception as ex:
        _status["state"] = "error"
        _status["last_error"] = str(ex)
        return False


# ==========================================================================
# Background Thread — ॲप सुरू असेपर्यंत दर 15 सेकंदांनी आपोआप sync
# ==========================================================================
def start_background_sync():
    global _sync_thread
    if _sync_thread is not None and _sync_thread.is_alive():
        return  # आधीच चालू आहे

    _stop_flag.clear()

    def _loop():
        while not _stop_flag.is_set():
            run_sync_once()
            _stop_flag.wait(SYNC_INTERVAL_SECONDS)

    _sync_thread = threading.Thread(target=_loop, daemon=True)
    _sync_thread.start()


def stop_background_sync():
    _stop_flag.set()
