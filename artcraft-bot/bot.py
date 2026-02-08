import os, io, json, random, time, subprocess
from datetime import datetime, timedelta
from dateutil import tz

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCreds

# ---------------- CONFIG ---------------- #

VIDEO_FOLDER = os.environ["VIDEO_FOLDER_ID"]
AUDIO_FOLDER = os.environ["AUDIO_FOLDER_ID"]
STATE_FOLDER = os.environ["STATE_FOLDER_ID"]

TZ = tz.gettz(os.environ["CHANNEL_TIMEZONE"])

START_DATE = datetime(2026, 2, 10, 8, 0, tzinfo=TZ)
SLOTS = [8, 12, 16]

MAX_PER_DAY = 3
BATCH_LIMIT = 10
SLEEP_24H = 24.1 * 3600

WATERMARK = "@ArtWeaver"

# ---------------- AUTH ---------------- #

drive_creds = Credentials.from_service_account_info(
    json.loads(os.environ["DRIVE_SERVICE_ACCOUNT_JSON"]),
    scopes=["https://www.googleapis.com/auth/drive"]
)

yt_creds = UserCreds.from_authorized_user_info(
    json.loads(os.environ["YOUTUBE_TOKEN_JSON"]),
    scopes=["https://www.googleapis.com/auth/youtube.upload"]
)

drive = build("drive", "v3", credentials=drive_creds)
youtube = build("youtube", "v3", credentials=yt_creds)

# ---------------- HELPERS ---------------- #

def download(file_id, path):
    req = drive.files().get_media(fileId=file_id)
    fh = io.FileIO(path, "wb")
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()

def list_files(folder):
    q = f"'{folder}' in parents and trashed=false"
    res = drive.files().list(q=q, fields="files(id,name)").execute()
    return res["files"]

def load_state():
    files = list_files(STATE_FOLDER)
    if not files:
        return set()
    fid = files[0]["id"]
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, drive.files().get_media(fileId=fid))
    downloader.next_chunk()
    return set(json.loads(buf.getvalue()))

def save_state(done):
    data = json.dumps(list(done)).encode()
    media = MediaFileUpload(io.BytesIO(data), mimetype="application/json")
    drive.files().update(fileId=list_files(STATE_FOLDER)[0]["id"], media_body=media).execute()

# ---------------- MAIN ---------------- #

processed = load_state()
videos = sorted(list_files(VIDEO_FOLDER), key=lambda x: x["name"])
audios = list_files(AUDIO_FOLDER)

schedule_time = START_DATE
uploaded_today = 0
batch = 0

for v in videos:
    if v["id"] in processed:
        continue

    if batch == BATCH_LIMIT:
        time.sleep(SLEEP_24H)
        batch = 0

    if uploaded_today == MAX_PER_DAY:
        schedule_time += timedelta(days=1)
        uploaded_today = 0

    slot_hour = SLOTS[uploaded_today]
    publish_at = schedule_time.replace(hour=slot_hour)

    vid_path = f"/tmp/{v['name']}"
    aud = random.choice(audios)
    aud_path = f"/tmp/{aud['name']}"
    out_path = f"/tmp/out_{v['name']}"

    download(v["id"], vid_path)
    download(aud["id"], aud_path)

    vol = random.uniform(0.4, 0.5)
    pos = random.choice(["10:10", "10:H-th-10"])

    cmd = [
        "ffmpeg", "-y",
        "-i", vid_path,
        "-i", aud_path,
        "-filter_complex",
        f"[0:a]volume=0[a0];[1:a]volume={vol}[a1];"
        f"[0:v]drawtext=text='{WATERMARK}':x=10:y={pos}:fontsize=24:fontcolor=white@0.4[v]",
        "-map", "[v]",
        "-map", "[a1]",
        "-shortest",
        out_path
    ]
    subprocess.run(cmd, check=True)

    title = v["name"].replace("_", " ").replace(".mp4", "")
    description = f"""{title}

Disclaimer: - Copyright Disclaimer under section 107 of the Copyright Act 1976. allowance is made for "fair use" for purposes such as criticism. Comment. News. reporting. Teaching. Scholarship . and research. Fair use is a use permitted by copy status that might otherwise be infringing Non-profit. Educational or per Sonal use tips the balance in favor

ArtCraft.
#bayshotyt #freefire #foryou #shotgun #shorts
"""

    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "26"
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at.isoformat()
            }
        },
        media_body=MediaFileUpload(out_path)
    )
    req.execute()

    processed.add(v["id"])
    save_state(processed)

    os.remove(vid_path)
    os.remove(aud_path)
    os.remove(out_path)

    uploaded_today += 1
    batch += 1
    time.sleep(random.randint(60, 120))

print("DONE")
