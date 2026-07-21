"""
============================================================================
CLOUD BACKUP — bhagwati.db + Excel Export रोज आपोआप Google Drive वर
============================================================================
का हवं: फोन/लॅपटॉप हरवला, खराब झाला किंवा चोरी झाला तरी तुझा संपूर्ण
Udhaari/Inventory/Finance डेटा Google Drive वर सुरक्षित राहील — नवीन
डिव्हाइसवर restore_backup() ने परत आणता येईल (db_core.py मध्ये आधीच आहे).

काय करतं:
  1. रोज (डिफॉल्ट रात्री उशिरा) db_core.manual_backup() ने ताजा local
     backup (.db फाईल) घेतो.
  2. तोच backup + एक ताजा Excel export (export_to_excel) Google Drive
     वरच्या ठराविक फोल्डरमध्ये अपलोड करतो.
  3. आधीच अपलोड झालेला असेल (त्याच दिवसाचा) तर पुन्हा अपलोड करत नाही —
     डुप्लिकेट फाईल्सचा गोंधळ होत नाही.
  4. ठरवलेल्या दिवसांपेक्षा जुने Drive backups आपोआप डिलीट होतात (जागा
     वाचावी म्हणून) — local backups (db_core.py) प्रमाणेच पॅटर्न.
  5. इंटरनेट नसेल, credentials नसतील, किंवा library install नसेल — तरी
     silently skip होतं; मुख्य ॲप कधीही crash होत नाही (fail-safe पॅटर्न,
     gsheet_sync.py/sync_engine.py सारखाच).

--------------------------------------------------------------------------
SETUP (एकदाच):

1. लायब्ररी इन्स्टॉल करा:
      pip install google-api-python-client google-auth --break-system-packages
   (google-auth तुझ्याकडे gsheet_sync.py साठी आधीच आहे.)

2. तुझ्याकडे आधीच "service_account.json" आहे — तेच वापरतो, वेगळी फाईल
   लागत नाही (त्यात आधीच Drive scope आहे).

3. **महत्त्वाचं — फोल्डर शेअर करणे:**
   Service Account ला स्वतःची "My Drive" स्टोरेज नसते — त्यामुळे थेट
   त्याच्या नावाने अपलोड केलेल्या फाईल्स "अनाथ" (कुणालाच न दिसणाऱ्या)
   राहू शकतात. म्हणून:
      a. तुझ्या स्वतःच्या Google Drive मध्ये एक फोल्डर बनव (उदा.
         "Bhagwati_App_Backups").
      b. तो फोल्डर उघड -> Share -> Service Account चा ईमेल (JSON मधला
         "client_email", उदा. bhagwati-sheets-bot@...iam.gserviceaccount.com)
         याला "Editor" access दे.
      c. त्या फोल्डरची लिंक उघडून URL मधला ID कॉपी कर:
         https://drive.google.com/drive/folders/<हा भाग कॉपी कर>
      d. खाली DRIVE_FOLDER_ID मध्ये तो पेस्ट कर.

4. main.py मध्ये फक्त एवढंच जोडायचं (sync_engine.start_background_sync()
   च्या शेजारीच):
        import cloud_backup
        cloud_backup.start_background_backup()
--------------------------------------------------------------------------
"""

import os
import threading
from datetime import datetime, timedelta

import database  # db_core.manual_backup(), export_to_excel(), DB_NAME, BACKUP_DIR

CREDENTIALS_FILE = "service_account.json"
DRIVE_FOLDER_ID = "https://drive.google.com/drive/folders/1K0YYMsTuolbrqNja0HICxItNWIvR9ZiF?usp=drive_link"  # 👈 वरच्या पायरी 3(d) प्रमाणे तुझ्या फोल्डरचा ID इथे टाक

BACKUP_KEEP_DAYS_DRIVE = 30       # Drive वर एवढ्या दिवसांपेक्षा जुने बॅकअप्स आपोआप जातील
BACKUP_INTERVAL_SECONDS = 6 * 60 * 60   # दर 6 तासांनी तपासतो — "आजचा झालाय का?"

SCOPES = ["https://www.googleapis.com/auth/drive"]

_service = None
_available = None
_thread = None
_stop_flag = threading.Event()
_status = {"state": "idle", "last_backup": None, "last_error": None}


# ==========================================================================
# AUTHENTICATION — googleapiclient (Drive API v3)
# ==========================================================================
def is_backup_available():
    """library + credentials + folder-id तिन्ही असतील तरच True."""
    global _available
    if _available is not None:
        return _available
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            _available = False
            return False
        if not DRIVE_FOLDER_ID:
            _status["last_error"] = "DRIVE_FOLDER_ID सेट केलेला नाही (cloud_backup.py उघडून टाक)."
            _available = False
            return False
        import googleapiclient  # noqa: F401  फक्त उपलब्धता तपासण्यासाठी
        _available = True
        return True
    except Exception as ex:
        _status["last_error"] = str(ex)
        _available = False
        return False


