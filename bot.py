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

TOTAL_VIDEOS = int(os.environ["TOTAL_VIDEOS"])

TZ = tz.gettz(os.environ["CHANNEL_TIMEZONE"])

START_DATE = datetime(2026, 2, 10, 8, 0, tzinfo=TZ)
TIME_SLOTS = [8, 12, 16]
MAX_PER_DAY = 3

MIN_REQUIRED_SLOTS = 10
SLEEP_24H = 24.1 * 3600
RECHECK_20_MIN = 20 * 60

WATERMARK = "@ArtWeaver"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# =========================================================
# CONSTANT CONTENT
# =========================================================

BASE_DESCRIPTION = """Disclaimer: - Copyright Disclaimer under section 107 of the Copyright Act 1976. allowance is made for "fair use" for purposes such as criticism. Comment. News. reporting. Teaching. Scholarship . and research. Fair use is a use permitted by copy status that might otherwise be infringing Non-profit. Educational or per Sonal use tips the balance in favor

ArtCraft.
"""

TAG_POOL = [
    "ArtCraft","Art","Craft","DIY","Drawing","Painting","Sketching",
    "Satisfying art","ASMR art","Viral art","Trending art","Creative",
    "Handmade","Artist","Shorts"
]

# =========================================================
# TELEGRAM STATE
# =========================================================

BOT_STATE = {
    "paused": False,
    "force_check": False
}

# =========================================================
# TELEGRAM HELPERS
# =========================================================

def progress_bar(done, total, size=20):
    filled = int(size * done / total)
    return "█" * filled + "░" * (size - filled)

def tg_send(text, with_buttons=True):
    if not TELEGRAM_TOKEN:
        return

    keyboard = {
        "inline_keyboard": [
            [{"text": "▶️ Wake & Check Now", "callback_data": "wake"}],
            [
                {"text": "⏸ Pause", "callback_data": "pause"},
                {"text": "▶️ Resume", "callback_data": "resume"}
            ],
            [{"text": "📊 Status", "callback_data": "status"}]
        ]
    } if with_buttons else None

    for chat in TELEGRAM_CHATS:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": chat.strip(),
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard
            }
        )

def poll_telegram():
    if not TELEGRAM_TOKEN:
        return
    try:
        res = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            timeout=10
        ).json()

        for u in res.get("result", []):
            if "callback_query" not in u:
                continue

            data = u["callback_query"]["data"]
            if data == "pause":
                BOT_STATE["paused"] = True
            elif data == "resume":
                BOT_STATE["paused"] = False
            elif data == "wake":
                BOT_STATE["force_check"] = True
    except:
        pass

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
    return json.loads(buf.getvalue()).get("last_processed", 0)

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
    return res.get("files", [None])[0]

def list_audios():
    return drive.files().list(
        q=f"'{AUDIO_FOLDER_ID}' in parents and trashed=false",
        fields="files(id,name)"
    ).execute()["files"]

def download(fid, path):
    req = drive.files().get_media(fileId=fid)
    with open(path, "wb") as f:
        dl = MediaIoBaseDownload(f, req)
        done = False
        while not done:
            _, done = dl.next_chunk()

def get_random_title():
    return random.choice([
        "Oddly Satisfying Art ✨",
        "Trust the process 👀",
        "ASMR Art 🎨",
        "Rate this 1–10 😱",
        "I tried this art hack 🔥",
        "Relaxing Craft Process 🖌️"
    ])

def remaining_slots():
    res = youtube.videos().list(part="status", mine=True, maxResults=50).execute()
    scheduled = sum(
        1 for v in res.get("items", [])
        if v["status"]["privacyStatus"] == "private"
        and v["status"].get("publishAt")
    )
    return max(0, MIN_REQUIRED_SLOTS - scheduled)

def wait_for_limit_reset():
    tg_send("⛔ <b>Upload limit reached</b>\n😴 Sleeping 24.1 hours")

    slept = 0
    while slept < SLEEP_24H:
        poll_telegram()
        if BOT_STATE["force_check"]:
            BOT_STATE["force_check"] = False
            break
        time.sleep(60)
        slept += 60

    while True:
        poll_telegram()
        slots = remaining_slots()
        if slots >= MIN_REQUIRED_SLOTS:
            tg_send("✅ <b>Upload slots available</b>\n🚀 Resuming")
            return
        time.sleep(RECHECK_20_MIN)

# =========================================================
# MAIN
# =========================================================

tg_send("🚀 <b>ArtCraft automation started</b>")

audios = list_audios()
last_processed = load_state()

schedule_day = START_DATE
uploaded_today = 0
batch_count = 0

while True:
    poll_telegram()
    while BOT_STATE["paused"]:
        tg_send("⏸ <b>Bot paused</b>", with_buttons=False)
        time.sleep(60)
        poll_telegram()

    next_num = last_processed + 1
    fname = next_filename(next_num)
    file = find_video(fname)

    if not file:
        tg_send("🛑 <b>No next video found</b>\nAutomation finished.")
        break

    while remaining_slots() < MIN_REQUIRED_SLOTS:
        wait_for_limit_reset()

    if uploaded_today >= MAX_PER_DAY:
        schedule_day += timedelta(days=1)
        uploaded_today = 0

    publish_at = schedule_day.replace(hour=TIME_SLOTS[uploaded_today])
    title = get_random_title()
    tags = random.sample(TAG_POOL, 10)

    description = f"{title}\n\n{BASE_DESCRIPTION}\n\n{', '.join(tags)}"

    save_state(next_num)
    last_processed = next_num
    batch_count += 1

    vid = f"/tmp/{fname}"
    aud = random.choice(audios)
    aud_p = f"/tmp/{aud['name']}"
    out = f"/tmp/out_{fname}"

    download(file["id"], vid)
    download(aud["id"], aud_p)

    subprocess.run([
        "ffmpeg","-y","-i",vid,"-i",aud_p,
        "-filter_complex",
        f"[1:a]volume=0.45[bg];"
        f"[0:v]drawtext=fontfile={FONT_PATH}:"
        f"text='{WATERMARK}':x=10:y=10:fontsize=24:fontcolor=white@0.4[v]",
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
                wait_for_limit_reset()
            else:
                raise

    tg_send(
        f"✅ <b>Video Scheduled</b>\n\n"
        f"🎥 {fname}\n"
        f"📝 {title}\n"
        f"🕒 {publish_at.strftime('%b %d • %H:%M IST')}",
        with_buttons=False
    )

    os.remove(vid)
    os.remove(aud_p)
    os.remove(out)

    uploaded_today += 1
    time.sleep(random.randint(60,120))

    # ===== BATCH END PROGRESS =====
    if batch_count >= MIN_REQUIRED_SLOTS:
        bar = progress_bar(last_processed, TOTAL_VIDEOS)
        tg_send(
            f"📦 <b>Batch Completed</b>\n\n"
            f"📊 <b>Progress</b>\n"
            f"{bar} {last_processed} / {TOTAL_VIDEOS}\n"
            f"📁 Remaining: {TOTAL_VIDEOS - last_processed}"
        )
        batch_count = 0

tg_send("🏁 <b>Automation finished safely</b>")
