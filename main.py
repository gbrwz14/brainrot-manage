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
class ScanDetails(BaseModel):  
    players: str  
    value: Any  
    brainrot: Any  
class ScanReport(BaseModel):  
    job_id: str  
    has_rare: bool  
    scanner_id: str  
    details: ScanDetails  
class ServerQueue(BaseModel):  
    job_id: str  
# Armazenamento em memória  
server_queue: List[str] = []  
scan_history: List[Dict] = []  
def send_discord_detailed_log(report: ScanReport):  
    """Envia o log formatado para o Discord com os novos detalhes solicitados"""  
    if not DISCORD_WEBHOOK_URL:  
        return  
      
    try:  
        # Extrai os dados do brainrot  
        brainrot_data = report.details.brainrot if isinstance(report.details.brainrot, dict) else {}  
          
        if brainrot_data:  
            nome = brainrot_data.get("nome", "Unknown")  
            valor_por_segundo = brainrot_data.get("valor_por_segundo", "N/A")  
            dono = brainrot_data.get("dono", "Unknown")  
            raridade = brainrot_data.get("raridade", "Unknown")  
            mutacao = brainrot_data.get("mutacao", "None")  
        else:  
            nome = "Nenhum"  
            valor_por_segundo = "N/A"  
            dono = "N/A"  
            raridade = "N/A"  
            mutacao = "N/A"  
          
        # Formata a mensagem para o Discord  
        embed = {  
            "title": "🛰️ Scan de Servidor Completo",  
            "color": 3447003,  
            "fields": [  
                {"name": "Job ID", "value": report.job_id, "inline": False},  
                {"name": "👤 Nome do Brainrot", "value": nome, "inline": True},  
                {"name": "💰 Valor por Segundo", "value": valor_por_segundo, "inline": True},  
                {"name": "🧠 Dono", "value": dono, "inline": True},  
                {"name": "✨ Raridade", "value": raridade, "inline": True},  
                {"name": "🔄 Mutação", "value": mutacao, "inline": True},  
                {"name": "🤖 Scanner", "value": report.scanner_id, "inline": True}  
            ],  
            "timestamp": datetime.utcnow().isoformat()  
        }  
          
        payload = {  
            "embeds": [embed]  
        }  
          
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)  
        if response.status_code == 204:  
            print(f"✅ Log enviado para Discord: {nome}")  
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
        print(f"   Has Rare: {report.has_rare}")  
          
        # Armazena no histórico  
        scan_history.append({  
            "timestamp": datetime.utcnow().isoformat(),  
            "job_id": report.job_id,  
            "scanner_id": report.scanner_id,  
            "has_rare": report.has_rare,  
            "details": report.details.dict()  
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
