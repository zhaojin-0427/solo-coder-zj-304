from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime

from app.database import get_db
from app.models import (
    BabyProfile, Medicine, BabyWeightRecord,
    MedicineDosageRule, MedicationPlan, MedicationRecord
)
from app.schemas import (
    BabyWeightRecordCreate, BabyWeightRecordOut,
    MedicineDosageRuleCreate, MedicineDosageRuleUpdate, MedicineDosageRuleOut,
    MedicationPlanCreate, MedicationPlanUpdate, MedicationPlanOut,
    DosageCheckResult
)
from app.services.dosage_service import (
    get_latest_weight, get_matching_dosage_rule,
    calculate_recommended_dose, generate_medication_plan,
    check_dosage_safety
)
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/dosage", tags=["体重剂量计划与安全用量校验"])


@router.post("/weight-records", response_model=dict)
def create_weight_record(record: BabyWeightRecordCreate, db: Session = Depends(get_db)):
    baby = db.query(BabyProfile).filter(BabyProfile.id == record.baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")

    db_record = BabyWeightRecord(**record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return success_response(
        data=BabyWeightRecordOut.model_validate(db_record).model_dump(),
        message="体重记录创建成功"
    )


@router.get("/weight-records", response_model=dict)
def list_weight_records(
    baby_id: int = Query(..., description="宝宝ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")

    query = db.query(BabyWeightRecord).filter(BabyWeightRecord.baby_id == baby_id)
    total = query.count()
    items = query.order_by(BabyWeightRecord.measured_date.desc()).offset(skip).limit(limit).all()

    latest = get_latest_weight(db, baby_id)

    result = {
        "total": total,
        "latest_weight": {
            "weight_kg": latest.weight_kg,
            "measured_date": latest.measured_date.isoformat()
        } if latest else None,
        "items": [BabyWeightRecordOut.model_validate(i).model_dump() for i in items]
    }
    return success_response(data=result, message="查询成功")


@router.get("/weight-records/{record_id}", response_model=dict)
def get_weight_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(BabyWeightRecord).filter(BabyWeightRecord.id == record_id).first()
    if not record:
        return error_response(code=404, message="体重记录不存在")
    return success_response(data=BabyWeightRecordOut.model_validate(record).model_dump(), message="查询成功")


@router.delete("/weight-records/{record_id}", response_model=dict)
def delete_weight_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(BabyWeightRecord).filter(BabyWeightRecord.id == record_id).first()
    if not record:
        return error_response(code=404, message="体重记录不存在")
    db.delete(record)
    db.commit()
    return success_response(message="删除成功")


@router.get("/weight-records/baby/{baby_id}/latest", response_model=dict)
def get_baby_latest_weight(baby_id: int, db: Session = Depends(get_db)):
    baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")

    latest = get_latest_weight(db, baby_id)
    if not latest:
        return success_response(data=None, message="暂无体重记录")

    return success_response(data=BabyWeightRecordOut.model_validate(latest).model_dump(), message="查询成功")


@router.post("/rules", response_model=dict)
def create_dosage_rule(rule: MedicineDosageRuleCreate, db: Session = Depends(get_db)):
    medicine = db.query(Medicine).filter(Medicine.id == rule.medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    db_rule = MedicineDosageRule(**rule.model_dump())
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return success_response(
        data=MedicineDosageRuleOut.model_validate(db_rule).model_dump(),
        message="剂量规则创建成功"
    )


@router.get("/rules", response_model=dict)
def list_dosage_rules(
    medicine_id: Optional[int] = Query(None, description="药品ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(MedicineDosageRule)
    if medicine_id:
        query = query.filter(MedicineDosageRule.medicine_id == medicine_id)

    total = query.count()
    items = query.order_by(MedicineDosageRule.id.desc()).offset(skip).limit(limit).all()

    result = {
        "total": total,
        "items": [MedicineDosageRuleOut.model_validate(i).model_dump() for i in items]
    }
    return success_response(data=result, message="查询成功")


@router.get("/rules/{rule_id}", response_model=dict)
def get_dosage_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(MedicineDosageRule).filter(MedicineDosageRule.id == rule_id).first()
    if not rule:
        return error_response(code=404, message="剂量规则不存在")
    return success_response(data=MedicineDosageRuleOut.model_validate(rule).model_dump(), message="查询成功")


@router.put("/rules/{rule_id}", response_model=dict)
def update_dosage_rule(rule_id: int, rule_update: MedicineDosageRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(MedicineDosageRule).filter(MedicineDosageRule.id == rule_id).first()
    if not rule:
        return error_response(code=404, message="剂量规则不存在")

    update_data = rule_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    db.commit()
    db.refresh(rule)
    return success_response(data=MedicineDosageRuleOut.model_validate(rule).model_dump(), message="更新成功")


@router.delete("/rules/{rule_id}", response_model=dict)
def delete_dosage_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(MedicineDosageRule).filter(MedicineDosageRule.id == rule_id).first()
    if not rule:
        return error_response(code=404, message="剂量规则不存在")

    db.query(MedicationPlan).filter(MedicationPlan.dosage_rule_id == rule_id).delete(synchronize_session=False)
    db.delete(rule)
    db.commit()
    return success_response(message="删除成功")


@router.post("/calculate", response_model=dict)
def calculate_dose(
    baby_id: int = Query(..., description="宝宝ID"),
    medicine_id: int = Query(..., description="药品ID"),
    db: Session = Depends(get_db)
):
    baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")

    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    from dateutil.relativedelta import relativedelta
    delta = relativedelta(date.today(), baby.birth_date)
    age_months = delta.years * 12 + delta.months

    weight_record = get_latest_weight(db, baby_id)
    weight_kg = weight_record.weight_kg if weight_record else None

    rule = get_matching_dosage_rule(db, medicine_id, age_months, weight_kg)
    if not rule:
        return error_response(code=404, message="未找到匹配的剂量规则，请先为该药品配置剂量规则")

    recommended_dose = calculate_recommended_dose(rule, weight_kg)

    result = {
        "baby_id": baby_id,
        "medicine_id": medicine_id,
        "age_months": age_months,
        "weight_kg": weight_kg,
        "dosage_rule_id": rule.id,
        "recommended_single_dose": recommended_dose,
        "dose_unit": rule.dose_unit,
        "max_single_dose": rule.max_single_dose,
        "daily_max_times": rule.daily_max_times,
        "min_interval_hours": rule.min_interval_hours,
        "course_days": rule.course_days
    }
    return success_response(data=result, message="剂量计算完成")


@router.post("/plans", response_model=dict)
def create_medication_plan(plan: MedicationPlanCreate, db: Session = Depends(get_db)):
    baby = db.query(BabyProfile).filter(BabyProfile.id == plan.baby_id).first()
    if not baby:
        return error_response(code=404, message="宝宝档案不存在")

    medicine = db.query(Medicine).filter(Medicine.id == plan.medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    if plan.dosage_rule_id:
        rule = db.query(MedicineDosageRule).filter(MedicineDosageRule.id == plan.dosage_rule_id).first()
        if not rule:
            return error_response(code=404, message="剂量规则不存在")

    db_plan = MedicationPlan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return success_response(
        data=MedicationPlanOut.model_validate(db_plan).model_dump(),
        message="用药计划创建成功"
    )


@router.post("/plans/generate", response_model=dict)
def generate_plan(
    baby_id: int = Query(..., description="宝宝ID"),
    medicine_id: int = Query(..., description="药品ID"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    notes: Optional[str] = Query(None, description="备注"),
    db: Session = Depends(get_db)
):
    plan = generate_medication_plan(db, baby_id, medicine_id, start_date=start_date, notes=notes)
    if not plan:
        return error_response(code=404, message="无法生成用药计划，请检查宝宝档案和药品剂量规则")

    return success_response(
        data=MedicationPlanOut.model_validate(plan).model_dump(),
        message="用药计划自动生成成功"
    )


@router.get("/plans", response_model=dict)
def list_medication_plans(
    baby_id: Optional[int] = Query(None, description="宝宝ID"),
    medicine_id: Optional[int] = Query(None, description="药品ID"),
    status: Optional[str] = Query(None, description="计划状态"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(MedicationPlan)
    if baby_id:
        query = query.filter(MedicationPlan.baby_id == baby_id)
    if medicine_id:
        query = query.filter(MedicationPlan.medicine_id == medicine_id)
    if status:
        query = query.filter(MedicationPlan.status == status)

    total = query.count()
    items = query.order_by(MedicationPlan.id.desc()).offset(skip).limit(limit).all()

    result_items = []
    for item in items:
        plan_dict = MedicationPlanOut.model_validate(item).model_dump()
        plan_dict["medicine_name"] = item.medicine.name if item.medicine else None
        plan_dict["baby_name"] = item.baby.name if item.baby else None
        result_items.append(plan_dict)

    result = {"total": total, "items": result_items}
    return success_response(data=result, message="查询成功")


@router.get("/plans/{plan_id}", response_model=dict)
def get_medication_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(MedicationPlan).filter(MedicationPlan.id == plan_id).first()
    if not plan:
        return error_response(code=404, message="用药计划不存在")

    plan_dict = MedicationPlanOut.model_validate(plan).model_dump()
    plan_dict["medicine_name"] = plan.medicine.name if plan.medicine else None
    plan_dict["baby_name"] = plan.baby.name if plan.baby else None
    return success_response(data=plan_dict, message="查询成功")


@router.put("/plans/{plan_id}", response_model=dict)
def update_medication_plan(plan_id: int, plan_update: MedicationPlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(MedicationPlan).filter(MedicationPlan.id == plan_id).first()
    if not plan:
        return error_response(code=404, message="用药计划不存在")

    update_data = plan_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)
    return success_response(
        data=MedicationPlanOut.model_validate(plan).model_dump(),
        message="更新成功"
    )


@router.delete("/plans/{plan_id}", response_model=dict)
def delete_medication_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(MedicationPlan).filter(MedicationPlan.id == plan_id).first()
    if not plan:
        return error_response(code=404, message="用药计划不存在")

    db.delete(plan)
    db.commit()
    return success_response(message="删除成功")


@router.post("/check", response_model=dict)
def check_dosage(
    baby_id: int = Query(..., description="宝宝ID"),
    medicine_id: int = Query(..., description="药品ID"),
    dose_value: Optional[float] = Query(None, gt=0, description="实际给药剂量"),
    plan_id: Optional[int] = Query(None, description="用药计划ID"),
    administration_time: Optional[datetime] = Query(None, description="给药时间"),
    db: Session = Depends(get_db)
):
    result = check_dosage_safety(
        db, baby_id, medicine_id,
        dose_value=dose_value,
        administration_time=administration_time,
        plan_id=plan_id
    )
    return success_response(data=result.model_dump(), message="剂量安全校验完成")
