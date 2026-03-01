from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel  
from typing import Optional, Dict, Any, List  
import os  
import requests  
from datetime import datetime  
import json  
import time  
import threading  
from concurrent.futures import ThreadPoolExecutor  
app = FastAPI()  
QUEUE_FILE = "server_queue.json"  
INVALID_SERVERS_FILE = "invalid_servers.json"  
STATUS_MESSAGE_FILE = "status_message.json"  
WEBHOOKS = {  
    "10-50M": "https://discord.com/api/webhooks/1465203465524609024/dqNqGxjE5rnZS_NWIlOvCUK8dkoaTUB9S8Sh-bmyCpAngVE3L93jyk3rrUZlqF05FXTF",  
    "50-100M": "https://discord.com/api/webhooks/1465203508574945330/ycF_1onTdZMARGQxYXXnyCJrK_YscwYYkILNgqNdjS5x80L1Yz1Q1G8QtYBbmvPEiWuj",  
    "100M-500M": "https://discord.com/api/webhooks/1465203562568089804/vapbWnEhAgtmRovUfYgZpCqvTuT6dIbHyFx01DdaluQDHj1XmNiU-bQCPK2oDD3UvTBj",  
    "500M-1B": "https://discord.com/api/webhooks/1465204919337484400/JgQ7blnGnBK1BLRC5jzxgB6Ud2sXsk8pQMwUFqZ1JRDMFAOkKAnElw6xJlQC0sspirKC",  
    "1B+": "https://discord.com/api/webhooks/1465478594372567278/La9Semqa4eWKucTZJew8GpuNLATC3OJL0tGT5tZLkRaRbyQEZK6Fn-L5hvP9ZlKObjG1"  
}  
STATUS_WEBHOOK = "https://discord.com/api/webhooks/1466200965416751218/vmfMbqibVu-NAMKbuz63Eeo1FEPuHKIVJdFaA6zMEQIPyTFSpDfSeXmQ_Dv5XxjqTgzj"  
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
server_queue: List[str] = []  
scan_history: List[Dict] = []  
invalid_servers: Dict[str, float] = {}  
active_accounts: Dict[str, float] = {}  
status_message_id: Optional[str] = None  
INVALID_SERVER_COOLDOWN = 300  
ACCOUNT_TIMEOUT = 600  
executor = ThreadPoolExecutor(max_workers=10)  
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
def load_status_message_id():  
    global status_message_id  
    try:  
        if os.path.exists(STATUS_MESSAGE_FILE):  
            with open(STATUS_MESSAGE_FILE, 'r') as f:  
                data = json.load(f)  
                status_message_id = data.get("message_id")  
                if status_message_id:  
                    print(f"✅ Message ID carregado: {status_message_id}")  
                return status_message_id  
    except Exception as e:  
        print(f"⚠️ Erro: {str(e)}")  
    return None  
def save_status_message_id(message_id):  
    global status_message_id  
    status_message_id = message_id  
    try:  
        with open(STATUS_MESSAGE_FILE, 'w') as f:  
            json.dump({"message_id": message_id}, f)  
        print(f"✅ Message ID salvo: {message_id}")  
    except Exception as e:  
        print(f"❌ Erro: {str(e)}")  
def load_queue():  
    try:  
        if os.path.exists(QUEUE_FILE):  
            with open(QUEUE_FILE, 'r') as f:  
                return json.load(f)  
    except:  
        pass  
    return []  
def save_queue():  
    try:  
        with open(QUEUE_FILE, 'w') as f:  
            json.dump(server_queue, f, indent=2)  
    except:  
        pass  
def load_invalid_servers():  
    try:  
        if os.path.exists(INVALID_SERVERS_FILE):  
            with open(INVALID_SERVERS_FILE, 'r') as f:  
                return json.load(f)  
    except:  
        pass  
    return {}  
def save_invalid_servers():  
    try:  
        with open(INVALID_SERVERS_FILE, 'w') as f:  
            json.dump(invalid_servers, f, indent=2)  
    except:  
        pass  
