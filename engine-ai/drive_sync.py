import io
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mkv', '.webm', '.avi')

def get_drive_service():
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Secret GDRIVE_CREDENTIALS belum terbaca!")
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def get_folder_ids(service=None):
    if service is None:
        service = get_drive_service()
    root_id = os.environ.get("GDRIVE_ROOT_FOLDER_ID")
    if not root_id:
        raise ValueError("Secret GDRIVE_ROOT_FOLDER_ID belum terbaca!")

    query = f"'{root_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    return {f['name']: f['id'] for f in results.get('files', [])}

def check_folders():
    folders = get_folder_ids()
    expected = ["01-Referensi-Style", "02-Bahan-Video", "03-Hasil-Render"]

    print("=== HASIL PENGECEKAN FOLDER GOOGLE DRIVE ===")
    all_ok = True
    for name in expected:
        if name in folders:
            print(f"[OK] {name} ditemukan (ID: {folders[name]})")
        else:
            print(f"[GAGAL] {name} TIDAK DITEMUKAN!")
            all_ok = False

    if not all_ok:
        raise RuntimeError("Ada folder yang belum sesuai di Google Drive.")
    print("\nSemua folder terhubung dengan sempurna!")

def download_bahan_video(dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    service = get_drive_service()
    folders = get_folder_ids(service)
    bahan_id = folders["02-Bahan-Video"]

    query = f"'{bahan_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name, createdTime)", orderBy="name").execute()
    files = results.get('files', [])

    downloaded = []
    for f in files:
        if not f['name'].lower().endswith(VIDEO_EXTENSIONS):
            continue
        local_path = os.path.join(dest_dir, f['name'])
        print(f"Mengunduh: {f['name']}...")
        request = service.files().get_media(fileId=f['id'])
        with io.FileIO(local_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        downloaded.append({
            "id": f['id'],
            "name": f['name'],
            "local_path": local_path
        })
    return downloaded

def upload_final_video(local_path, output_name):
    service = get_drive_service()
    folders = get_folder_ids(service)
    hasil_id = folders["03-Hasil-Render"]

    file_metadata = {
        'name': output_name,
        'parents': [hasil_id]
    }
    media = MediaFileUpload(local_path, mimetype='video/mp4', resumable=True)
    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()
    print(f"[SUKSES] Video terunggah ke 03-Hasil-Render: {uploaded.get('name')} (ID: {uploaded.get('id')})")
    return uploaded.get('id')

def archive_processed_files(file_ids):
    if not file_ids:
        return
    service = get_drive_service()
    folders = get_folder_ids(service)
    bahan_id = folders["02-Bahan-Video"]

    # Cari atau buat subfolder 'Selesai' di dalam 02-Bahan-Video
    query = f"'{bahan_id}' in parents and name = 'Selesai' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = service.files().list(q=query, fields="files(id)").execute().get('files', [])
    if res:
        selesai_id = res[0]['id']
    else:
        meta = {
            'name': 'Selesai',
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [bahan_id]
        }
        selesai_id = service.files().create(body=meta, fields='id').execute()['id']

    for fid in file_ids:
        service.files().update(
            fileId=fid,
            addParents=selesai_id,
            removeParents=bahan_id,
            fields='id, parents'
        ).execute()
    print(f"[ARSIP] {len(file_ids)} file mentah dipindahkan ke folder 'Selesai'.")

if __name__ == "__main__":
    check_folders()
