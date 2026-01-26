from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel  
from typing import Optional, Dict, Any, List  
import os  
import requests  
from datetime import datetime  
app = FastAPI()  
# Configuração  
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")  
API_PASSWORD = os.environ.get("PASSWORD", "default_password")  
# Modelos  
class Brainrot(BaseModel):  
    name: str  
    valuePerSecond: str  
    valueNumeric: float  
    owner: str  
    rarity: str  
    mutation: str  
class ScanDetails(BaseModel):  
    top_owner: str  
    top_owner_brainrots: List[Brainrot]  
    all_brainrots: List[Brainrot]  
class ScanReport(BaseModel):  
    job_id: str  
    scanner_id: str  
    player_count: int  
    details: ScanDetails  
class ServerQueue(BaseModel):  
    job_id: str  
# Armazenamento em memória  
server_queue: List[str] = []  
scan_history: List[Dict] = []  
def send_discord_detailed_log(report: ScanReport):  
    """Envia o log formatado para o Discord"""  
    if not DISCORD_WEBHOOK_URL:  
        return  
      
    try:  
        top_owner = report.details.top_owner  
        top_owner_brainrots = report.details.top_owner_brainrots  
          
        # Formata lista de brainrots  
        brainrot_list = ""  
        if top_owner_brainrots:  
            for i, br in enumerate(top_owner_brainrots, 1):  
                brainrot_list += f"{i}x {br.name} ({br.valuePerSecond})\n"  
        else:  
            brainrot_list = "Nenhum brainrot encontrado"  
          
        # Cria o embed  
        embed = {  
            "title": "☠️ Scan de Servidor Completo",  
            "color": 16711680,  # Vermelho  
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
                },  
                {  
                    "name": "🧠 Base com Maior Valor",  
                    "value": f"```\n{top_owner}```",  
                    "inline": False  
                },  
                {  
                    "name": "🤖 Scanner",  
                    "value": f"```\n{report.scanner_id}```",  
                    "inline": False  
                }  
            ],  
            "timestamp": datetime.utcnow().isoformat()  
        }  
          
        payload = {  
            "embeds": [embed]  
        }  
          
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)  
        if response.status_code == 204:  
            print(f"✅ Log enviado para Discord: {top_owner}")  
        else:  
            print(f"⚠️ Erro ao enviar para Discord: {response.status_code}")  
    except Exception as e:  
        print(f"❌ Erro ao enviar log para Discord: {e}")  
@app.post("/scan-report")  
async def receive_scan_report(report: ScanReport):  
    """Recebe relatório de scan do worker"""  
    try:  
        print(f"\n📊 Novo Scan Recebido:")  
        print(f"   Job ID: {report.job_id}")  
        print(f"   Scanner: {report.scanner_id}")  
        print(f"   Players: {report.player_count}")  
        print(f"   Top Owner: {report.details.top_owner}")  
        print(f"   Brainrots: {len(report.details.top_owner_brainrots)}")  
          
        # Armazena no histórico  
        scan_history.append({  
            "timestamp": datetime.utcnow().isoformat(),  
            "job_id": report.job_id,  
            "scanner_id": report.scanner_id,  
            "player_count": report.player_count,  
            "top_owner": report.details.top_owner,  
            "brainrot_count": len(report.details.top_owner_brainrots)  
        })  
          
        # Envia para Discord  
        send_discord_detailed_log(report)  
          
        return {"status": "ok", "message": "Scan recebido com sucesso"}  
    except Exception as e:  
        print(f"❌ Erro ao processar scan: {e}")  
        raise HTTPException(status_code=400, detail=str(e))  
@app.post("/add-server")  
async def add_server(server: ServerQueue):  
    """Adiciona servidor à fila"""  
    if not server.job_id:  
        raise HTTPException(status_code=400, detail="job_id é obrigatório")  
      
    # Evita duplicatas  
    if server.job_id not in server_queue:  
        server_queue.append(server.job_id)  
        print(f"✅ Servidor adicionado à fila: {server.job_id} (Total: {len(server_queue)})")  
    else:  
        print(f"⚠️ Servidor já existe na fila: {server.job_id}")  
      
    return {"status": "ok", "queue_size": len(server_queue)}  
@app.post("/add-job")  
async def add_job(server: ServerQueue):  
    """Alias para /add-server (compatibilidade)"""  
    return await add_server(server)  
@app.get("/next-server")  
async def get_next_server(scanner_id: str = ""):  
    """Retorna o próximo servidor da fila"""  
    if server_queue:  
        next_job = server_queue.pop(0)  
        print(f"🚀 Próximo servidor para {scanner_id}: {next_job} (Restantes: {len(server_queue)})")  
        return {"job_id": next_job}  
    else:  
        print(f"📭 Fila vazia para {scanner_id}")  
        return {"job_id": None}  
@app.get("/servers")  
async def get_servers():  
    """Retorna lista de servidores na fila"""  
    return {  
        "queue_size": len(server_queue),  
        "servers": server_queue,  
        "history_count": len(scan_history)  
    }  
@app.get("/queue-status")  
async def queue_status():  
    """Retorna status da fila"""  
    return {  
        "queue_size": len(server_queue),  
        "servers": server_queue,  
        "history_count": len(scan_history)  
    }  
@app.get("/history")  
async def get_history(limit: int = 10):  
    """Retorna histórico de scans"""  
    return {"scans": scan_history[-limit:]}  
@app.get("/health")  
async def health_check():  
    """Health check"""  
    return {"status": "ok", "webhook_configured": bool(DISCORD_WEBHOOK_URL)}  
if __name__ == "__main__":  
    import uvicorn  
    port = int(os.environ.get("PORT", 8080))  
    uvicorn.run(app, host="0.0.0.0", port=port)  
