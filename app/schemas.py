from pydantic import BaseModel, Field
from datetime import date


class ReceiptCreate(BaseModel):
    tanker_no: str
    quantity: float
    received_quantity: float | None = None
    bitumen_rate: float | None = 55000

    bitumen_grade: str
    supplier: str
    receipt_date: date


class LabReportCreate(BaseModel):
    receipt_id: int
    penetration: float
    softening_point: float
    ductility: float
