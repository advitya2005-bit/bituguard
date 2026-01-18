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
# APP
# -------------------------------------------------
app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# STATIC FILES
# -------------------------------------------------
app.mount(
    "/ui",
    StaticFiles(directory="app/static", html=True),
    name="ui"
)

# -------------------------------------------------
# DATABASE
# -------------------------------------------------
DATABASE_URL = "sqlite:///./bituguard.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# -------------------------------------------------
# DATABASE MODELS
# -------------------------------------------------
class ReceiptDB(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True)
    tanker_no = Column(String)
    grade = Column(String)
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
# INPUT SCHEMAS
# -------------------------------------------------
class Receipt(BaseModel):
    tanker_no: str
    grade: str
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
# WHATSAPP (SAFE MODE)
# -------------------------------------------------
def send_whatsapp(message: str):
    print("\n========== WHATSAPP ALERT ==========")
    print(message)
    print("===================================\n")

# -------------------------------------------------
# QUALITY CHECK (GRADE BASED)
# -------------------------------------------------
def check_quality(grade, penetration, softening, ductility):
    limits = {
        "VG10": {"pen": (80, 100), "soft": 40, "duct": 75},
        "VG30": {"pen": (50, 70), "soft": 47, "duct": 75},
        "VG40": {"pen": (40, 60), "soft": 50, "duct": 50},
    }

    g = limits.get(grade)
    if not g:
        return "FAIL"

    if not (g["pen"][0] <= penetration <= g["pen"][1]):
        return "FAIL"
    if softening < g["soft"]:
        return "FAIL"
    if ductility < g["duct"]:
        return "FAIL"

    return "PASS"

# -------------------------------------------------
# SAVE RECEIPT
# -------------------------------------------------
@app.post("/save")
def save_receipt(data: Receipt):
    db = SessionLocal()

    if not data.grade:
        return {"error": "Grade required"}

    loss_mt = max(0, data.quantity - data.received_quantity)
    loss_rupees = round(loss_mt * data.bitumen_rate, 2)
    leakage_pct = round(
        (loss_mt / data.quantity) * 100, 2
    ) if data.quantity > 0 else 0

    rec = ReceiptDB(
        tanker_no=data.tanker_no,
        grade=data.grade,
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
# SAVE LAB RESULT
# -------------------------------------------------
@app.post("/lab")
def save_lab(data: Lab):
    db = SessionLocal()

    receipt = db.query(ReceiptDB).filter(
        ReceiptDB.id == data.receipt_id
    ).first()

    if not receipt:
        db.close()
        return {"error": "Invalid receipt ID"}

    verdict = check_quality(
        receipt.grade,
        data.penetration,
        data.softening_point,
        data.ductility
    )

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
# FRAUD / ALERTS
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
                "message": f"{r.tanker_no} ({r.grade}) leakage {r.leakage_pct}%"
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
# SUPPLIER SCORECARD
# -------------------------------------------------
@app.get("/supplier/scorecard")
def supplier_scorecard():
    db = SessionLocal()

    receipts = db.query(ReceiptDB).all()
    labs = db.query(LabDB).all()

    data = {}

    for r in receipts:
        key = r.supplier.lower()
        if key not in data:
            data[key] = {
                "supplier": r.supplier,
                "tankers": 0,
                "total_leakage": 0,
                "quality_fails": 0
            }
        data[key]["tankers"] += 1
        data[key]["total_leakage"] += r.leakage_pct

    for lab in labs:
        if lab.verdict == "FAIL":
            key = lab.receipt.supplier.lower()
            if key in data:
                data[key]["quality_fails"] += 1

    result = []
    for s in data.values():
        avg_leak = round(
            s["total_leakage"] / s["tankers"], 2
        ) if s["tankers"] > 0 else 0

        if s["quality_fails"] >= 3 or avg_leak >= 5:
            risk = "HIGH"
        elif s["quality_fails"] >= 1 or avg_leak >= 3:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        result.append({
            "supplier": s["supplier"],
            "tankers": s["tankers"],
            "avg_leakage_pct": avg_leak,
            "quality_fails": s["quality_fails"],
            "risk": risk
        })

    db.close()
    return result

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
# AUDIT EXCEL
# -------------------------------------------------
@app.get("/audit/excel")
def audit_excel(year: int, month: int):
    db = SessionLocal()
    receipts = db.query(ReceiptDB).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bitumen Audit"

    ws.append([
        "Date", "Tanker", "Grade", "Supplier",
        "Invoice Qty", "Received Qty",
        "Rate", "Loss MT", "Loss ₹", "Leakage %"
    ])

    for r in receipts:
        if r.receipt_date.year == year and r.receipt_date.month == month:
            ws.append([
                str(r.receipt_date),
                r.tanker_no,
                r.grade,
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
