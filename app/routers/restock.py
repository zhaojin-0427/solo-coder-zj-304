from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models import RestockRecord, Medicine
from app.schemas import RestockRecordCreate, RestockRecordOut, RestockSuggestion
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/restock", tags=["补货建议与记录"])


@router.post("", response_model=dict)
def create_restock(record: RestockRecordCreate, db: Session = Depends(get_db)):
    medicine = db.query(Medicine).filter(Medicine.id == record.medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    db_record = RestockRecord(**record.model_dump())
    db.add(db_record)

    medicine.current_stock += record.quantity
    if not medicine.open_date and record.purchase_date:
        pass

    db.commit()
    db.refresh(db_record)
    return success_response(data=RestockRecordOut.model_validate(db_record).model_dump(), message="补货记录创建成功")


@router.get("", response_model=dict)
def list_restock_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    medicine_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(RestockRecord)

    if medicine_id:
        query = query.filter(RestockRecord.medicine_id == medicine_id)

    total = query.count()
    items = query.order_by(RestockRecord.purchase_date.desc()).offset(skip).limit(limit).all()

    result = {
        "total": total,
        "items": [RestockRecordOut.model_validate(item).model_dump() for item in items]
    }
    return success_response(data=result, message="查询成功")


@router.get("/suggestions", response_model=dict)
def get_restock_suggestions(db: Session = Depends(get_db)):
    medicines = db.query(Medicine).all()
    suggestions: List[dict] = []

    for med in medicines:
        suggestion = _generate_suggestion(med)
        if suggestion:
            suggestions.append(suggestion)

    suggestions.sort(key=lambda x: _urgency_priority(x["urgency"]))

    return success_response(data=suggestions, message="补货建议生成成功")


def _generate_suggestion(medicine: Medicine) -> Optional[dict]:
    if medicine.current_stock >= medicine.min_stock * 1.5:
        return None

    urgency = "low"
    reason = ""

    if medicine.current_stock <= 0:
        urgency = "critical"
        reason = f"当前库存为0，已断货，急需补货"
        suggested = medicine.min_stock * 2
    elif medicine.current_stock <= medicine.min_stock * 0.2:
        urgency = "high"
        reason = f"库存严重不足，仅剩余 {medicine.current_stock} {medicine.stock_unit}"
        suggested = medicine.min_stock * 2 - medicine.current_stock
    elif medicine.current_stock <= medicine.min_stock * 0.5:
        urgency = "medium"
        reason = f"库存偏低，剩余 {medicine.current_stock} {medicine.stock_unit}"
        suggested = medicine.min_stock * 1.5 - medicine.current_stock
    elif medicine.current_stock < medicine.min_stock:
        urgency = "low"
        reason = f"库存略低于警戒线，剩余 {medicine.current_stock} {medicine.stock_unit}"
        suggested = medicine.min_stock - medicine.current_stock
    else:
        return None

    from datetime import date
    days_to_expiry = (medicine.expiry_date - date.today()).days
    if days_to_expiry < 30:
        reason += f"；注意：药品仅剩 {days_to_expiry} 天过期，补货时请注意有效期"

    return {
        "medicine_id": medicine.id,
        "medicine_name": medicine.name,
        "medicine_type": medicine.medicine_type,
        "current_stock": medicine.current_stock,
        "stock_unit": medicine.stock_unit,
        "min_stock": medicine.min_stock,
        "suggested_quantity": round(suggested, 2),
        "reason": reason,
        "urgency": urgency
    }


@router.get("/{record_id}", response_model=dict)
def get_restock_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(RestockRecord).filter(RestockRecord.id == record_id).first()
    if not record:
        return error_response(code=404, message="补货记录不存在")
    return success_response(data=RestockRecordOut.model_validate(record).model_dump(), message="查询成功")


def _urgency_priority(urgency: str) -> int:
    priority = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3
    }
    return priority.get(urgency, 99)
