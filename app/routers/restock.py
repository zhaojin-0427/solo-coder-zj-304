from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models import RestockRecord, Medicine, BabyMedicineConfig, BabyProfile
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

    result = RestockRecordOut.model_validate(db_record).model_dump()

    from app.services.recall_service import check_restock_recall_risk
    recall_risk = check_restock_recall_risk(record.medicine_id, record.batch_number, db)
    if recall_risk:
        result["recall_risk"] = recall_risk

    return success_response(data=result, message="补货记录创建成功")


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
def get_restock_suggestions(
    baby_id: Optional[int] = Query(None, description="宝宝ID，传了则按个性化库存提醒配置筛选"),
    db: Session = Depends(get_db)
):
    medicines = db.query(Medicine).all()
    suggestions: List[dict] = []

    baby = None
    if baby_id is not None:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")

    for med in medicines:
        baby_config = None
        if baby_id:
            baby_config = db.query(BabyMedicineConfig).filter(
                BabyMedicineConfig.baby_id == baby_id,
                BabyMedicineConfig.medicine_id == med.id
            ).first()
            if baby_config and not baby_config.enable_stock_alert:
                continue

        suggestion = _generate_suggestion(med, baby_id=baby_id, baby_name=baby.name if baby else None, db=db)
        if suggestion:
            suggestions.append(suggestion)

    suggestions.sort(key=lambda x: _urgency_priority(x["urgency"]))

    return success_response(data=suggestions, message="补货建议生成成功")


def _generate_suggestion(medicine: Medicine, baby_id: int = None, baby_name: str = None, db: Session = None) -> Optional[dict]:
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
    if days_to_expiry < 0:
        reason += f"；注意：当前库存药品已过期 {abs(days_to_expiry)} 天，请勿使用，建议直接更换新药"
    elif days_to_expiry < 30:
        reason += f"；注意：药品仅剩 {days_to_expiry} 天过期，补货时请注意有效期"

    result = {
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
    if baby_id is not None:
        result["baby_id"] = baby_id
        result["baby_name"] = baby_name

    if db is not None:
        from app.services.recall_service import get_medicine_recall_info
        recall_info = get_medicine_recall_info(medicine.id, db)
        if recall_info:
            result["recall_info"] = recall_info
            if urgency not in ["critical", "high"]:
                urgency = "high"
                result["urgency"] = "high"
            result["reason"] += "；注意：该药品存在召回风险，补货前请确认召回情况"

    return result


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
