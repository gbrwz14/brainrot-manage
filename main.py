from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List
import os
import requests
from datetime import datetime
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# =========================================================
# CONFIG
# =========================================================

QUEUE_FILE = "server_queue.json"
INVALID_SERVERS_FILE = "invalid_servers.json"
STATUS_MESSAGE_FILE = "status_message.json"

INVALID_SERVER_COOLDOWN = 300
ACCOUNT_TIMEOUT = 600
TOTAL_ACCOUNTS = 25

executor = ThreadPoolExecutor(max_workers=10)

app = FastAPI()

# =========================================================
# WEBHOOKS
# =========================================================

WEBHOOKS = {
    "10-50M": "https://discord.com/api/webhooks/1479881579173118019/GSDVkO0yELWBFtc1jCatlNubyCqq207GYt7uSKpaK3BNfqF5rYTXufFwz5fbQl9sDu1l",
    "50-100M": "https://discord.com/api/webhooks/1479881604229763148/gnkIMNbe8PWrJe-TdpvbdZW_xkeo0uR3ujpb57Ao5-knnS42tiQ7yvFXZ0SXRPb_Y_9J",
    "100M-500M": "https://discord.com/api/webhooks/1479881636941398129/UAg3i6M52o3tzxoBz75cn8IgmSbYPfk3XWgIroEUFeqh6fUUVReG9miqMLDTKuUpc9sE",
    "500M-1B": "https://discord.com/api/webhooks/1479881660282568808/GA_ptoR8Xi3auFgNq4YYOZILDhSnZQco0DsAT5P404qqE3lphINhYgKVYaz1jPL41CFe",
    "1B+": "https://discord.com/api/webhooks/1479881689345036492/ceglYzLn089s1DYxk90zvM6takOMr4KtH33d9BekD66i58RtndE93FnNo010SUyLABpQ"
}

STATUS_WEBHOOK = "https://discord.com/api/webhooks/1479881542602981416/_AQfR4ioqLrwJ-vqSX5Fm6uyRN2LLEeg3vA7Ll6PwY355wbAALnVquqt2GAbC0qn_Wts"

# =========================================================
# MODELS
# =========================================================

class Brainrot(BaseModel):
    name: str
    value_per_second: str
    value_numeric: float
    count: int
    rarity: str


class ScanDetails(BaseModel):
    brainrots: List[Brainrot]
    has_rare: bool


class ScanReport(BaseModel):
    job_id: str
    player_count: int
    details: ScanDetails


class ServerQueue(BaseModel):
    job_id: str


# =========================================================
# MEMORY
# =========================================================

server_queue: List[str] = []
invalid_servers: Dict[str, float] = {}
active_accounts: Dict[str, float] = {}
scan_history: List[Dict] = []

status_message_id: Optional[str] = None

stats = {
    "total_scans": 0,
    "total_brainrots": 0,
    "brainrots_by_category": {
        "10-50M": 0,
        "50-100M": 0,
        "100M-500M": 0,
        "500M-1B": 0,
        "1B+": 0
    }
}

# =========================================================
# FILE HELPERS
# =========================================================

def load_json(file, default):

    try:
        if os.path.exists(file):
            with open(file, "r") as f:
                return json.load(f)
    except:
        pass

    return default