server_queue = load_queue()  
invalid_servers = load_invalid_servers()  
load_status_message_id()  
def update_stats(report: ScanReport):  
    global stats  
    stats["total_scans"] += 1  
      
    for brainrot in report.details.brainrots:  
        stats["total_brainrots"] += 1  
          
        if brainrot.value_numeric >= 1_000_000_000:  
            stats["brainrots_by_category"]["1B+"] += 1  
        elif brainrot.value_numeric >= 500_000_000:  
            stats["brainrots_by_category"]["500M-1B"] += 1  
        elif brainrot.value_numeric >= 100_000_000:  
            stats["brainrots_by_category"]["100M-500M"] += 1  
        elif brainrot.value_numeric >= 50_000_000:  
            stats["brainrots_by_category"]["50-100M"] += 1  
        else:  
            stats["brainrots_by_category"]["10-50M"] += 1  
def mark_account_active(job_id: str):  
    active_accounts[job_id] = datetime.utcnow().timestamp()  
def get_active_accounts_count():  
    current_time = datetime.utcnow().timestamp()  
    active_count = 0  
      
    for job_id, last_seen in list(active_accounts.items()):  
        if current_time - last_seen < ACCOUNT_TIMEOUT:  
            active_count += 1  
        else:  
            del active_accounts[job_id]  
      
    return active_count  
def get_target_webhook(value: float):  
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
def send_discord_async(embed, target_webhook):  
    try:  
        payload = {"embeds": [embed]}  
        response = requests.post(target_webhook, json=payload, timeout=5)  
        if response.status_code in [200, 204]:  
            print(f"✅ Brainrot enviado")  
    except Exception as e:  
        print(f"❌ Erro: {str(e)}")  
def send_discord_detailed_log(report: ScanReport):  
    try:  
        brainrots = report.details.brainrots  
        if not brainrots:  
            return  
          
        top_value = max([br.value_numeric for br in brainrots])  
        target_webhook = get_target_webhook(top_value)  
          
        if not target_webhook:  
            return  
          
        brainrot_list = ""  
        for br in brainrots:  
            brainrot_list += f"{br.count}x {br.name} {br.value_per_second}\n"  
          
        embed = {  
            "title": "☠️ Brainrots Detectados",  
            "color": 16711680,  
            "fields": [  
                {"name": "☠️ Brainrots", "value": f"```\n{brainrot_list}```", "inline": False},  
                {"name": "🆔 Server ID", "value": f"```\n{report.job_id}```", "inline": False},  
                {"name": "👥 Players", "value": f"```\n{report.player_count}```", "inline": False}  
            ],  
            "timestamp": datetime.utcnow().isoformat()  
        }  
          
        executor.submit(send_discord_async, embed, target_webhook)  
    except Exception as e:  
        print(f"❌ Erro: {str(e)}")  
def send_status_to_discord():  
    global status_message_id  
      
    try:  
        active_count = get_active_accounts_count()  
        total_accounts = 25  
        percentage = (active_count / total_accounts) * 100 if total_accounts > 0 else 0  
          
        categories = stats["brainrots_by_category"]  
        total_brainrots = stats["total_brainrots"]  
          
        if percentage >= 80:  
            color = 3066993  
        elif percentage >= 50:  
            color = 16776960  
        else:  
            color = 16711680  
          
        embed = {  
            "title": "📊 STATUS DO NOTIFIER",  
            "color": color,  
            "fields": [  
                {"name": "🤖 CONTAS ATIVAS", "value": f"**{active_count}/{total_accounts}** ({percentage:.1f}%)", "inline": False},  
                {"name": "🛰️ SISTEMA", "value": f"**Fila:** {len(server_queue)} IDs\n**Inválidos:** {len(invalid_servers)}\n**Scans:** {stats['total_scans']}", "inline": False},  
                {"name": "☠️ BRAINROTS", "value": f"**Total:** {total_brainrots}", "inline": False},  
                {"name": "💰 10-50M", "value": f"{categories['10-50M']}", "inline": True},  
                {"name": "💰 50-100M", "value": f"{categories['50-100M']}", "inline": True},  
                {"name": "💰 100M-500M", "value": f"{categories['100M-500M']}", "inline": True},  
                {"name": "💰 500M-1B", "value": f"{categories['500M-1B']}", "inline": True},  
                {"name": "💰 1B+", "value": f"{categories['1B+']}", "inline": True}  
            ],  
            "timestamp": datetime.utcnow().isoformat()  
        }  
          
        payload = {"embeds": [embed]}  
          
        if status_message_id:  
            try:  
                webhook_parts = STATUS_WEBHOOK.split("/webhooks/")[1].split("/")  
                webhook_id = webhook_parts[0]  
                webhook_token = webhook_parts[1]  
                  
                edit_url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}/messages/{status_message_id}"  
                  
                print(f"🔄 Editando mensagem: {status_message_id}")  
                response = requests.patch(edit_url, json=payload, timeout=5)  
                  
                if response.status_code in [200, 204]:  
                    print(f"✅ Mensagem editada!")  
                    return  
                else:  
                    print(f"⚠️ Falha ao editar")  
                    status_message_id = None  
            except Exception as e:  
                print(f"⚠️ Erro: {str(e)}")  
                status_message_id = None  
          
        print(f"📤 Enviando nova mensagem...")  
        response = requests.post(STATUS_WEBHOOK, json=payload, timeout=5)  
          
        if response.status_code in [200, 204]:  
            data = response.json()  
            new_message_id = data.get("id")  
            if new_message_id:  
                save_status_message_id(new_message_id)  
                print(f"✅ Nova mensagem: {new_message_id}")  
      
    except Exception as e:  
        print(f"❌ Erro: {str(e)}")  
