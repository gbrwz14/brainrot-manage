from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel  
from typing import Optional, Dict, Any, List  
import os  
import requests  
from datetime import datetime  
import json  
import asyncio  
import time  
import threading  
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
# --- WEBHOOK DE STATUS ---  
STATUS_WEBHOOK = "https://discord.com/api/webhooks/1466200965416751218/vmfMbqibVu-NAMKbuz63Eeo1FEPuHKIVJdFaA6zMEQIPyTFSpDfSeXmQ_Dv5XxjqTgzj"  
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
active_accounts: Dict[str, float] = {}  
INVALID_SERVER_COOLDOWN = 300  
ACCOUNT_TIMEOUT = 600  # 10 minutos  
executor = ThreadPoolExecutor(max_workers=10)  
# --- ESTATÍSTICAS GLOBAIS ---  
stats = {  
    "total_scans": 0,  
    "total_brainrots": 0,  
    "brainrots_by_category": {  
        "10-50M": 0,  
        "50-100M": 0,  
        "100M-500M": 0,  
        "500M-1B": 0,  
        "1B+": 0  
    },  
    "last_update": datetime.utcnow()  
}  
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
# --- FUNÇÕES DE ESTATÍSTICAS ---  
def update_stats(report: ScanReport):  
    """Atualiza estatísticas globais"""  
    global stats  
    stats["total_scans"] += 1  
      
    for brainrot in report.details.brainrots:  
        stats["total_brainrots"] += 1  
          
        # Categoriza por valor  
        if brainrot.valueNumeric >= 1_000_000_000:  
            stats["brainrots_by_category"]["1B+"] += 1  
        elif brainrot.valueNumeric >= 500_000_000:  
            stats["brainrots_by_category"]["500M-1B"] += 1  
        elif brainrot.valueNumeric >= 100_000_000:  
            stats["brainrots_by_category"]["100M-500M"] += 1  
        elif brainrot.valueNumeric >= 50_000_000:  
            stats["brainrots_by_category"]["50-100M"] += 1  
        else:  
            stats["brainrots_by_category"]["10-50M"] += 1  
def mark_account_active(job_id: str):  
    """Marca uma conta como ativa"""  
    active_accounts[job_id] = datetime.utcnow().timestamp()  
def get_active_accounts_count():  
    """Retorna número de contas ativas"""  
    current_time = datetime.utcnow().timestamp()  
    active_count = 0  
      
    for job_id, last_seen in list(active_accounts.items()):  
        time_diff = current_time - last_seen  
        if time_diff < ACCOUNT_TIMEOUT:  
            active_count += 1  
        else:  
            del active_accounts[job_id]  
      
    return active_count  
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
          
        executor.submit(send_discord_async, embed, target_webhook)  
          
    except Exception as e:  
        print(f"❌ Erro ao processar Discord: {str(e)}")  
def send_status_to_discord():  
    """Envia status para Discord a cada 5 minutos"""  
    try:  
        active_count = get_active_accounts_count()  
        total_accounts = 25  # Mude para seu número de contas  
        percentage = (active_count / total_accounts) * 100 if total_accounts > 0 else 0  
          
        categories = stats["brainrots_by_category"]  
        total_brainrots = stats["total_brainrots"]  
          
        # Determina cor baseado na saúde  
        if percentage >= 80:  
            color = 3066993  # Verde  
        elif percentage >= 50:  
            color = 16776960  # Amarelo  
        else:  
            color = 16711680  # Vermelho  
          
        embed = {  
            "title": "📊 STATUS DO NOTIFIER",  
            "color": color,  
            "fields": [  
                {  
                    "name": "🤖 CONTAS ATIVAS",  
                    "value": f"**{active_count}/{total_accounts}** ({percentage:.1f}%)",  
                    "inline": False  
                },  
                {  
                    "name": "🛰️ SISTEMA",  
                    "value": f"""  
**Fila:** {len(server_queue)} IDs  
**Inválidos:** {len(invalid_servers)}  
**Scans totais:** {stats['total_scans']}  
                    """,  
                    "inline": False  
                },  
                {  
                    "name": "☠️ BRAINROTS ENCONTRADOS",  
                    "value": f"**Total:** {total_brainrots}",  
                    "inline": False  
                },  
                {  
                    "name": "💰 10-50M",  
                    "value": f"{categories['10-50M']}",  
                    "inline": True  
                },  
                {  
                    "name": "💰 50-100M",  
                    "value": f"{categories['50-100M']}",  
                    "inline": True  
                },  
                {  
                    "name": "💰 100M-500M",  
                    "value": f"{categories['100M-500M']}",  
                    "inline": True  
                },  
                {  
                    "name": "💰 500M-1B",  
                    "value": f"{categories['500M-1B']}",  
                    "inline": True  
                },  
                {  
                    "name": "💰 1B+",  
                    "value": f"{categories['1B+']}",  
                    "inline": True  
                }  
            ],  
            "timestamp": datetime.utcnow().isoformat()  
        }  
          
        payload = {"embeds": [embed]}  
        requests.post(STATUS_WEBHOOK, json=payload, timeout=5)  
        print(f"✅ Status enviado: {active_count}/{total_accounts} contas ativas")  
    except Exception as e:  
        print(f"❌ Erro ao enviar status: {str(e)}")  
