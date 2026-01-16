from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from app.database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True)
    tanker_no = Column(String, nullable=False)

    quantity = Column(Float, nullable=False)              # invoiced
    received_quantity = Column(Float, nullable=True)     # measured

    bitumen_rate = Column(Float, default=55000)          # ₹ per MT
    loss_rupees = Column(Float, default=0)               # auto-calculated

    bitumen_grade = Column(String, nullable=False)
    supplier = Column(String, nullable=False)
    receipt_date = Column(Date, nullable=False)


class LabReport(Base):
    __tablename__ = "lab_reports"

    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)

    penetration = Column(Float, nullable=False)
    softening_point = Column(Float, nullable=False)
    ductility = Column(Float, nullable=False)

    ai_verdict = Column(String, nullable=False)
    ai_comment = Column(String, nullable=False)
