from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import requests
from datetime import datetime

app = FastAPI()

# --- CONFIGURAÇÃO DAS WEBHOOKS POR CATEGORIA ---
WEBHOOKS = {
    "1-10M": "https://discord.com/api/webhooks/1464779393334509822/LeeBhEdD0XfXF9ppprAHv30hqs4uKHlm44sCcnJYK7E5HDwZWA1YeptaFmzP2x5jrBjZ",
    "10-50M": "https://discord.com/api/webhooks/1465203465524609024/dqNqGxjE5rnZS_NWIlOvCUK8dkoaTUB9S8Sh-bmyCpAngVE3L93jyk3rrUZlqF05FXTF",
    "50-100M": "https://discord.com/api/webhooks/1465203508574945330/ycF_1onTdZMARGQxYXXnyCJrK_YscwYYkILNgqNdjS5x80L1Yz1Q1G8QtYBbmvPEiWuj",
    "100M-500M": "https://discord.com/api/webhooks/1465203562568089804/vapbWnEhAgtmRovUfYgZpCqvTuT6dIbHyFx01DdaluQDHj1XmNiU-bQCPK2oDD3UvTBj",
    "500M-1B": "https://discord.com/api/webhooks/1465204919337484400/JgQ7blnGnBK1BLRC5jzxgB6Ud2sXsk8pQMwUFqZ1JRDMFAOkKAnElw6xJlQC0sspirKC"
}

# Modelos (Mantidos conforme o seu original)
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

def get_target_webhook(value: float):
    """Define a webhook correta com base no valor numérico"""
    if value >= 500_000_000: return WEBHOOKS["500M-1B"]
    if value >= 100_000_000: return WEBHOOKS["100M-500M"]
    if value >= 50_000_000: return WEBHOOKS["50-100M"]
    if value >= 10_000_000: return WEBHOOKS["10-50M"]
    if value >= 1_000_000: return WEBHOOKS["1-10M"]
    return None

def send_discord_detailed_log(report: ScanReport):
    """Envia o log formatado para a Webhook da categoria correta"""
    try:
        brainrots = report.details.brainrots
        if not brainrots:
            return

        # Pega o item de maior valor para decidir a categoria
        top_value = max([br.valueNumeric for br in brainrots])
        target_webhook = get_target_webhook(top_value)
        
        if not target_webhook:
            print(f"⚠️ Valor {top_value} abaixo do limite de 1M. Ignorando Discord.")
            return

        # Formata lista de brainrots (Mantendo seu designer)
        brainrot_list = ""
        for br in brainrots:
            brainrot_list += f"{br.count}x {br.name} {br.valuePerSecond}\n"

        # Cria o embed (IDÊNTICO AO SEU DESIGNER)
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
        
        payload = {"embeds": [embed]}
        requests.post(target_webhook, json=payload, timeout=10)
        
    except Exception as e:
        print(f"❌ Erro ao enviar log para Discord: {str(e)}")

@app.post("/scan-report")
async def receive_scan_report(report: ScanReport):
    try:
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
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/add-job")
async def add_job(server: ServerQueue):
    if server.job_id not in server_queue:
        server_queue.append(server.job_id)
    return {"status": "ok", "queue_size": len(server_queue)}

@app.get("/next-server")
async def get_next_server(scanner_id: str = ""):
    if server_queue:
        return {"job_id": server_queue.pop(0)}
    return {"job_id": None}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
