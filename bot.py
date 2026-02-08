import smtplib
from email.message import EmailMessage
import os, io, json, random, time, subprocess
from datetime import datetime, timedelta
from dateutil import tz

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCreds

# =========================================================
# CONFIG
# =========================================================

EMAIL_FROM = os.environ["REPORT_EMAIL_FROM"]
EMAIL_TO = os.environ["REPORT_EMAIL_TO"]
EMAIL_PASS = os.environ["REPORT_EMAIL_PASSWORD"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

VIDEO_FOLDER = os.environ["VIDEO_FOLDER_ID"]
AUDIO_FOLDER = os.environ["AUDIO_FOLDER_ID"]
STATE_FOLDER = os.environ["STATE_FOLDER_ID"]

TZ = tz.gettz(os.environ["CHANNEL_TIMEZONE"])

START_DATE = datetime(2026, 2, 10, 8, 0, tzinfo=TZ)
TIME_SLOTS = [8, 12, 16]
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
# EMAIL REPORT
# =========================================================

def send_report_email(batch_no, rows, detected_limit):
    msg = EmailMessage()
    msg["Subject"] = f"ArtCraft Upload Report – Batch {batch_no} Completed"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    table = "\n".join(rows)

    msg.set_content(f"""
ART & CRAFT – YOUTUBE SCHEDULING REPORT
=====================================

Batch Number        : {batch_no}
Detected Limit      : {detected_limit}
Uploaded This Batch : {len(rows)}
Sleep Duration      : 24.1 hours

----------------------------------------------------
| # | Video File | Generated Title | Date | Time |
----------------------------------------------------
{table}
----------------------------------------------------

Status: SAFE – YouTube scheduling limit respected
""")

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
        s.starttls()
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.send_message(msg)

# =========================================================
# TITLE GENERATOR
# =========================================================

def get_random_title():
    adjectives = ["Satisfying","Oddly Satisfying","Relaxing","Crazy","Impossible","Realistic",
                  "3D","Glowing","Neon","Tiny","Huge","Quick","Easy","Simple","Complex",
                  "Abstract","Detailed","Messy","Clean","Perfect"]
    actions = ["Drawing","Painting","Sketching","Sculpting","Crafting","Mixing","Designing",
               "Coloring","Building","Restoring","Doodling","Shading","Layering","Carving",
               "Pouring","Spraying"]
    mediums = ["Acrylics","Watercolors","Pencil","Charcoal","Resin","Clay","Polymer Clay",
               "Posca Markers","Gouache","Spray Paint","Oil Pastels","Digital Art",
               "Procreate","Ink","Tape","Paper","Origami","Slime"]
    subjects = ["Anime Eyes","a Dragon","a Landscape","a Portrait","an Illusion","a Logo",
                "a Mandala","a Flower","a Sunset","a Galaxy","a Pattern","Textures",
                "a Face","Hands","Lips","a 3D Hole","Room Decor","Stickers"]
    hooks = ["Wait for the end","Don't blink","Trust the process","You won't believe this",
             "ASMR Art","Art Challenge","Guess the drawing","Rate this 1-10"]
    emojis = ["🎨","✨","🔥","🖌️","😱","🤩","🌈","👀","🤯"]

    t = random.randint(1, 7)
    if t == 1:
        return f"{random.choice(adjectives)} {random.choice(mediums)} {random.choice(actions)} {random.choice(emojis)} #shorts"
    elif t == 2:
        return f"How to {random.choice(actions).lower()} {random.choice(subjects)} ({random.choice(adjectives)}) {random.choice(emojis)}"
    elif t == 3:
        return f"{random.choice(hooks)}... {random.choice(emojis)} #art"
    elif t == 4:
        return f"{random.choice(actions)} {random.choice(subjects)} with {random.choice(mediums)} {random.choice(emojis)}"
    elif t == 5:
        return f"I tried this {random.choice(adjectives)} Art Hack! {random.choice(emojis)}"
    elif t == 6:
        return f"Day {random.randint(1,365)} of {random.choice(actions)} every day {random.choice(emojis)}"
    else:
        return f"ASMR: {random.choice(actions)} {random.choice(mediums)} ({random.choice(adjectives)}) {random.choice(emojis)}"

# =========================================================
# TAGS + DESCRIPTION
# =========================================================

TAG_POOL = [
"ArtCraft","Art","Craft","DIY","Drawing","Painting","Sketching","How to draw","Tutorial",
"Artist","Creative","Handmade","Paper craft","Origami","Acrylic painting","Watercolor",
"Digital art","Speedpaint","Satisfying art","Art hacks","DIY hacks","Easy drawing",
"Anime drawing","Realistic drawing","3D art","Optical illusion","Calligraphy","Mandala",
"Graffiti","Street art","Fluid art","Resin art","Clay art","Canvas painting","Pencil sketch",
"Markers","Procreate","Art vlog","Viral art","Trending art","ASMR art","Aesthetic",
"Miniature","Doodle","Zentangle","Abstract art","Modern art","Sculpture","Pottery",
"Home decor DIY","Art challenge","Inspiration","Motivation"
]

FIXED_DESCRIPTION = """Disclaimer: - Copyright Disclaimer under section 107 of the Copyright Act 1976. allowance is made for "fair use" for purposes such as criticism. Comment. News. reporting. Teaching. Scholarship . and research. Fair use is a use permitted by copy status that might otherwise be infringing Non-profit. Educational or per Sonal use tips the balance in favor

ArtCraft.
#bayshotyt #freefire #foryou #freefireconta #spas12 #aimbotfreefire #hackfreefire #sho
They think I'm an Emulatortgunhandcam
#shotgun #x1freefire #freefirebrasil #freefireclipes #melhoresmomentos #handcam #loud
a01,a11,a10,a20,a30,50,a70,a80, iphone,
#freefire #freefirehighlights #equipou #habash #bestplayer #m1014 #spas12 #dpifreefire #contarara #bestmoments #Iphonefreefire #androidfreefire #equipou ,
blackn444, bak, loud, ph, movimentação, como subir capa, como colocar gel rápido, free fire pro,pro player, ff, higlight, piuzinho, el gato, sansung a10, jogando no a10, jogador mestre, mobile nivel emulador, level up, nobru, como subir capa, mobile, kauan vm, kauan free fire, menino capudo, revelacao mobile, free fire argentina, free fire Tailândia, free fire, heróico, mastro, mestre, x1 dos youtubers free fire
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

def remaining_schedule_slots():
    try:
        res = youtube.videos().list(
            part="status",
            mine=True,
            maxResults=50
        ).execute()
        scheduled = sum(
            1 for v in res.get("items", [])
            if v["status"]["privacyStatus"] == "private" and v["status"].get("publishAt")
        )
        return max(0, SAFE_MAX_SCHEDULE - scheduled)
    except:
        return SAFE_MAX_SCHEDULE

# =========================================================
# MAIN
# =========================================================

processed = set()
state_file = list_files(STATE_FOLDER)[0]["id"]

buf = io.BytesIO()
MediaIoBaseDownload(buf, drive.files().get_media(fileId=state_file)).next_chunk()
try:
    processed = set(json.loads(buf.getvalue()))
except:
    processed = set()

videos = sorted(list_files(VIDEO_FOLDER), key=lambda x: x["name"])
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

    if batch_count >= limit:
        send_report_email(batch_no, report_rows, limit)
        batch_no += 1
        report_rows = []
        batch_count = 0
        time.sleep(SLEEP_24H)
        limit = remaining_schedule_slots()

    if uploaded_today == MAX_PER_DAY:
        schedule_day += timedelta(days=1)
        uploaded_today = 0

    publish_at = schedule_day.replace(hour=TIME_SLOTS[uploaded_today])
    title = get_random_title()

    vid = f"/tmp/{v['name']}"
    aud = random.choice(audios)
    aud_p = f"/tmp/{aud['name']}"
    out = f"/tmp/out_{v['name']}"

    download(v["id"], vid)
    download(aud["id"], aud_p)

    subprocess.run([
        "ffmpeg", "-y",
        "-i", vid,
        "-i", aud_p,
        "-filter_complex",
        f"[1:a]volume={random.uniform(0.4,0.5)}[bg];"
        f"[0:v]drawtext=fontfile={FONT_PATH}:"
        f"text='{WATERMARK}':x=10:y=10:fontsize=24:fontcolor=white@0.4[v]",
        "-map", "[v]",
        "-map", "[bg]",
        "-shortest",
        out
    ], check=True)

    youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet":{
                "title": title,
                "description": FIXED_DESCRIPTION,
                "tags": random.sample(TAG_POOL, 25),
                "categoryId":"26"
            },
            "status":{
                "privacyStatus":"private",
                "publishAt": publish_at.isoformat()
            }
        },
        media_body=MediaFileUpload(out)
    ).execute()

    report_rows.append(
        f"| {batch_count+1} | {v['name']} | {title[:35]} | {publish_at.date()} | {publish_at.hour}:00 |"
    )

    processed.add(v["id"])
    drive.files().update(
        fileId=state_file,
        media_body=MediaFileUpload(
            io.BytesIO(json.dumps(list(processed)).encode()),
            mimetype="application/json"
        )
    ).execute()

    os.remove(vid)
    os.remove(aud_p)
    os.remove(out)

    uploaded_today += 1
    batch_count += 1
    time.sleep(random.randint(60,120))

print("AUTOMATION RUNNING FOREVER")
