from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel  
from typing import Optional, Dict, Any, List  
import os  
import requests  
from datetime import datetime  
import json  
import asyncio  
from concurrent.futures import ThreadPoolExecutor  
app = FastAPI()  
# --- ARQUIVO DE PERSISTÊNCIA ---  
QUEUE_FILE = "server_queue.json"  
INVALID_SERVERS_FILE = "invalid_servers.json"  
# --- CONFIGURAÇÃO DAS WEBHOOKS POR CATEGORIA ---  
WEBHOOKS = {  
    "10-50M": "https://discord.com/api/webhooks/1465203465524609024/dqNqGxjE5rnZS_NWIlOvCUK8dkoaTUB9S8Sh-bmyCpAngVE3L93jyk3rrUZlqF05FXTF",  
    "50-100M": "https://discord.com/api/webhooks/1465203508574945330/ycF_1onTdZMARGQxYXXnyCJrK_YscwYYkILNgqNdjS5x80L1Yz1Q1G8QtYBbmvPEiWuj",  
    "100M-500M": "https://discord.com/api/webhooks/1465203562568089804/vapbWnEhAgtmRovUfYgZpCqvTuT6dIbHyFx01DdaluQDHj1XmNiU-bQCPK2oDD3UvTBj",  
    "500M-1B": "https://discord.com/api/webhooks/1465204919337484400/JgQ7blnGnBK1BLRC5jzxgB6Ud2sXsk8pQMwUFqZ1JRDMFAOkKAnElw6xJlQC0sspirKC",  
    "1B+": "https://discord.com/api/webhooks/1465478594372567278/La9Semqa4eWKucTZJew8GpuNLATC3OJL0tGT5tZLkRaRbyQEZK6Fn-L5hvP9ZlKObjG1"  
}  
# Modelos  
class Brainrot(BaseModel):  
    name: str  
    valuePerSecond: str  
    valueNumeric: float  
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
# Armazenamento em memória  
server_queue: List[str] = []  
scan_history: List[Dict] = []  
invalid_servers: Dict[str, float] = {}  
INVALID_SERVER_COOLDOWN = 300  
executor = ThreadPoolExecutor(max_workers=10)  # ← PROCESSAMENTO PARALELO  
# --- FUNÇÕES DE PERSISTÊNCIA ---  
def load_queue():  
    try:  
        if os.path.exists(QUEUE_FILE):  
            with open(QUEUE_FILE, 'r') as f:  
                data = json.load(f)  
                print(f"✅ Fila carregada: {len(data)} servidores")  
                return data  
    except Exception as e:  
        print(f"⚠️ Erro ao carregar fila: {str(e)}")  
    return []  
def save_queue():  
    try:  
        with open(QUEUE_FILE, 'w') as f:  
            json.dump(server_queue, f, indent=2)  
    except Exception as e:  
        print(f"❌ Erro ao salvar fila: {str(e)}")  
def load_invalid_servers():  
    try:  
        if os.path.exists(INVALID_SERVERS_FILE):  
            with open(INVALID_SERVERS_FILE, 'r') as f:  
                return json.load(f)  
    except Exception as e:  
        print(f"⚠️ Erro ao carregar servidores inválidos: {str(e)}")  
    return {}  
def save_invalid_servers():  
    try:  
        with open(INVALID_SERVERS_FILE, 'w') as f:  
            json.dump(invalid_servers, f, indent=2)  
    except Exception as e:  
        print(f"❌ Erro ao salvar servidores inválidos: {str(e)}")  
server_queue = load_queue()  
invalid_servers = load_invalid_servers()  
def get_target_webhook(value: float):  
    if value >= 1_000_000_000: return WEBHOOKS["1B+"]  
    if value >= 500_000_000: return WEBHOOKS["500M-1B"]  
    if value >= 100_000_000: return WEBHOOKS["100M-500M"]  
    if value >= 50_000_000: return WEBHOOKS["50-100M"]  
    if value >= 10_000_000: return WEBHOOKS["10-50M"]  
    return None  