def status_sender():  
    """Thread para enviar status a cada 5 minutos"""  
    while True:  
        time.sleep(300)  # 5 minutos  
        send_status_to_discord()  
# Inicia thread de status  
status_thread = threading.Thread(target=status_sender, daemon=True)  
status_thread.start()  
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
    print(f"⚠️ Servidor marcado como inválido: {job_id}")  
# --- ROTAS ---  
@app.post("/scan-report")  
async def receive_scan_report(report: ScanReport):  
    try:  
        # Marca conta como ativa  
        mark_account_active(report.job_id)  
          
        scan_history.append({  
            "timestamp": datetime.utcnow().isoformat(),  
            "job_id": report.job_id,  
            "player_count": report.player_count,  
            "brainrot_count": len(report.details.brainrots)  
        })  
          
        # Atualiza estatísticas  
        update_stats(report)  
          
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
@app.post("/clear-queue")  
async def clear_queue():  
    """Limpa toda a fila de servidores"""  
    global server_queue  
    cleared_count = len(server_queue)  
    server_queue = []  
    save_queue()  
    print(f"🧹 Fila limpa! {cleared_count} servidores removidos")  
    return {  
        "status": "ok",  
        "message": f"Fila limpa! {cleared_count} servidores removidos",  
        "queue_size": 0  
    }  
@app.post("/clear-invalid")  
async def clear_invalid():  
    """Limpa a lista de servidores inválidos"""  
    global invalid_servers  
    cleared_count = len(invalid_servers)  
    invalid_servers = {}  
    save_invalid_servers()  
    print(f"🧹 Inválidos limpos! {cleared_count} removidos")  
    return {  
        "status": "ok",  
        "message": f"Servidores inválidos limpos! {cleared_count} removidos",  
        "invalid_count": 0  
    }  
@app.post("/refresh-queue")  
async def refresh_queue():  
    """Limpa TUDO e prepara para novos IDs (RESET COMPLETO)"""  
    global server_queue, invalid_servers  
    queue_count = len(server_queue)  
    invalid_count = len(invalid_servers)  
      
    server_queue = []  
    invalid_servers = {}  
    save_queue()  
    save_invalid_servers()  
      
    print(f"🔄 Sistema resetado! Fila: {queue_count} | Inválidos: {invalid_count}")  
    return {  
        "status": "ok",  
        "message": "✅ Sistema resetado! Pronto para novos IDs",  
        "cleared_queue": queue_count,  
        "cleared_invalid": invalid_count,  
        "queue_size": 0,  
        "invalid_count": 0  
    }  
@app.get("/queue-health")  
async def queue_health():  
    """Mostra saúde da fila"""  
    if len(server_queue) > 100:  
        health = "✅ EXCELENTE"  
    elif len(server_queue) > 50:  
        health = "✅ BOM"  
    elif len(server_queue) > 10:  
        health = "⚠️ BAIXO"  
    elif len(server_queue) > 0:  
        health = "⚠️ CRÍTICO"  
    else:  
        health = "❌ VAZIO"  
      
    return {  
        "status": "ok",  
        "queue_size": len(server_queue),  
        "invalid_count": len(invalid_servers),  
        "total_processed": len(scan_history),  
        "health": health,  
        "timestamp": datetime.utcnow().isoformat()  
    }  
@app.get("/stats")  
async def get_stats():  
    """Estatísticas completas do sistema"""  
    active_count = get_active_accounts_count()  
      
    return {  
        "status": "ok",  
        "queue_size": len(server_queue),  
        "invalid_servers": len(invalid_servers),  
        "total_scans": stats["total_scans"],  
        "total_brainrots": stats["total_brainrots"],  
        "active_accounts": active_count,  
        "brainrots_by_category": stats["brainrots_by_category"],  
        "uptime": "24/7",  
        "timestamp": datetime.utcnow().isoformat()  
    }  
@app.get("/health")  
async def health_check():  
    return {"status": "ok"}  
@app.get("/")  
async def root():  
    """Informações da API"""  
    return {  
        "name": "Brainrot Scanner API",  
        "version": "4.0",  
        "status": "running",  
        "endpoints": {  
            "POST /scan-report": "Receber relatório de scan",  
            "POST /add-job": "Adicionar servidor à fila",  
            "GET /next-server": "Obter próximo servidor",  
            "GET /servers": "Ver todos os servidores",  
            "GET /queue-status": "Status da fila",  
            "GET /queue-health": "Saúde da fila",  
            "GET /invalid-servers": "Servidores inválidos",  
            "POST /clear-queue": "Limpar fila",  
            "POST /clear-invalid": "Limpar inválidos",  
            "POST /refresh-queue": "Reset completo",  
            "GET /stats": "Estatísticas completas",  
            "GET /health": "Health check"  
        }  
    }  
if __name__ == "__main__":  
    import uvicorn  
    port = int(os.environ.get("PORT", 8080))  
    print(f"🚀 Iniciando servidor na porta {port}")  
    uvicorn.run(app, host="0.0.0.0", port=port)  
