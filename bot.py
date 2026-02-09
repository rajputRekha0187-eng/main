import os, io, json, time, random, subprocess, requests
from datetime import datetime, timedelta
from dateutil import tz
import smtplib
from email.message import EmailMessage

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCreds

# =========================================================
# CONFIG
# =========================================================

EMAIL_FROM = os.environ["REPORT_EMAIL_FROM"]
EMAIL_TO   = os.environ["REPORT_EMAIL_TO"]
EMAIL_PASS = os.environ["REPORT_EMAIL_PASSWORD"]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHATS = os.environ.get("TELEGRAM_CHAT_ID", "").split(",")

VIDEO_FOLDER_ID = os.environ["VIDEO_FOLDER_ID"]
AUDIO_FOLDER_ID = os.environ["AUDIO_FOLDER_ID"]
STATE_FILE_ID   = os.environ["STATE_FOLDER_ID"]

TOTAL_VIDEOS = int(os.environ.get("TOTAL_VIDEOS", "0"))

TZ = tz.gettz(os.environ["CHANNEL_TIMEZONE"])

START_DATE = datetime(2026, 2, 10, 8, 0, tzinfo=TZ)
TIME_SLOTS = [8, 12, 16]
MAX_PER_DAY = 3

BATCH_SIZE = 10
SLEEP_24H = 24.1 * 3600
RECHECK_20_MIN = 20 * 60

WATERMARK = "@ArtWeaver"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SAFE_WATERMARK = WATERMARK.replace("'", "\\'")

BASE_DESCRIPTION = """Disclaimer: Copyright Disclaimer under section 107 of the Copyright Act 1976.
Fair use is permitted for criticism, comment, news reporting, teaching, scholarship and research.

ArtCraft.
"""

TAG_POOL = [
    "ArtCraft","Art","Craft","DIY","Drawing","Painting","Sketching",
    "Satisfying art","ASMR art","Viral art","Trending art","Creative",
    "Handmade","Artist","Shorts"
]

# =========================================================
# BOT STATE
# =========================================================

PAUSED = False
FORCE_WAKE = False
LAST_UPDATE_ID = 0

# =========================================================
# TELEGRAM
# =========================================================

def tg(msg):
    if not TELEGRAM_TOKEN:
        return
    for c in TELEGRAM_CHATS:
        if c.strip():
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": c.strip(), "text": msg, "parse_mode": "HTML"},
                timeout=10
            )

def progress_bar(done, total, size=20):
    if total <= 0:
        return "?"
    filled = int(size * done / total)
    return "█" * filled + "░" * (size - filled)

def poll_commands(last_processed):
    global PAUSED, FORCE_WAKE, LAST_UPDATE_ID
    if not TELEGRAM_TOKEN:
        return

    r = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
        params={"offset": LAST_UPDATE_ID + 1},
        timeout=10
    ).json()

    for u in r.get("result", []):
        LAST_UPDATE_ID = u["update_id"]
        if "message" not in u:
            continue

        text = u["message"].get("text", "").lower().strip()

        if text == "/pause":
            PAUSED = True
            tg("⏸ <b>Paused</b>")

        elif text == "/resume":
            PAUSED = False
            tg("▶️ <b>Resumed</b>")

        elif text == "/wake":
            FORCE_WAKE = True
            tg("⏰ <b>Wake requested</b>")

        elif text == "/status":
            bar = progress_bar(last_processed, TOTAL_VIDEOS)
            tg(
                f"📊 <b>Status</b>\n\n"
                f"{bar}\n"
                f"{last_processed} / {TOTAL_VIDEOS}\n"
                f"Paused: {PAUSED}"
            )

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
# HELPERS
# =========================================================

def next_filename(n):
    return f"{n:03d}craft.mp4"

def load_state():
    buf = io.BytesIO()
    MediaIoBaseDownload(buf, drive.files().get_media(fileId=STATE_FILE_ID)).next_chunk()
    try:
        return json.loads(buf.getvalue()).get("last_processed", 0)
    except:
        return 0

def save_state(n):
    data = json.dumps({"last_processed": n}).encode()
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/json")
    drive.files().update(fileId=STATE_FILE_ID, media_body=media).execute()

