from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import BabyMedicineConfig, BabyProfile, Medicine
from app.schemas import BabyMedicineConfigCreate, BabyMedicineConfigUpdate, BabyMedicineConfigOut
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/baby-medicine-config", tags=["宝宝药品适配配置"])


@router.post("", response_model=dict)
def create_baby_medicine_config(config: BabyMedicineConfigCreate, db: Session = Depends(get_db)):
    baby = db.query(BabyProfile).filter(BabyProfile.id == config.baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")

    medicine = db.query(Medicine).filter(Medicine.id == config.medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    existing = db.query(BabyMedicineConfig).filter(
        BabyMedicineConfig.baby_id == config.baby_id,
        BabyMedicineConfig.medicine_id == config.medicine_id
    ).first()
    if existing:
        return error_response(code=400, message="该宝宝对此药品的适配配置已存在，请使用更新接口")

    db_config = BabyMedicineConfig(**config.model_dump())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return success_response(
        data=BabyMedicineConfigOut.model_validate(db_config).model_dump(),
        message="宝宝药品适配配置创建成功"
    )


@router.get("", response_model=dict)
def list_baby_medicine_configs(
    baby_id: Optional[int] = Query(None, description="按宝宝ID筛选"),
    medicine_id: Optional[int] = Query(None, description="按药品ID筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(BabyMedicineConfig)

    if baby_id is not None:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")
        query = query.filter(BabyMedicineConfig.baby_id == baby_id)
    if medicine_id is not None:
        medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
        if not medicine:
            return error_response(code=404, message="药品不存在")
        query = query.filter(BabyMedicineConfig.medicine_id == medicine_id)

    total = query.count()
    items = query.order_by(BabyMedicineConfig.id.desc()).offset(skip).limit(limit).all()

    result_items = []
    for item in items:
        out = BabyMedicineConfigOut.model_validate(item).model_dump()
        out["baby_name"] = item.baby.name if item.baby else None
        out["medicine_name"] = item.medicine.name if item.medicine else None
        result_items.append(out)

    result = {
        "total": total,
        "items": result_items
    }
    return success_response(data=result, message="查询成功")


@router.get("/{config_id}", response_model=dict)
def get_baby_medicine_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(BabyMedicineConfig).filter(BabyMedicineConfig.id == config_id).first()
    if not config:
        return error_response(code=404, message="适配配置不存在")

    out = BabyMedicineConfigOut.model_validate(config).model_dump()
    out["baby_name"] = config.baby.name if config.baby else None
    out["medicine_name"] = config.medicine.name if config.medicine else None
    return success_response(data=out, message="查询成功")


@router.put("/{config_id}", response_model=dict)
def update_baby_medicine_config(
    config_id: int,
    config_update: BabyMedicineConfigUpdate,
    db: Session = Depends(get_db)
):
    db_config = db.query(BabyMedicineConfig).filter(BabyMedicineConfig.id == config_id).first()
    if not db_config:
        return error_response(code=404, message="适配配置不存在")

    update_data = config_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_config, key, value)

    db.commit()
    db.refresh(db_config)

    out = BabyMedicineConfigOut.model_validate(db_config).model_dump()
    out["baby_name"] = db_config.baby.name if db_config.baby else None
    out["medicine_name"] = db_config.medicine.name if db_config.medicine else None
    return success_response(data=out, message="更新成功")


@router.delete("/{config_id}", response_model=dict)
def delete_baby_medicine_config(config_id: int, db: Session = Depends(get_db)):
    db_config = db.query(BabyMedicineConfig).filter(BabyMedicineConfig.id == config_id).first()
    if not db_config:
        return error_response(code=404, message="适配配置不存在")

    db.delete(db_config)
    db.commit()
    return success_response(message="删除成功")


@router.get("/baby/{baby_id}/overview", response_model=dict)
def get_baby_medicine_overview(baby_id: int, db: Session = Depends(get_db)):
    baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")

    configs = db.query(BabyMedicineConfig).filter(BabyMedicineConfig.baby_id == baby_id).all()
    total_medicines = db.query(Medicine).count()

    disabled_count = sum(1 for c in configs if c.is_disabled)
    stock_alert_enabled = sum(1 for c in configs if c.enable_stock_alert)
    open_alert_enabled = sum(1 for c in configs if c.enable_open_alert)

    disabled_list = []
    for c in configs:
        if c.is_disabled:
            med = c.medicine
            disabled_list.append({
                "medicine_id": c.medicine_id,
                "medicine_name": med.name if med else None,
                "disable_reason": c.disable_reason,
                "contraindication_tags": c.contraindication_tags,
                "doctor_advice": c.doctor_advice
            })

    result = {
        "baby_id": baby_id,
        "baby_name": baby.name,
        "total_medicines": total_medicines,
        "configured_medicines": len(configs),
        "disabled_count": disabled_count,
        "stock_alert_enabled_count": stock_alert_enabled,
        "open_alert_enabled_count": open_alert_enabled,
        "coverage_rate": round(len(configs) / total_medicines, 4) if total_medicines > 0 else 0,
        "disabled_medicines": disabled_list
    }
    return success_response(data=result, message="宝宝药品适配概览获取成功")
