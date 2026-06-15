from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date
from dateutil.relativedelta import relativedelta

from app.database import get_db
from app.models import BabyProfile
from app.schemas import BabyProfileCreate, BabyProfileUpdate, BabyProfileOut
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/baby", tags=["宝宝档案"])


def calculate_age_months(birth_date: date) -> int:
    delta = relativedelta(date.today(), birth_date)
    return delta.years * 12 + delta.months


@router.post("", response_model=dict)
def create_baby(baby: BabyProfileCreate, db: Session = Depends(get_db)):
    age_months = calculate_age_months(baby.birth_date)
    db_baby = BabyProfile(**baby.model_dump(), current_age_months=age_months)
    db.add(db_baby)
    db.commit()
    db.refresh(db_baby)
    return success_response(data=BabyProfileOut.model_validate(db_baby).model_dump(), message="宝宝档案创建成功")


@router.get("", response_model=dict)
def list_babies(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(BabyProfile)
    total = query.count()
    babies = query.order_by(BabyProfile.id.desc()).offset(skip).limit(limit).all()

    for baby in babies:
        baby.current_age_months = calculate_age_months(baby.birth_date)

    result = {
        "total": total,
        "items": [BabyProfileOut.model_validate(baby).model_dump() for baby in babies]
    }
    return success_response(data=result, message="查询成功")


@router.get("/{baby_id}", response_model=dict)
def get_baby(baby_id: int, db: Session = Depends(get_db)):
    baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")
    baby.current_age_months = calculate_age_months(baby.birth_date)
    return success_response(data=BabyProfileOut.model_validate(baby).model_dump(), message="查询成功")


@router.put("/{baby_id}", response_model=dict)
def update_baby(baby_id: int, baby: BabyProfileUpdate, db: Session = Depends(get_db)):
    db_baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not db_baby:
        return error_response(code=404, message="宝宝档案不存在")

    update_data = baby.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_baby, key, value)

    if "birth_date" in update_data:
        db_baby.current_age_months = calculate_age_months(db_baby.birth_date)

    db.commit()
    db.refresh(db_baby)
    return success_response(data=BabyProfileOut.model_validate(db_baby).model_dump(), message="更新成功")


@router.delete("/{baby_id}", response_model=dict)
def delete_baby(baby_id: int, db: Session = Depends(get_db)):
    db_baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not db_baby:
        return error_response(code=404, message="宝宝档案不存在")

    db.delete(db_baby)
    db.commit()
    return success_response(message="删除成功")
