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
def send_discord_detailed_log(report: ScanReport):  
    """Envia o log formatado para o Discord"""  
    if not DISCORD_WEBHOOK_URL:  
        return  
      
    try:  
        brainrots = report.details.brainrots  
          
        # Formata lista de brainrots  
        brainrot_list = ""  
        if brainrots:  
            for br in brainrots:  
                brainrot_list += f"{br.count}x {br.name} {br.valuePerSecond}\n"  
        else:  
            brainrot_list = "Nenhum brainrot com 10M+ encontrado"  
          
        # Cria o embed  
        embed = {  
            "title": "☠️ Brainrots Detectados",  
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
                }  
            ],  
            "timestamp": datetime.utcnow().isoformat()  
        }  
          
        payload = {  
            "embeds": [embed]  
        }  
          
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)  
        if response.status_code == 204:  
            print(f"✅ Log enviado para Discord")  
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
        print(f"   Players: {report.player_count}")  
        print(f"   Brainrots (10M+): {len(report.details.brainrots)}")  
          
        # Armazena no histórico  
        scan_history.append({  
            "timestamp": datetime.utcnow().isoformat(),  
            "job_id": report.job_id,  
            "player_count": report.player_count,  
            "brainrot_count": len(report.details.brainrots)  
        })  
          
        # Envia para Discord apenas se houver brainrots  
        if report.details.brainrots:  
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
      
    return {"status": "ok", "queue_size": len(server_queue)}  
@app.post("/add-job")  
async def add_job(server: ServerQueue):  
    """Alias para /add-server"""  
    return await add_server(server)  
@app.get("/next-server")  
async def get_next_server(scanner_id: str = ""):  
    """Retorna o próximo servidor da fila"""  
    if server_queue:  
        next_job = server_queue.pop(0)  
        print(f"🚀 Próximo servidor: {next_job} (Restantes: {len(server_queue)})")  
        return {"job_id": next_job}  
    else:  
        print(f"📭 Fila vazia")  
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
