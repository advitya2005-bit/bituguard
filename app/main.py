from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import date
from collections import defaultdict

from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Date, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

import openpyxl

# -------------------------------------------------
# FASTAPI APP (Swagger hidden)
# -------------------------------------------------
app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# -------------------------------------------------
# CORS (UI access allowed)
# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# STATIC UI (IMPORTANT FIX)
# UI lives at /ui/*
# -------------------------------------------------
app.mount(
    "/ui",
    StaticFiles(directory="app/static", html=True),
    name="ui"
)

# -------------------------------------------------
# DATABASE (SQLite)
# -------------------------------------------------
DATABASE_URL = "sqlite:///./bituguard.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# -------------------------------------------------
# DATABASE TABLES
# -------------------------------------------------
class ReceiptDB(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True)
    tanker_no = Column(String)
    quantity = Column(Float)
    received_quantity = Column(Float)
    bitumen_rate = Column(Float)
    supplier = Column(String)
    receipt_date = Column(Date)
    loss_mt = Column(Float)
    loss_rupees = Column(Float)
    leakage_pct = Column(Float)

    labs = relationship("LabDB", back_populates="receipt")


class LabDB(Base):
    __tablename__ = "labs"

    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"))
    penetration = Column(Float)
    softening_point = Column(Float)
    ductility = Column(Float)
    verdict = Column(String)

    receipt = relationship("ReceiptDB", back_populates="labs")


Base.metadata.create_all(engine)

# -------------------------------------------------
# API INPUT MODELS
# -------------------------------------------------
class Receipt(BaseModel):
    tanker_no: str
    quantity: float
    received_quantity: float
    bitumen_rate: float
    supplier: str
    receipt_date: date


class Lab(BaseModel):
    receipt_id: int
    penetration: float
    softening_point: float
    ductility: float

# -------------------------------------------------
# SAVE RECEIPT
# -------------------------------------------------
@app.post("/save")
def save_receipt(data: Receipt):
    db = SessionLocal()

    loss_mt = max(0, data.quantity - data.received_quantity)
    loss_rupees = round(loss_mt * data.bitumen_rate, 2)
    leakage_pct = round((loss_mt / data.quantity) * 100, 2) if data.quantity > 0 else 0

    rec = ReceiptDB(
        tanker_no=data.tanker_no,
        quantity=data.quantity,
        received_quantity=data.received_quantity,
        bitumen_rate=data.bitumen_rate,
        supplier=data.supplier,
        receipt_date=data.receipt_date,
        loss_mt=loss_mt,
        loss_rupees=loss_rupees,
        leakage_pct=leakage_pct
    )

    db.add(rec)
    db.commit()
    db.refresh(rec)
    db.close()

    return {
        "receipt_id": rec.id,
        "loss_rupees": loss_rupees,
        "leakage_pct": leakage_pct
    }

# -------------------------------------------------
# SAVE LAB REPORT
# -------------------------------------------------
@app.post("/lab")
def save_lab(data: Lab):
    db = SessionLocal()

    verdict = "PASS"
    if data.penetration < 50 or data.ductility < 75:
        verdict = "FAIL"

    lab = LabDB(
        receipt_id=data.receipt_id,
        penetration=data.penetration,
        softening_point=data.softening_point,
        ductility=data.ductility,
        verdict=verdict
    )

    db.add(lab)
    db.commit()
    db.close()

    return {"ai_verdict": verdict}

# -------------------------------------------------
# ALERTS (Leakage + Supplier Risk)
# -------------------------------------------------
@app.get("/fraud/alerts")
def fraud_alerts():
    db = SessionLocal()
    alerts = []

    receipts = db.query(ReceiptDB).all()
    for r in receipts:
        if r.leakage_pct >= 3:
            alerts.append({
                "type": "LEAKAGE",
                "message": f"{r.tanker_no} leakage {r.leakage_pct}%"
            })

    supplier_fail = defaultdict(int)
    labs = db.query(LabDB).filter(LabDB.verdict == "FAIL").all()

    for lab in labs:
        supplier_fail[lab.receipt.supplier] += 1

    for supplier, count in supplier_fail.items():
        if count >= 3:
            alerts.append({
                "type": "SUPPLIER_QUALITY_RISK",
                "message": f"{supplier} has {count} quality FAILs"
            })

    db.close()
    return {"alerts": alerts}

# -------------------------------------------------
# MONTHLY ANALYTICS
# -------------------------------------------------
@app.get("/analytics/loss/monthly")
def monthly_loss(year: int, month: int):
    db = SessionLocal()
    receipts = db.query(ReceiptDB).all()

    total_loss = 0
    supplier_loss = defaultdict(float)

    for r in receipts:
        if r.receipt_date.year == year and r.receipt_date.month == month:
            total_loss += r.loss_rupees
            supplier_loss[r.supplier] += r.loss_rupees

    db.close()
    return {
        "year": year,
        "month": month,
        "total_loss_rupees": total_loss,
        "supplier_loss": supplier_loss
    }

# -------------------------------------------------
# EXCEL AUDIT DOWNLOAD
# -------------------------------------------------
@app.get("/audit/excel")
def audit_excel(year: int, month: int):
    db = SessionLocal()
    receipts = db.query(ReceiptDB).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bitumen Audit"

    ws.append([
        "Date", "Tanker", "Supplier",
        "Invoice Qty", "Received Qty",
        "Rate", "Loss MT", "Loss ₹", "Leakage %"
    ])

    for r in receipts:
        if r.receipt_date.year == year and r.receipt_date.month == month:
            ws.append([
                str(r.receipt_date),
                r.tanker_no,
                r.supplier,
                r.quantity,
                r.received_quantity,
                r.bitumen_rate,
                r.loss_mt,
                r.loss_rupees,
                r.leakage_pct
            ])

    filename = f"audit_{year}_{month}.xlsx"
    wb.save(filename)
    db.close()

    return FileResponse(
        filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )
