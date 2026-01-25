from fastapi import FastAPI, HTTPException, Depends, Request, status
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime
import json
import os

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# DB setup (SQLite para simplicidade)
DB_FILE = os.environ.get("DB_FILE", "servers.db")
DATABASE_URL = f"sqlite:///{DB_FILE}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Server(Base):
    __tablename__ = "servers"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True, nullable=False)  # JobID do Roblox
    has_rare = Column(Boolean, default=False, index=True)
    data = Column(Text, default="{}")  # JSON string with extra info (map, players, items, etc)
    assigned = Column(Boolean, default=False, index=True)  # se foi atribuído a um bot
    assigned_to = Column(String, nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    scanned = Column(Boolean, default=False, index=True)  # se já foi scanado/varrido definitivamente
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


# Pydantic models
class ScanReport(BaseModel):
    job_id: str
    has_rare: bool
    scanner_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None  # qualquer dado adicional (items, coords, etc)


class NextServerResponse(BaseModel):
    job_id: str
    data: Optional[Dict[str, Any]] = None
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None


class MarkScannedRequest(BaseModel):
    job_id: str
    scanner_id: Optional[str] = None
    scanned: bool = True  # marcar como escaneado (remover do pool)


app = FastAPI(title="Job ID Fetcher - Steal a Brainrot")


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/scan-report", status_code=status.HTTP_201_CREATED)
def scan_report(report: ScanReport, db: Session = Depends(get_db)):
    """
    Recebe relatórios de scan.
    Corpo JSON:
    {
      "job_id": "123456789",
      "has_rare": true,
      "scanner_id": "bot-1",
      "details": { ... }
    }
    """
    now = datetime.utcnow()
    payload_text = json.dumps(report.details or {})

    # salvar log
    log = ScanLog(job_id=report.job_id, scanner_id=report.scanner_id, payload=payload_text, timestamp=now)
    db.add(log)

    # upsert no servidor
    server = db.query(Server).filter_by(job_id=report.job_id).first()
    if server:
        server.last_seen = now
        server.data = payload_text if payload_text != "{}" else server.data
        # once has_rare becomes True keep it True
        if report.has_rare:
            server.has_rare = True
    else:
        server = Server(
            job_id=report.job_id,
            has_rare=report.has_rare,
            data=payload_text,
            first_seen=now,
            last_seen=now
        )
        db.add(server)

    db.commit()
    return {"status": "ok", "job_id": report.job_id, "has_rare": report.has_rare}


@app.get("/next-server", response_model=Optional[NextServerResponse])
def next_server(scanner_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Retorna o próximo servidor com item raro disponível para pular.
    Marca o servidor como 'assigned' para evitar que outros bots peguem ao mesmo tempo.
    Parâmetro opcional: scanner_id (id do bot que solicita)
    """
    now = datetime.utcnow()

    # Procurar um servidor disponível (has_rare=True, not assigned, not scanned)
    # Tentamos de forma simples: buscar e depois atualizar por id para evitar race conditions
    server = db.query(Server).filter_by(has_rare=True, assigned=False, scanned=False).order_by(Server.first_seen.asc()).first()
    if not server:
        # nada disponível
        return None

    # tentar marcar como assigned atomically-ish
    updated = db.query(Server).filter_by(id=server.id, assigned=False).update({
        "assigned": True,
        "assigned_to": scanner_id,
        "assigned_at": now
    })
    if updated:
        db.commit()
        # recarregar
        s = db.query(Server).filter_by(id=server.id).first()
        try:
            data_parsed = json.loads(s.data) if s.data else {}
        except Exception:
            data_parsed = {}
        return NextServerResponse(job_id=s.job_id, data=data_parsed, assigned_to=s.assigned_to, assigned_at=s.assigned_at)
    else:
        # outra concorrência pegou; retornar null para o cliente tentar novamente
        db.rollback()
        return None


@app.post("/mark-scanned")
def mark_scanned(req: MarkScannedRequest, db: Session = Depends(get_db)):
    """
    Marca um job_id como scanado (remover do pool de servidores a pular).
    {
      "job_id": "123",
      "scanner_id": "bot-1",
      "scanned": true
    }
    """
    server = db.query(Server).filter_by(job_id=req.job_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="job_id not found")
    server.scanned = req.scanned
    # liberar atribuição (opcional)
    server.assigned = False
    server.assigned_to = None
    server.assigned_at = None
    server.last_seen = datetime.utcnow()
    db.commit()
    return {"status": "ok", "job_id": req.job_id, "scanned": server.scanned}


@app.get("/servers")
def list_servers(limit: int = 100, db: Session = Depends(get_db)):
    """
    Lista servidores armazenados - para depuração/monitoramento.
    """
    servers = db.query(Server).order_by(Server.first_seen.desc()).limit(limit).all()
    result = []
    for s in servers:
        try:
            data = json.loads(s.data) if s.data else {}
        except Exception:
            data = {}
        result.append({
            "job_id": s.job_id,
            "has_rare": s.has_rare,
            "assigned": s.assigned,
            "assigned_to": s.assigned_to,
            "scanned": s.scanned,
            "first_seen": s.first_seen.isoformat() if s.first_seen else None,
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
            "data": data
        })
    return {"count": len(result), "servers": result}

