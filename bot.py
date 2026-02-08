import smtplib
from email.message import EmailMessage
import os, io, json, random, time, subprocess, re
from datetime import datetime, timedelta
from dateutil import tz

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCreds

# =========================================================
# CONFIG
# =========================================================

EMAIL_FROM = os.environ["REPORT_EMAIL_FROM"]
EMAIL_TO = os.environ["REPORT_EMAIL_TO"]
EMAIL_PASS = os.environ["REPORT_EMAIL_PASSWORD"]

VIDEO_FOLDER = os.environ["VIDEO_FOLDER_ID"]
AUDIO_FOLDER = os.environ["AUDIO_FOLDER_ID"]
STATE_FOLDER = os.environ["STATE_FOLDER_ID"]

TZ = tz.gettz(os.environ["CHANNEL_TIMEZONE"])

START_DATE = datetime(2026, 2, 10, 8, 0, tzinfo=TZ)
TIME_SLOTS = [8, 12, 16]       # STRICT 3 PER DAY
MAX_PER_DAY = 3
SAFE_MAX_SCHEDULE = 10
SLEEP_24H = 24.1 * 3600

WATERMARK = "@ArtWeaver"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# =========================================================
# AUTH
# =========================================================

drive = build(
    "drive", "v3",
    credentials=Credentials.from_service_account_info(
        json.loads(os.environ["DRIVE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/drive"]
    )
)

youtube = build(
    "youtube", "v3",
    credentials=UserCreds.from_authorized_user_info(
        json.loads(os.environ["YOUTUBE_TOKEN_JSON"]),
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
)

# =========================================================
# EMAIL
# =========================================================

def send_report_email(batch_no, rows, limit):
    msg = EmailMessage()
    msg["Subject"] = f"ArtCraft Upload Report – Batch {batch_no}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    msg.set_content(
        "ART & CRAFT – YOUTUBE REPORT\n\n" +
        "\n".join(rows) +
        f"\n\nSchedule limit respected: {limit}"
    )

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.send_message(msg)

# =========================================================
# TITLE
# =========================================================

def get_random_title():
    return random.choice([
        "Oddly Satisfying Art ✨ #shorts",
        "Trust the process 👀 #art",
        "ASMR Drawing 🎨",
        "Rate this 1–10 😱",
        "I tried this art hack 🔥",
        "How to draw this ✏️"
    ])

# =========================================================
# TAGS + DESCRIPTION
# =========================================================

TAG_POOL = [
    "Art","DIY","Drawing","Painting","Craft","Shorts",
    "Satisfying art","ASMR art","Trending art","Viral art"
]

FIXED_DESCRIPTION = """Disclaimer: - Copyright Disclaimer under section 107 of the Copyright Act 1976...
ArtCraft.
"""

# =========================================================
# HELPERS
# =========================================================

def list_files(folder):
    return drive.files().list(
        q=f"'{folder}' in parents and trashed=false",
        fields="files(id,name)"
    ).execute()["files"]

def download(fid, path):
    req = drive.files().get_media(fileId=fid)
    fh = io.FileIO(path, "wb")
    dl = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = dl.next_chunk()

def numeric_key(name):
    m = re.search(r"\d+", name)
    return int(m.group()) if m else 0

def remaining_schedule_slots():
    try:
        res = youtube.videos().list(
            part="status",
            mine=True,
            maxResults=50
        ).execute()
        scheduled = sum(
            1 for v in res.get("items", [])
            if v["status"]["privacyStatus"] == "private"
            and v["status"].get("publishAt")
        )
        return max(0, SAFE_MAX_SCHEDULE - scheduled)
    except:
        return SAFE_MAX_SCHEDULE

def save_state(state_id, processed):
    drive.files().update(
        fileId=state_id,
        media_body=MediaFileUpload(
            filename=None,
            mimetype="application/json",
            body=json.dumps(list(processed)).encode("utf-8"),
            resumable=False
        )
    ).execute()

def wait_for_upload_limit_reset():
    print("⚠️ Upload limit hit. Sleeping 24 hours...")
    time.sleep(24 * 3600)

    while True:
        try:
            youtube.videos().list(
                part="status",
                mine=True,
                maxResults=1
            ).execute()
            print("✅ Upload limit reset. Resuming.")
            return
        except HttpError as e:
            if "uploadLimitExceeded" in str(e):
                print("⏳ Still limited. Checking again in 20 minutes...")
                time.sleep(20 * 60)
            else:
                raise

# =========================================================
# MAIN
# =========================================================

# LOAD STATE (processed.json MUST BE [])
state_file = list_files(STATE_FOLDER)[0]["id"]
buf = io.BytesIO()
MediaIoBaseDownload(buf, drive.files().get_media(fileId=state_file)).next_chunk()

try:
    processed = set(json.loads(buf.getvalue()))
except:
    processed = set()

videos = sorted(
    list_files(VIDEO_FOLDER),
    key=lambda x: numeric_key(x["name"])
)
audios = list_files(AUDIO_FOLDER)

schedule_day = START_DATE
uploaded_today = 0
batch_no = 1
batch_count = 0
report_rows = []

limit = remaining_schedule_slots()

for v in videos:
    if v["id"] in processed:
        continue

    if uploaded_today >= MAX_PER_DAY:
        schedule_day += timedelta(days=1)
        uploaded_today = 0

    if batch_count >= limit:
        send_report_email(batch_no, report_rows, limit)
        batch_no += 1
        report_rows = []
        batch_count = 0
        time.sleep(SLEEP_24H)
        limit = remaining_schedule_slots()

    publish_at = schedule_day.replace(hour=TIME_SLOTS[uploaded_today])
    title = get_random_title()

    vid = f"/tmp/{v['name']}"
    aud = random.choice(audios)
    aud_p = f"/tmp/{aud['name']}"
    out = f"/tmp/out_{v['name']}"

    print(f"🎬 Processing {v['name']} → {publish_at}")

    download(v["id"], vid)
    download(aud["id"], aud_p)

    # MARK AS PROCESSED BEFORE UPLOAD (CRASH SAFE)
    processed.add(v["id"])
    save_state(state_file, processed)

    subprocess.run([
        "ffmpeg","-y",
        "-i",vid,
        "-i",aud_p,
        "-filter_complex",
        f"[1:a]volume=0.45[bg];"
        f"[0:v]drawtext=fontfile={FONT_PATH}:"
        f"text='{WATERMARK}':x=10:y=10:fontsize=24:fontcolor=white@0.4[v]",
        "-map","[v]","-map","[bg]",
        "-shortest", out
    ], check=True)

    while True:
        try:
            youtube.videos().insert(
                part="snippet,status",
                body={
                    "snippet":{
                        "title": title,
                        "description": FIXED_DESCRIPTION,
                        "tags": random.sample(TAG_POOL, 5),
                        "categoryId":"26"
                    },
                    "status":{
                        "privacyStatus":"private",
                        "publishAt": publish_at.isoformat()
                    }
                },
                media_body=MediaFileUpload(out)
            ).execute()
            break
        except HttpError as e:
            if "uploadLimitExceeded" in str(e):
                wait_for_upload_limit_reset()
            else:
                raise

    report_rows.append(f"{v['name']} → {publish_at}")

    os.remove(vid)
    os.remove(aud_p)
    os.remove(out)

    uploaded_today += 1
    batch_count += 1
    time.sleep(random.randint(60,120))

# FINAL REPORT (ALWAYS SEND)
if report_rows:
    send_report_email(batch_no, report_rows, limit)

print("AUTOMATION RUNNING – SAFE MODE ✅")
