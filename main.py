from fastapi import FastAPI, HTTPException, Depends, status  
from pydantic import BaseModel  
from typing import Optional, Any, Dict  
from datetime import datetime  
import json  
import os  
import requests  # Necessário para enviar a Webhook
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text  
from sqlalchemy.orm import sessionmaker, declarative_base, Session  

# Configurações de Banco de Dados
DB_FILE = os.environ.get("DB_FILE", "servers.db")  
DATABASE_URL = f"sqlite:///{DB_FILE}"  
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})  
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)  
Base = declarative_base()  

# Definição da URL da Webhook - COLOQUE A SUA AQUI
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")    

class Server(Base):  
    __tablename__ = "servers"  
    id = Column(Integer, primary_key=True, index=True)  
    job_id = Column(String, unique=True, index=True, nullable=False)  
    has_rare = Column(Boolean, default=False, index=True)  
    data = Column(Text, default="{}")  
    assigned = Column(Boolean, default=False, index=True)  
    assigned_to = Column(String, nullable=True)  
    assigned_at = Column(DateTime, nullable=True)  
    scanned = Column(Boolean, default=False, index=True)  
    first_seen = Column(DateTime, default=datetime.utcnow)  
    last_seen = Column(DateTime, default=datetime.utcnow)  

class ScanLog(Base):  
    __tablename__ = "scanlogs"  
    id = Column(Integer, primary_key=True, index=True)  
    job_id = Column(String, index=True)  
    scanner_id = Column(String, nullable=True)  
    payload = Column(Text, default="{}")  
    timestamp = Column(DateTime, default=datetime.utcnow)  

Base.metadata.create_all(bind=engine)  

class AddJobRequest(BaseModel):  
    job_id: str  

class ScanReport(BaseModel):  
    job_id: str  
    has_rare: bool  
    scanner_id: Optional[str] = None  
    details: Optional[Dict[str, Any]] = None  

class NextServerResponse(BaseModel):  
    job_id: str  
    data: Optional[Dict[str, Any]] = None  
    assigned_to: Optional[str] = None  
    assigned_at: Optional[datetime] = None  

class MarkScannedRequest(BaseModel):  
    job_id: str  
    scanner_id: Optional[str] = None  
    scanned: bool = True  

app = FastAPI()  

def get_db():  
    db = SessionLocal()  
    try:  
        yield db  
    finally:  
        db.close()  

def send_discord_detailed_log(report: ScanReport):
    """Envia o log formatado para o Discord com os novos detalhes solicitados"""
    if not DISCORD_WEBHOOK_URL or "SUA_WEBHOOK" in DISCORD_WEBHOOK_URL:
        return

    details = report.details or {}
    
    # Extração dos dados enviados pelo Roblox
    players = details.get("players", "Nenhum")
    value = details.get("value", 0)
    brainrot = details.get("brainrot", "N/A")
    
    embed = {
        "title": "🛰️ Scan de Servidor Completo",
        "description": f"**Job ID:** `{report.job_id}`",
        "color": 0x00ff00 if report.has_rare else 0x3498db,
        "fields": [
            {"name": "👤 Jogadores/Donos", "value": str(players), "inline": False},
            {"name": "🧠 Brainrot", "value": str(brainrot), "inline": True},
            {"name": "💰 Valor Total", "value": f"R$ {value}", "inline": True},
            {"name": "🤖 Scanner", "value": report.scanner_id or "Desconhecido", "inline": True}
        ],
        "footer": {"text": "Sistema de Monitorização Luxar"},
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    except Exception as e:
        print(f"Erro ao enviar webhook: {e}")

@app.post("/scan-report", status_code=status.HTTP_201_CREATED)  
def scan_report(report: ScanReport, db: Session = Depends(get_db)):  
    now = datetime.utcnow()  
    payload_text = json.dumps(report.details or {})  
    
    # Envia o log para o Discord com os detalhes novos
    send_discord_detailed_log(report)

    # Lógica original de armazenamento
    log = ScanLog(job_id=report.job_id, scanner_id=report.scanner_id, payload=payload_text, timestamp=now)  
    db.add(log)  
    
    server = db.query(Server).filter_by(job_id=report.job_id).first()  
    if server:  
        server.last_seen = now  
        server.data = payload_text  
        server.scanned = True  # Marca como escaneado para o hopper não repetir
        if report.has_rare:  
            server.has_rare = True  
    else:  
        server = Server(job_id=report.job_id, has_rare=report.has_rare, data=payload_text, scanned=True, first_seen=now, last_seen=now)  
        db.add(server)  
    
    db.commit()  
    return {"status": "ok"}  

@app.post("/add-job", status_code=status.HTTP_201_CREATED)  
def add_job(request: AddJobRequest, db: Session = Depends(get_db)):  
    existing = db.query(Server).filter_by(job_id=request.job_id).first()  
    if existing:  
        return {"status": "already_exists"}  
    
    server = Server(job_id=request.job_id, scanned=False, assigned=False)  
    db.add(server)  
    db.commit()  
    return {"status": "added"}  

@app.get("/next-server", response_model=Optional[NextServerResponse])  
def next_server(scanner_id: Optional[str] = None, db: Session = Depends(get_db)):  
    server = db.query(Server).filter_by(assigned=False, scanned=False).order_by(Server.first_seen.asc()).first()  
    if not server:  
        return None  
    
    server.assigned = True  
    server.assigned_to = scanner_id  
    server.assigned_at = datetime.utcnow()  
    db.commit()  
    
    return {"job_id": server.job_id}

@app.get("/servers")  
def list_servers(db: Session = Depends(get_db)):  
    servers = db.query(Server).all()  
    return {"count": len(servers), "servers": [s.job_id for s in servers]}

if __name__ == "__main__":  
    import uvicorn  
    uvicorn.run(app, host="0.0.0.0", port=8080)