def _get_drive_service():
    global _service
    if _service is None:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _service


def get_status():
    return dict(_status)


# ==========================================================================
# UPLOAD / CLEANUP
# ==========================================================================
def _find_existing_file(service, filename):
    """त्याच नावाची फाईल फोल्डरमध्ये आधीच आहे का ते शोधतो (डुप्लिकेट टाळण्यासाठी)."""
    query = f"name = '{filename}' and '{DRIVE_FOLDER_ID}' in parents and trashed = false"
    result = service.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def _upload_file(service, local_path, drive_filename):
    """फाईल अपलोड करतो — आधीच असेल तर overwrite (update), नसेल तर नवीन (create)."""
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(local_path, resumable=True)
    existing_id = _find_existing_file(service, drive_filename)

    if existing_id:
        service.files().update(fileId=existing_id, media_body=media).execute()
        return existing_id
    else:
        metadata = {"name": drive_filename, "parents": [DRIVE_FOLDER_ID]}
        created = service.files().create(body=metadata, media_body=media, fields="id").execute()
        return created["id"]


def _cleanup_old_drive_backups(service):
    """ठरवलेल्या दिवसांपेक्षा जुने बॅकअप्स Drive वरून काढून टाकतो."""
    cutoff = (datetime.now() - timedelta(days=BACKUP_KEEP_DAYS_DRIVE)).isoformat() + "Z"
    query = (
        f"'{DRIVE_FOLDER_ID}' in parents and trashed = false "
        f"and name contains 'bhagwati_backup_' and modifiedTime < '{cutoff}'"
    )
    try:
        result = service.files().list(q=query, fields="files(id, name)").execute()
        for f in result.get("files", []):
            service.files().delete(fileId=f["id"]).execute()
    except Exception:
        pass  # cleanup फेल झालं तरी मुख्य backup प्रक्रिया अडकू नये


# ==========================================================================
# MAIN — एक पूर्ण backup सायकल (local + Excel + Drive upload + cleanup)
# ==========================================================================
def run_backup_once(force=False):
    """
    Returns:
        (success: bool, message: str)
    """
    if not is_backup_available():
        return False, f"⚠️ Cloud Backup उपलब्ध नाही: {_status.get('last_error', 'सेटअप अपूर्ण आहे')}"

    today_str = datetime.now().strftime("%Y-%m-%d")
    last_backup = _status.get("last_backup")
    if not force and last_backup == today_str:
        return True, "ℹ️ आजचा Cloud Backup आधीच झालाय."

    try:
        _status["state"] = "backing_up"

        # 1) ताजा local .db backup घे (db_core.py चंच function वापरून)
        local_backup_path = database.manual_backup()

        # 2) ताजा Excel export सुद्धा घे (Udhaari data साठी वेगळी उपयोगी कॉपी)
        excel_path = os.path.join(database.BACKUP_DIR, f"udhaari_export_{today_str}.xlsx")
        try:
            database.export_to_excel(excel_path)
        except Exception:
            excel_path = None  # Excel export फेल झालं तरी .db backup तरी जाईल

        # 3) Google Drive वर अपलोड
        service = _get_drive_service()
        db_filename = os.path.basename(local_backup_path)
        _upload_file(service, local_backup_path, db_filename)

        if excel_path and os.path.exists(excel_path):
            _upload_file(service, excel_path, os.path.basename(excel_path))

        # 4) जुने Drive backups साफ कर
        _cleanup_old_drive_backups(service)

        _status["state"] = "done"
        _status["last_backup"] = today_str
        _status["last_error"] = None
        return True, f"✅ Cloud Backup यशस्वी झाला ({db_filename})"

    except Exception as ex:
        _status["state"] = "error"
        _status["last_error"] = str(ex)
        return False, f"❌ Cloud Backup Error: {ex}"


# ==========================================================================
# BACKGROUND THREAD — ॲप चालू असेपर्यंत दर काही तासांनी तपासत राहतो
# ==========================================================================
def start_background_backup():
    global _thread
    if _thread is not None and _thread.is_alive():
        return  # आधीच चालू आहे

    _stop_flag.clear()

    def _loop():
        while not _stop_flag.is_set():
            run_backup_once()
            _stop_flag.wait(BACKUP_INTERVAL_SECONDS)

    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop_background_backup():
    _stop_flag.set()


# ==========================================================================
# EXAMPLE — मॅन्युअली टेस्ट करण्यासाठी (उदा. header.py च्या Backup बटणातून
# सुद्धा run_backup_once(force=True) कॉल करता येईल)
# ==========================================================================
if __name__ == "__main__":
    ok, msg = run_backup_once(force=True)
    print(msg)
