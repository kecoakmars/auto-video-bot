import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Secret GDRIVE_CREDENTIALS belum terbaca!")
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def check_folders():
    service = get_drive_service()
    root_id = os.environ.get("GDRIVE_ROOT_FOLDER_ID")
    if not root_id:
        raise ValueError("Secret GDRIVE_ROOT_FOLDER_ID belum terbaca!")

    query = f"'{root_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = {f['name']: f['id'] for f in results.get('files', [])}

    expected = [
        "01-Referensi-Style",
        "02-Bahan-Video",
        "03-Hasil-Render"
    ]

    print("=== HASIL PENGECEKAN FOLDER GOOGLE DRIVE ===")
    all_ok = True
    for name in expected:
        if name in folders:
            print(f"[OK] {name} ditemukan (ID: {folders[name]})")
        else:
            print(f"[GAGAL] {name} TIDAK DITEMUKAN! Cek kembali penulisan nama folder.")
            all_ok = False

    if not all_ok:
        raise RuntimeError("Ada folder yang belum sesuai. Perbaiki nama folder di Google Drive.")
    print("\nSemua folder terhubung dengan sempurna!")

if __name__ == "__main__":
    check_folders()
