from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import Medicine, MedicationRecord, RestockRecord, RiskAlert, BabyMedicineConfig
from app.schemas import MedicineCreate, MedicineUpdate, MedicineOut, MedicineList
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/medicines", tags=["药品档案管理"])


@router.post("", response_model=dict)
def create_medicine(medicine: MedicineCreate, db: Session = Depends(get_db)):
    db_medicine = Medicine(**medicine.model_dump())
    db.add(db_medicine)
    db.commit()
    db.refresh(db_medicine)
    return success_response(data=MedicineOut.model_validate(db_medicine).model_dump(), message="药品创建成功")


@router.get("", response_model=dict)
def list_medicines(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    medicine_type: Optional[str] = Query(None, description="药品类型"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    db: Session = Depends(get_db)
):
    query = db.query(Medicine)

    if medicine_type:
        query = query.filter(Medicine.medicine_type == medicine_type)
    if keyword:
        query = query.filter(Medicine.name.contains(keyword))

    total = query.count()
    items = query.order_by(Medicine.id.desc()).offset(skip).limit(limit).all()

    result = {
        "total": total,
        "items": [MedicineOut.model_validate(item).model_dump() for item in items]
    }
    return success_response(data=result, message="查询成功")


@router.get("/{medicine_id}", response_model=dict)
def get_medicine(medicine_id: int, db: Session = Depends(get_db)):
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")
    return success_response(data=MedicineOut.model_validate(medicine).model_dump(), message="查询成功")


@router.put("/{medicine_id}", response_model=dict)
def update_medicine(medicine_id: int, medicine: MedicineUpdate, db: Session = Depends(get_db)):
    db_medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not db_medicine:
        return error_response(code=404, message="药品不存在")

    update_data = medicine.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_medicine, key, value)

    db.commit()
    db.refresh(db_medicine)
    return success_response(data=MedicineOut.model_validate(db_medicine).model_dump(), message="更新成功")


@router.delete("/{medicine_id}", response_model=dict)
def delete_medicine(medicine_id: int, db: Session = Depends(get_db)):
    db_medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not db_medicine:
        return error_response(code=404, message="药品不存在")

    db.query(RiskAlert).filter(RiskAlert.medicine_id == medicine_id).delete(synchronize_session=False)
    db.query(MedicationRecord).filter(MedicationRecord.medicine_id == medicine_id).delete(synchronize_session=False)
    db.query(RestockRecord).filter(RestockRecord.medicine_id == medicine_id).delete(synchronize_session=False)
    db.query(BabyMedicineConfig).filter(BabyMedicineConfig.medicine_id == medicine_id).delete(synchronize_session=False)

    db.delete(db_medicine)
    db.commit()
    return success_response(message="删除成功")


@router.post("/{medicine_id}/open", response_model=dict)
def mark_as_opened(medicine_id: int, db: Session = Depends(get_db)):
    from datetime import date
    db_medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not db_medicine:
        return error_response(code=404, message="药品不存在")

    db_medicine.open_date = date.today()
    db.commit()
    db.refresh(db_medicine)
    return success_response(data=MedicineOut.model_validate(db_medicine).model_dump(), message="已标记为开封")