def status_sender():  
    print("🚀 Thread de status iniciada")  
    while True:  
        try:  
            time.sleep(300)  
            send_status_to_discord()  
        except Exception as e:  
            print(f"❌ Erro: {str(e)}")  
            time.sleep(60)  
print("🔄 Iniciando thread...")  
status_thread = threading.Thread(target=status_sender, daemon=True)  
status_thread.start()  
print("✅ Thread iniciada")  
def is_server_invalid(job_id: str) -> bool:  
    if job_id in invalid_servers:  
        if datetime.utcnow().timestamp() - invalid_servers[job_id] < INVALID_SERVER_COOLDOWN:  
            return True  
        else:  
            del invalid_servers[job_id]  
            save_invalid_servers()  
    return False  
def mark_server_invalid(job_id: str):  
    invalid_servers[job_id] = datetime.utcnow().timestamp()  
    save_invalid_servers()  
@app.post("/scan-report")  
async def receive_scan_report(report: ScanReport):  
    try:  
        mark_account_active(report.job_id)  
        scan_history.append({  
            "timestamp": datetime.utcnow().isoformat(),  
            "job_id": report.job_id,  
            "player_count": report.player_count,  
            "brainrot_count": len(report.details.brainrots)  
        })  
          
        update_stats(report)  
          
        print(f"📊 Scan: {report.job_id} - {len(report.details.brainrots)} brainrots")  
          
        if report.details.brainrots:  
            print(f"🎯 Enviando para Discord...")  
            send_discord_detailed_log(report)  
              
        return {"status": "ok", "message": "Scan recebido com sucesso"}  
    except Exception as e:  
        print(f"❌ Erro: {str(e)}")  
        raise HTTPException(status_code=400, detail=str(e))  
@app.post("/add-job")  
async def add_job(server: ServerQueue):  
    if server.job_id not in server_queue:  
        server_queue.append(server.job_id)  
        save_queue()  
    return {"status": "ok", "queue_size": len(server_queue)}  
@app.get("/next-server")  
async def get_next_server():  
    while server_queue:  
        job_id = server_queue[0]  
          
        if is_server_invalid(job_id):  
            server_queue.pop(0)  
            save_queue()  
            continue  
          
        server_queue.pop(0)  
        save_queue()  
        return {"job_id": job_id}  
      
    return {"job_id": None}  
@app.post("/mark-invalid")  
async def mark_invalid(server: ServerQueue):  
    mark_server_invalid(server.job_id)  
    return {"status": "ok", "message": "Servidor marcado como inválido"}  
@app.get("/servers")  
async def get_servers():  
    return {  
        "status": "ok",  
        "queue_size": len(server_queue),  
        "servers": server_queue,  
        "timestamp": datetime.utcnow().isoformat()  
    }  
@app.get("/invalid-servers")  
async def get_invalid_servers():  
    expired = []  
    for job_id in list(invalid_servers.keys()):  
        if datetime.utcnow().timestamp() - invalid_servers[job_id] >= INVALID_SERVER_COOLDOWN:  
            expired.append(job_id)  
            del invalid_servers[job_id]  
      
    if expired:  
        save_invalid_servers()  
      
    return {  
        "status": "ok",  
        "total_invalid": len(invalid_
