from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models import Medicine, BabyProfile, RiskAlert, BabyMedicineConfig
from app.services.risk_engine import (
    assess_medicine_risk,
    check_expiry,
    check_post_open_validity,
    check_age_appropriateness,
    check_stock_level,
    EXPIRING_SOON_DAYS
)
from app.services.alert_service import sync_alerts_for_medicine, sync_alerts_for_all
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/risk", tags=["风险提醒与监控"])


@router.get("/assess/all", response_model=dict)
def assess_all_medicines(
    baby_id: Optional[int] = Query(None, description="宝宝ID，传了会做月龄适配校验"),
    age_months: Optional[int] = Query(None, description="直接传月龄，优先级低于baby_id"),
    db: Session = Depends(get_db)
):
    baby = None
    if baby_id:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")

    assessments = sync_alerts_for_all(db, baby=baby, age_months=age_months)
    results = [a.model_dump() for a in assessments]
    results.sort(key=lambda x: _risk_priority(x["overall_risk"]))

    return success_response(data=results, message="风险评估完成，告警已同步")


@router.get("/assess/{medicine_id}", response_model=dict)
def assess_single_medicine(
    medicine_id: int,
    baby_id: Optional[int] = Query(None),
    age_months: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    baby = None
    baby_config = None
    if baby_id:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")
        baby_config = db.query(BabyMedicineConfig).filter(
            BabyMedicineConfig.baby_id == baby_id,
            BabyMedicineConfig.medicine_id == medicine_id
        ).first()

    assessment = sync_alerts_for_medicine(
        db, medicine, baby=baby, age_months=age_months, baby_config=baby_config
    )
    return success_response(data=assessment.model_dump(), message="风险评估完成，告警已同步")


@router.get("/expiry-monitor", response_model=dict)
def expiry_monitor(
    days: int = Query(EXPIRING_SOON_DAYS, gt=0, description="临期天数阈值"),
    baby_id: Optional[int] = Query(None, description="宝宝ID，传了会按个性化提醒天数配置"),
    db: Session = Depends(get_db)
):
    from datetime import date, timedelta
    today = date.today()

    medicines = db.query(Medicine).all()
    expiring_soon = []
    expired = []
    post_open_expired = []

    for med in medicines:
        effective_days = days
        if baby_id:
            config = db.query(BabyMedicineConfig).filter(
                BabyMedicineConfig.baby_id == baby_id,
                BabyMedicineConfig.medicine_id == med.id
            ).first()
            if config and config.remind_days_before:
                effective_days = config.remind_days_before

        expiry_risk = check_expiry(med, today, expiring_soon_days=effective_days)
        if expiry_risk:
            days_to_expiry = (med.expiry_date - today).days
            item = {
                "id": med.id,
                "name": med.name,
                "medicine_type": med.medicine_type,
                "expiry_date": med.expiry_date.isoformat(),
                "days_to_expiry": days_to_expiry,
                "risk_level": expiry_risk.risk_level,
                "message": expiry_risk.message
            }
            if baby_id:
                item["baby_id"] = baby_id
                item["remind_days_before"] = effective_days
            if days_to_expiry < 0:
                expired.append(item)
            else:
                expiring_soon.append(item)

        should_check_post_open = True
        if baby_id:
            config = db.query(BabyMedicineConfig).filter(
                BabyMedicineConfig.baby_id == baby_id,
                BabyMedicineConfig.medicine_id == med.id
            ).first()
            if config and not config.enable_open_alert:
                should_check_post_open = False

        if should_check_post_open:
            post_open_risk = check_post_open_validity(med, today)
            if post_open_risk and post_open_risk.risk_level == "CRITICAL":
                post_open_expired.append({
                    "id": med.id,
                    "name": med.name,
                    "medicine_type": med.medicine_type,
                    "open_date": med.open_date.isoformat() if med.open_date else None,
                    "post_open_days": (today - med.open_date).days if med.open_date else 0,
                    "risk_level": post_open_risk.risk_level,
                    "message": post_open_risk.message
                })

    result = {
        "total_medicines": len(medicines),
        "expiring_soon_count": len(expiring_soon),
        "expired_count": len(expired),
        "post_open_expired_count": len(post_open_expired),
        "expiring_soon": expiring_soon,
        "expired": expired,
        "post_open_expired": post_open_expired
    }
    return success_response(data=result, message="有效期监控完成")


@router.get("/age-check/{medicine_id}", response_model=dict)
def age_appropriateness_check(
    medicine_id: int,
    baby_id: Optional[int] = Query(None),
    age_months: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    baby = None
    baby_config = None
    if baby_id:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")
        baby_config = db.query(BabyMedicineConfig).filter(
            BabyMedicineConfig.baby_id == baby_id,
            BabyMedicineConfig.medicine_id == medicine_id
        ).first()
    elif age_months is None:
        return error_response(code=400, message="请提供 baby_id 或 age_months")

    risk = check_age_appropriateness(medicine, baby=baby, age_months=age_months)

    from dateutil.relativedelta import relativedelta
    from datetime import date
    if baby:
        delta = relativedelta(date.today(), baby.birth_date)
        actual_age = delta.years * 12 + delta.months
    else:
        actual_age = age_months

    baby_disabled = None
    if baby_config and baby_config.is_disabled:
        baby_disabled = {
            "is_disabled": True,
            "disable_reason": baby_config.disable_reason,
            "contraindication_tags": baby_config.contraindication_tags,
            "doctor_advice": baby_config.doctor_advice
        }

    result = {
        "medicine_id": medicine.id,
        "medicine_name": medicine.name,
        "medicine_type": medicine.medicine_type,
        "baby_age_months": actual_age,
        "min_age_months": medicine.min_age_months,
        "max_age_months": medicine.max_age_months,
        "is_appropriate": (risk is None or risk.risk_level == "LOW") and not baby_disabled,
        "risk": risk.model_dump() if risk else None,
        "baby_disabled": baby_disabled,
        "advice": _get_age_advice(medicine, actual_age, baby_config)
    }
    return success_response(data=result, message="月龄适配校验完成")


@router.get("/alerts", response_model=dict)
def list_risk_alerts(
    is_read: Optional[bool] = Query(None),
    risk_level: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(RiskAlert)

    if is_read is not None:
        query = query.filter(RiskAlert.is_read == is_read)
    if risk_level:
        query = query.filter(RiskAlert.risk_level == risk_level)

    total = query.count()
    alerts = query.order_by(RiskAlert.created_at.desc()).offset(skip).limit(limit).all()

    result_items = []
    for alert in alerts:
        item = {
            "id": alert.id,
            "medicine_id": alert.medicine_id,
            "medicine_name": alert.medicine.name if alert.medicine else None,
            "alert_type": alert.alert_type,
            "risk_level": alert.risk_level,
            "message": alert.message,
            "is_read": alert.is_read,
            "created_at": alert.created_at.isoformat() if alert.created_at else None
        }
        result_items.append(item)

    result = {
        "total": total,
        "unread_count": query.filter(RiskAlert.is_read == False).count(),
        "items": result_items
    }
    return success_response(data=result, message="查询成功")


@router.put("/alerts/{alert_id}/read", response_model=dict)
def mark_alert_read(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
    if not alert:
        return error_response(code=404, message="告警不存在")

    alert.is_read = True
    db.commit()
    return success_response(message="已标记为已读")


def _risk_priority(risk_level: str) -> int:
    priority = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3
    }
    return priority.get(risk_level, 99)


def _get_age_advice(medicine: Medicine, age_months: int, baby_config=None) -> str:
    from app.services.risk_engine import AGE_RULES

    advice = []

    if baby_config and baby_config.is_disabled:
        advice.append(f"【个性化禁用】该药品对此宝宝已被禁用：{baby_config.disable_reason or '无具体原因'}")
        if baby_config.doctor_advice:
            advice.append(f"【医生建议】{baby_config.doctor_advice}")
        advice.append("用药前请仔细阅读药品说明书，如有疑问请咨询医生。")
        return " ".join(advice)

    type_warning = ""
    type_rules = AGE_RULES.get(medicine.medicine_type, [])
    for rule in type_rules:
        if rule["min_age"] <= age_months < rule["max_age"]:
            type_warning = rule["warning"]
            break

    if age_months < medicine.min_age_months:
        advice.append(f"【不适用】宝宝月龄 {age_months} 个月，低于药品最低适用月龄 {medicine.min_age_months} 个月，请勿使用。")
    elif age_months > medicine.max_age_months:
        advice.append(f"【超龄】宝宝月龄 {age_months} 个月，已超过药品最高适用月龄 {medicine.max_age_months} 个月，建议更换更合适的药品。")
    else:
        if type_warning:
            advice.append(f"【适用但需注意】月龄在药品适用范围内。{type_warning}")
        else:
            advice.append("【适用】月龄在药品适用范围内，可按说明书使用。")

    if baby_config and baby_config.doctor_advice:
        advice.append(f"【医生建议】{baby_config.doctor_advice}")

    advice.append("用药前请仔细阅读药品说明书，如有疑问请咨询医生。")
    return " ".join(advice)
