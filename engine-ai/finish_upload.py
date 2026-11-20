import os
import json
from datetime import datetime, timezone, timedelta
from drive_sync import upload_final_video, archive_processed_project

def main():
    final_video = "remotion/out/final.mp4"
    if not os.path.exists(final_video):
        raise FileNotFoundError("File hasil render remotion/out/final.mp4 tidak ditemukan!")

    manifest = {}
    if os.path.exists("workspace/prep_manifest.json"):
        with open("workspace/prep_manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)

    project_name = manifest.get("project_name", "TalkingHead")
    project_folder_id = manifest.get("project_folder_id")

    wib = timezone(timedelta(hours=7))
    timestamp = datetime.now(wib).strftime("%Y%m%d_%H%M")
    output_name = f"{project_name}_{timestamp}.mp4"

    upload_final_video(final_video, output_name, project_name=project_name)
    archive_processed_project(
        project_folder_id=project_folder_id,
        project_name=project_name,
        file_ids=manifest.get("drive_file_ids", [])
    )

if __name__ == "__main__":
    main()