def send_discord_async(embed, target_webhook):  
    """Envia para Discord de forma assíncrona"""  
    try:  
        payload = {"embeds": [embed]}  
        requests.post(target_webhook, json=payload, timeout=5)  
    except Exception as e:  
        print(f"❌ Erro ao enviar Discord: {str(e)}")  
def send_discord_detailed_log(report: ScanReport):  
    try:  
        brainrots = report.details.brainrots  
        if not brainrots:  
            return  
        top_value = max([br.valueNumeric for br in brainrots])  
        target_webhook = get_target_webhook(top_value)  
          
        if not target_webhook:  
            return  
        brainrot_list = ""  
        for br in brainrots:  
            brainrot_list += f"{br.count}x {br.name} {br.valuePerSecond}\n"  
        embed = {  
            "title": "☠️ Brainrots Detectados",  
            "color": 16711680,  
            "fields": [  
                {  
                    "name": "☠️ Brainrots",  
                    "value": f"```\n{brainrot_list}```",  
                    "inline": False  
                },  
                {  
                    "name": "🆔 Server ID",  
                    "value": f"```\n{report.job_id}```",  
                    "inline": False  
                },  
                {  
                    "name": "👥 Players no Servidor",  
                    "value": f"```\n{report.player_count}```",  
                    "inline": False  
                }  
            ],  
            "timestamp": datetime.utcnow().isoformat()  
        }  
          
        # Envia de forma assíncrona  
        executor.submit(send_discord_async, embed, target_webhook)  
          
    except Exception as e:  
        print(f"❌ Erro ao processar Discord: {str(e)}")  
def is_server_invalid(job_id: str) -> bool:  
    if job_id in invalid_servers:  
        time_diff = datetime.utcnow().timestamp() - invalid_servers[job_id]  
        if time_diff < INVALID_SERVER_COOLDOWN:  
            return True  
        else:  
            del invalid_servers[job_id]  
            save_invalid_servers()  
    return False  
def mark_server_invalid(job_id: str):  
    invalid_servers[job_id] = datetime.utcnow().timestamp()  
    save_invalid_servers()  
# --- ROTAS ---  
@app.post("/scan-report")  
async def receive_scan_report(report: ScanReport):  
    try:  
        scan_history.append({  
            "timestamp": datetime.utcnow().isoformat(),  
            "job_id": report.job_id,  
            "player_count": report.player_count,  
            "brainrot_count": len(report.details.brainrots)  
        })  
          
        if report.details.brainrots:  
            send_discord_detailed_log(report)  
            
        return {"status": "ok", "message": "Scan recebido com sucesso"}  
    except Exception as e:  
        raise HTTPException(status_code=400, detail=str(e))  
@app.post("/add-job")  
async def add_job(server: ServerQueue):  
    if server.job_id not in server_queue:  
        server_queue.append(server.job_id)  
        save_queue()  
    return {"status": "ok", "queue_size": len(server_queue)}  
@app.get("/next-server")  
async def get_next_server(scanner_id: str = ""):  
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
    return {"status": "ok", "message": f"Servidor marcado como inválido"}  
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
        time_diff = datetime.utcnow().timestamp() - invalid_servers[job_id]  
        if time_diff >= INVALID_SERVER_COOLDOWN:  
            expired.append(job_id)  
            del invalid_servers[job_id]  
      
    if expired:  
        save_invalid_servers()  
      
    return {  
        "status": "ok",  
        "total_invalid": len(invalid_servers),  
        "invalid_servers": invalid_servers,  
        "timestamp": datetime.utcnow().isoformat()  
    }  
@app.get("/queue-status")  
async def queue_status():  
    return {  
        "status": "ok",  
        "queue_size": len(server_queue),  
        "servers_in_queue": server_queue,  
        "invalid_servers_count": len(invalid_servers),  
        "scan_history_count": len(scan_history),  
        "last_scans": scan_history[-10:] if scan_history else [],  
        "timestamp": datetime.utcnow().isoformat()  
    }  
@app.get("/health")  
async def health_check():  
    return {"status": "ok"}  
if __name__ == "__main__":  
    import uvicorn  
    port = int(os.environ.get("PORT", 8080))  
    uvicorn.run(app, host="0.0.0.0", port=port)  
