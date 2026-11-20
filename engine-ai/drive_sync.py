import io
import os
import json
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mkv', '.webm', '.avi')

def get_drive_service():
    client_id = os.environ.get("GDRIVE_CLIENT_ID")
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET")
    refresh_token = os.environ.get("GDRIVE_REFRESH_TOKEN")

    if client_id and client_secret and refresh_token:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        return build('drive', 'v3', credentials=creds)

    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Kredensial Google Drive belum terbaca!")
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

def get_or_create_subfolder(service, parent_id, folder_name):
    safe_name = folder_name.replace("'", "\\'")
    query = (
        f"'{parent_id}' in parents and name = '{safe_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = service.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    if res:
        return res[0]['id']
    meta = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    return service.files().create(body=meta, fields='id').execute()['id']

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

def download_bahan_video(dest_dir, target_folder_name=None):
    os.makedirs(dest_dir, exist_ok=True)
    service = get_drive_service()
    folders = get_folder_ids(service)
    bahan_id = folders["02-Bahan-Video"]

    # Cari subfolder proyek di dalam 02-Bahan-Video (kecuali 'Selesai')
    sub_query = (
        f"'{bahan_id}' in parents and mimeType = 'application/vnd.google-apps.folder' "
        f"and name != 'Selesai' and trashed = false"
    )
    subfolders = service.files().list(
        q=sub_query, fields="files(id, name, createdTime)", orderBy="createdTime desc"
    ).execute().get('files', [])

    active_folder_id = bahan_id
    active_folder_name = "General"

    if target_folder_name:
        matched = [sf for sf in subfolders if sf['name'].lower() == target_folder_name.strip().lower()]
        if not matched:
            available = [sf['name'] for sf in subfolders]
            raise FileNotFoundError(
                f"Folder '{target_folder_name}' tidak ditemukan di dalam 02-Bahan-Video! "
                f"Folder yang tersedia: {available}"
            )
        active_folder_id = matched[0]['id']
        active_folder_name = matched[0]['name']
    elif subfolders:
        # Otomatis pilih folder proyek terbaru jika input dikosongkan
        active_folder_id = subfolders[0]['id']
        active_folder_name = subfolders[0]['name']

    print(f"Membaca bahan video dari folder: 02-Bahan-Video/{active_folder_name}")

    query = f"'{active_folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
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

    return {
        "files": downloaded,
        "project_name": active_folder_name,
        "project_folder_id": active_folder_id if active_folder_id != bahan_id else None
    }

def upload_final_video(local_path, output_name, project_name=None):
    service = get_drive_service()
    folders = get_folder_ids(service)
    hasil_id = folders["03-Hasil-Render"]

    target_parent_id = hasil_id
    dest_label = "03-Hasil-Render"
    if project_name and project_name != "General":
        target_parent_id = get_or_create_subfolder(service, hasil_id, project_name)
        dest_label = f"03-Hasil-Render/{project_name}"

    file_metadata = {
        'name': output_name,
        'parents': [target_parent_id]
    }
    media = MediaFileUpload(local_path, mimetype='video/mp4', resumable=True)
    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()
    print(f"[SUKSES] Video terunggah ke {dest_label}: {uploaded.get('name')} (ID: {uploaded.get('id')})")
    return uploaded.get('id')

def archive_processed_project(project_folder_id, project_name, file_ids):
    service = get_drive_service()
    folders = get_folder_ids(service)
    bahan_id = folders["02-Bahan-Video"]
    selesai_id = get_or_create_subfolder(service, bahan_id, "Selesai")

    if project_folder_id:
        # Pindahkan seluruh folder proyek (misal 'IPTV') ke dalam 02-Bahan-Video/Selesai
        service.files().update(
            fileId=project_folder_id,
            addParents=selesai_id,
            removeParents=bahan_id,
            fields='id, parents'
        ).execute()
        print(f"[ARSIP] Folder '{project_name}' dipindahkan utuh ke 02-Bahan-Video/Selesai/{project_name}.")
    elif file_ids:
        for fid in file_ids:
            service.files().update(
                fileId=fid,
                addParents=selesai_id,
                removeParents=bahan_id,
                fields='id, parents'
            ).execute()
        print(f"[ARSIP] {len(file_ids)} file dipindahkan ke 02-Bahan-Video/Selesai.")

if __name__ == "__main__":
    check_folders()