def save_json(file, data):

    try:
        with open(file, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass


def load_queue():
    global server_queue
    server_queue = load_json(QUEUE_FILE, [])


def save_queue():
    save_json(QUEUE_FILE, server_queue)


def load_invalid():
    global invalid_servers
    invalid_servers = load_json(INVALID_SERVERS_FILE, {})


def save_invalid():
    save_json(INVALID_SERVERS_FILE, invalid_servers)


def load_status_message():

    global status_message_id

    data = load_json(STATUS_MESSAGE_FILE, {})

    status_message_id = data.get("message_id")


def save_status_message(message_id):

    global status_message_id

    status_message_id = message_id

    save_json(STATUS_MESSAGE_FILE, {"message_id": message_id})


# =========================================================
# ACCOUNT TRACKING
# =========================================================

def mark_account_active(job_id: str):

    active_accounts[job_id] = datetime.utcnow().timestamp()


def get_active_accounts_count():

    now = datetime.utcnow().timestamp()

    active = 0

    for job, last in list(active_accounts.items()):

        if now - last < ACCOUNT_TIMEOUT:

            active += 1

        else:

            del active_accounts[job]

    return active


# =========================================================
# WEBHOOK SELECTOR
# =========================================================

def get_target_webhook(value):

    if value >= 1_000_000_000:
        return WEBHOOKS["1B+"]

    if value >= 500_000_000:
        return WEBHOOKS["500M-1B"]

    if value >= 100_000_000:
        return WEBHOOKS["100M-500M"]

    if value >= 50_000_000:
        return WEBHOOKS["50-100M"]

    if value >= 10_000_000:
        return WEBHOOKS["10-50M"]

    return None


# =========================================================
# WEBHOOK SEND
# =========================================================

def send_webhook_async(embed, webhook):

    try:

        requests.post(
            webhook,
            json={"embeds": [embed]},
            timeout=5
        )

    except Exception as e:

        print("Webhook error:", e)


# =========================================================
# BRAINROT LOG
# =========================================================

def send_brainrot_log(report: ScanReport):

    brainrots = report.details.brainrots

    if not brainrots:
        return

    top_value = max(br.value_numeric for br in brainrots)

    webhook = get_target_webhook(top_value)

    if not webhook:
        return

    brainrot_text = ""

    for br in brainrots:
        brainrot_text += f"{br.count}x {br.name} {br.value_per_second}\n"

    embed = {
        "title": "☠️ Brainrots Detectados",
        "color": 16711680,
        "fields": [
            {
                "name": "Brainrots",
                "value": f"```\n{brainrot_text}```",
                "inline": False
            },
            {
                "name": "Server",
                "value": report.job_id,
                "inline": False
            },
            {
                "name": "Players",
                "value": str(report.player_count),
                "inline": False
            }
        ],
        "timestamp": datetime.utcnow().isoformat()
    }

    executor.submit(send_webhook_async, embed, webhook)


# =========================================================
# STATUS SYSTEM
# =========================================================

def send_status():

    global status_message_id

    active = get_active_accounts_count()

    percent = (active / TOTAL_ACCOUNTS) * 100

    if percent >= 80:
        color = 3066993
    elif percent >= 50:
        color = 16776960
    else:
        color = 16711680

    embed = {
        "title": "STATUS DO NOTIFIER",
        "color": color,
        "fields": [
            {
                "name": "Contas Ativas",
                "value": f"{active}/{TOTAL_ACCOUNTS} ({percent:.1f}%)",
                "inline": False
            },
            {
                "name": "Queue",
                "value": str(len(server_queue)),
                "inline": True
            },
            {
                "name": "Invalid",
                "value": str(len(invalid_servers)),
                "inline": True
            }
        ],
        "timestamp": datetime.utcnow().isoformat()
    }

    payload = {"embeds": [embed]}

    try:

        if status_message_id:

            parts = STATUS_WEBHOOK.split("/webhooks/")[1].split("/")

            edit_url = f"https://discord.com/api/webhooks/{parts[0]}/{parts[1]}/messages/{status_message_id}"

            r = requests.patch(edit_url, json=payload)

            if r.status_code in [200, 204]:
                return

        r = requests.post(STATUS_WEBHOOK + "?wait=true", json=payload)

        if r.status_code in [200, 204]:

            try:

                data = r.json()

                if "id" in data:

                    save_status_message(data["id"])

            except:

                pass

    except Exception as e:

        print("Status error:", e)


# =========================================================
# STATUS THREAD
# =========================================================

def status_loop():

    print("Status thread started")

    while True:

        try:

            send_status()

        except Exception as e:

            print("Thread error:", e)

        time.sleep(300)


threading.Thread(target=status_loop, daemon=True).start()

# =========================================================
# INVALID SERVERS
# =========================================================

def is_server_invalid(job):

    if job in invalid_servers:

        if datetime.utcnow().timestamp() - invalid_servers[job] < INVALID_SERVER_COOLDOWN:

            return True

        del invalid_servers[job]

        save_invalid()

    return False


def mark_server_invalid(job):

    invalid_servers[job] = datetime.utcnow().timestamp()

    save_invalid()


# =========================================================
# API
# =========================================================

@app.post("/scan-report")
async def scan_report(report: ScanReport):

    try:

        mark_account_active(report.job_id)

        scan_history.append({
            "job": report.job_id,
            "time": datetime.utcnow().isoformat()
        })

        if report.details.brainrots:

            send_brainrot_log(report)

        return {"status": "ok"}

    except Exception as e:

        raise HTTPException(status_code=400, detail=str(e))


@app.post("/add-job")
async def add_job(server: ServerQueue):

    if server.job_id not in server_queue:

        server_queue.append(server.job_id)

        save_queue()

    return {"queue_size": len(server_queue)}


@app.get("/next-server")
async def next_server():

    while server_queue:

        job = server_queue.pop(0)

        save_queue()

        if not is_server_invalid(job):

            return {"job_id": job}

    return {"job_id": None}


@app.post("/mark-invalid")
async def mark_invalid(server: ServerQueue):

    mark_server_invalid(server.job_id)

    return {"status": "ok"}


@app.get("/health")
async def health():

    return {"status": "ok"}


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    import uvicorn

    load_queue()
    load_invalid()
    load_status_message()

    port = int(os.environ.get("PORT", 8080))

    print("Server started")

    uvicorn.run(app, host="0.0.0.0", port=port)
