from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime
import json
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

DB_FILE = os.environ.get("DB_FILE", "servers.db")
DATABASE_URL = f"sqlite:///{DB_FILE}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()

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

@app.post("/scan-report", status_code=status.HTTP_201_CREATED)
def scan_report(report: ScanReport, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    payload_text = json.dumps(report.details or {})
    log = ScanLog(job_id=report.job_id, scanner_id=report.scanner_id, payload=payload_text, timestamp=now)
    db.add(log)
    server = db.query(Server).filter_by(job_id=report.job_id).first()
    if server:
        server.last_seen = now
        if payload_text != "{}":
            server.data = payload_text
        if report.has_rare:
            server.has_rare = True
    else:
        server = Server(job_id=report.job_id, has_rare=report.has_rare, data=payload_text, first_seen=now, last_seen=now)
        db.add(server)
    db.commit()
    return {"status": "ok", "job_id": report.job_id, "has_rare": report.has_rare}

@app.get("/next-server", response_model=Optional[NextServerResponse])
def next_server(scanner_id: Optional[str] = None, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    server = db.query(Server).filter_by(has_rare=True, assigned=False, scanned=False).order_by(Server.first_seen.asc()).first()
    if not server:
        return None
    updated = db.query(Server).filter_by(id=server.id, assigned=False).update({
        "assigned": True,
        "assigned_to": scanner_id,
        "assigned_at": now
    })
    if updated:
        db.commit()
        s = db.query(Server).filter_by(id=server.id).first()
        try:
            data_parsed = json.loads(s.data) if s.data else {}
        except Exception:
            data_parsed = {}
        return NextServerResponse(job_id=s.job_id, data=data_parsed, assigned_to=s.assigned_to, assigned_at=s.assigned_at)
    else:
        db.rollback()
        return None

@app.post("/mark-scanned")
def mark_scanned(req: MarkScannedRequest, db: Session = Depends(get_db)):
    server = db.query(Server).filter_by(job_id=req.job_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="job_id not found")
    server.scanned = req.scanned
    server.assigned = False
    server.assigned_to = None
    server.assigned_at = None
    server.last_seen = datetime.utcnow()
    db.commit()
    return {"status": "ok", "job_id": req.job_id, "scanned": server.scanned}

@app.get("/servers")
def list_servers(limit: int = 100, db: Session = Depends(get_db)):
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
