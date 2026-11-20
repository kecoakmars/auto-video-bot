import os
import json
from datetime import datetime, timezone, timedelta
from drive_sync import upload_final_video, archive_processed_files

def main():
    final_video = "remotion/out/final.mp4"
    if not os.path.exists(final_video):
        raise FileNotFoundError("File hasil render remotion/out/final.mp4 tidak ditemukan!")

    wib = timezone(timedelta(hours=7))
    timestamp = datetime.now(wib).strftime("%Y%m%d_%H%M")
    output_name = f"TalkingHead_Edited_{timestamp}.mp4"

    upload_final_video(final_video, output_name)

    if os.path.exists("workspace/prep_manifest.json"):
        with open("workspace/prep_manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        archive_processed_files(manifest.get("drive_file_ids", []))

if __name__ == "__main__":
    main()