def find_video(name):
    res = drive.files().list(
        q=f"'{VIDEO_FOLDER_ID}' in parents and name='{name}' and trashed=false",
        fields="files(id,name)",
        pageSize=1
    ).execute()
    files = res.get("files", [])
    return files[0] if files else None

def list_audios():
    return drive.files().list(
        q=f"'{AUDIO_FOLDER_ID}' in parents and trashed=false",
        fields="files(id,name)"
    ).execute()["files"]

def download(file_id, path):
    req = drive.files().get_media(fileId=file_id)
    with open(path, "wb") as f:
        dl = MediaIoBaseDownload(f, req)
        done = False
        while not done:
            _, done = dl.next_chunk()

def random_title():
    return random.choice([
        "Oddly Satisfying Art ✨",
        "Trust the process 👀",
        "ASMR Art 🎨",
        "Rate this 1–10 😱",
        "Relaxing Craft Process 🖌️"
    ])

def wait_for_upload_limit(last_processed):
    global FORCE_WAKE
    tg("⛔ <b>Upload limit reached</b>\n😴 Sleeping 24.1 hours")

    slept = 0
    while slept < SLEEP_24H:
        poll_commands(last_processed)
        if FORCE_WAKE:
            FORCE_WAKE = False
            tg("⏰ <b>Wake forced — retrying</b>")
            return
        time.sleep(60)
        slept += 60

    tg("🔁 <b>Retrying every 20 minutes</b>")
    while True:
        poll_commands(last_processed)
        time.sleep(RECHECK_20_MIN)
        return

# =========================================================
# MAIN
# =========================================================

tg("🚀 <b>ArtCraft automation started</b>")

audios = list_audios()
last_processed = load_state()

schedule_day = START_DATE
uploaded_today = 0
batch_counter = 0

while True:
    poll_commands(last_processed)

    while PAUSED:
        time.sleep(30)
        poll_commands(last_processed)

    next_num = last_processed + 1
    fname = next_filename(next_num)
    file = find_video(fname)

    if not file:
        tg("🏁 <b>All videos completed</b>")
        break

    if uploaded_today >= MAX_PER_DAY:
        schedule_day += timedelta(days=1)
        uploaded_today = 0

    publish_at = schedule_day.replace(hour=TIME_SLOTS[uploaded_today])

    title = random_title()
    tags = random.sample(TAG_POOL, min(10, len(TAG_POOL)))
    description = f"{title}\n\n{BASE_DESCRIPTION}\n\n{', '.join(tags)}"

    save_state(next_num)
    last_processed = next_num
    batch_counter += 1

    vid = f"/tmp/{fname}"
    aud = random.choice(audios)
    aud_p = f"/tmp/{aud['name']}"
    out = f"/tmp/out_{fname}"

    download(file["id"], vid)
    download(aud["id"], aud_p)

    subprocess.run([
        "ffmpeg","-y",
        "-i",vid,"-i",aud_p,
        "-filter_complex",
        f"[1:a]volume=0.45[bg];"
        f"[0:v]drawtext=fontfile={FONT_PATH}:"
        f"text='{SAFE_WATERMARK}':x=10:y=10:fontsize=24:fontcolor=white@0.4[v]",
        "-map","[v]","-map","[bg]","-shortest",out
    ], check=True)

    while True:
        try:
            youtube.videos().insert(
                part="snippet,status",
                body={
                    "snippet":{
                        "title": title,
                        "description": description,
                        "tags": tags,
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
                wait_for_upload_limit(last_processed)
            else:
                raise

    tg(
        f"✅ <b>Scheduled</b>\n\n"
        f"{fname}\n"
        f"📝 {title}\n"
        f"🕒 {publish_at.strftime('%b %d • %H:%M IST')}"
    )

    os.remove(vid)
    os.remove(aud_p)
    os.remove(out)

    uploaded_today += 1
    time.sleep(random.randint(60,120))

    if batch_counter >= BATCH_SIZE:
        bar = progress_bar(last_processed, TOTAL_VIDEOS)
        tg(
            f"📦 <b>Batch completed</b>\n\n"
            f"{bar}\n"
            f"{last_processed} / {TOTAL_VIDEOS}"
        )
        batch_counter = 0

tg("🏁 <b>Automation finished safely</b>")
