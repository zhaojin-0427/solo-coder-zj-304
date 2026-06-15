from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models import MedicationRecord, Medicine
from app.schemas import MedicationRecordCreate, MedicationRecordOut
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/records", tags=["用药记录"])


@router.post("", response_model=dict)
def create_record(record: MedicationRecordCreate, db: Session = Depends(get_db)):
    medicine = db.query(Medicine).filter(Medicine.id == record.medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    db_record = MedicationRecord(**record.model_dump())
    if not db_record.administration_time:
        db_record.administration_time = datetime.now()

    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return success_response(data=MedicationRecordOut.model_validate(db_record).model_dump(), message="用药记录创建成功")


@router.get("", response_model=dict)
def list_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    medicine_id: Optional[int] = Query(None),
    baby_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(MedicationRecord)

    if medicine_id is not None:
        medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
        if not medicine:
            return error_response(code=404, message="药品不存在")
        query = query.filter(MedicationRecord.medicine_id == medicine_id)
    if baby_id is not None:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")
        query = query.filter(MedicationRecord.baby_id == baby_id)

    total = query.count()
    items = query.order_by(MedicationRecord.administration_time.desc()).offset(skip).limit(limit).all()

    result = {
        "total": total,
        "items": [MedicationRecordOut.model_validate(item).model_dump() for item in items]
    }
    return success_response(data=result, message="查询成功")


@router.get("/{record_id}", response_model=dict)
def get_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(MedicationRecord).filter(MedicationRecord.id == record_id).first()
    if not record:
        return error_response(code=404, message="用药记录不存在")
    return success_response(data=MedicationRecordOut.model_validate(record).model_dump(), message="查询成功")


@router.delete("/{record_id}", response_model=dict)
def delete_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(MedicationRecord).filter(MedicationRecord.id == record_id).first()
    if not record:
        return error_response(code=404, message="用药记录不存在")

    db.delete(record)
    db.commit()
    return success_response(message="删除成功")
