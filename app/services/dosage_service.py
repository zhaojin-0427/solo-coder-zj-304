from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy.orm import Session

from app.models import (
    BabyProfile, BabyWeightRecord, MedicineDosageRule,
    MedicationPlan, MedicationRecord, Medicine
)
from app.schemas.schemas import DosageRiskInfo, DosageCheckResult


ALERT_TYPE_SINGLE_OVERDOSE = "SINGLE_OVERDOSE"
ALERT_TYPE_DAILY_OVERDOSE = "DAILY_OVERDOSE"
ALERT_TYPE_INTERVAL_CONFLICT = "INTERVAL_CONFLICT"
ALERT_TYPE_COURSE_EXCEEDED = "COURSE_EXCEEDED"

RISK_LEVEL_LOW = "LOW"
RISK_LEVEL_MEDIUM = "MEDIUM"
RISK_LEVEL_HIGH = "HIGH"
RISK_LEVEL_CRITICAL = "CRITICAL"


def get_latest_weight(db: Session, baby_id: int) -> Optional[BabyWeightRecord]:
    return db.query(BabyWeightRecord).filter(
        BabyWeightRecord.baby_id == baby_id
    ).order_by(BabyWeightRecord.measured_date.desc()).first()


def get_matching_dosage_rule(
    db: Session, medicine_id: int, age_months: int, weight_kg: Optional[float] = None
) -> Optional[MedicineDosageRule]:
    rules = db.query(MedicineDosageRule).filter(
        MedicineDosageRule.medicine_id == medicine_id,
        MedicineDosageRule.min_age_months <= age_months,
        MedicineDosageRule.max_age_months > age_months
    ).all()

    if not rules:
        return None

    if weight_kg is not None:
        for rule in rules:
            if rule.min_weight_kg is not None and weight_kg < rule.min_weight_kg:
                continue
            if rule.max_weight_kg is not None and weight_kg >= rule.max_weight_kg:
                continue
            return rule

    return rules[0]


def calculate_recommended_dose(
    rule: MedicineDosageRule, weight_kg: Optional[float] = None
) -> Optional[float]:
    if rule.dose_per_kg and weight_kg:
        calculated = rule.dose_per_kg * weight_kg
        if rule.max_single_dose:
            calculated = min(calculated, rule.max_single_dose)
        return round(calculated, 2)
    if rule.single_dose:
        return rule.single_dose
    return None


def generate_medication_plan(
    db: Session,
    baby_id: int,
    medicine_id: int,
    start_date: Optional[date] = None,
    notes: Optional[str] = None
) -> Optional[MedicationPlan]:
    baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not baby:
        return None

    from dateutil.relativedelta import relativedelta
    delta = relativedelta(date.today(), baby.birth_date)
    age_months = delta.years * 12 + delta.months

    weight_record = get_latest_weight(db, baby_id)
    weight_kg = weight_record.weight_kg if weight_record else None

    rule = get_matching_dosage_rule(db, medicine_id, age_months, weight_kg)
    if not rule:
        return None

    recommended_dose = calculate_recommended_dose(rule, weight_kg)

    if not start_date:
        start_date = date.today()

    end_date = None
    if rule.course_days:
        end_date = start_date + timedelta(days=rule.course_days)

    plan = MedicationPlan(
        baby_id=baby_id,
        medicine_id=medicine_id,
        dosage_rule_id=rule.id,
        weight_kg=weight_kg,
        recommended_single_dose=recommended_dose,
        dose_unit=rule.dose_unit,
        daily_times=rule.daily_max_times,
        min_interval_hours=rule.min_interval_hours,
        course_days=rule.course_days,
        start_date=start_date,
        end_date=end_date,
        status="ACTIVE",
        notes=notes
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def check_dosage_safety(
    db: Session,
    baby_id: int,
    medicine_id: int,
    dose_value: Optional[float] = None,
    administration_time: Optional[datetime] = None,
    plan_id: Optional[int] = None
) -> DosageCheckResult:
    risks: List[DosageRiskInfo] = []

    baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
    if not baby:
        return DosageCheckResult(
            baby_id=baby_id, medicine_id=medicine_id,
            risks=[DosageRiskInfo(
                risk_type="NO_BABY", risk_level=RISK_LEVEL_CRITICAL,
                message="宝宝档案不存在"
            )],
            is_safe=False
        )

    from dateutil.relativedelta import relativedelta
    delta = relativedelta(date.today(), baby.birth_date)
    age_months = delta.years * 12 + delta.months

    weight_record = get_latest_weight(db, baby_id)
    weight_kg = weight_record.weight_kg if weight_record else None

    rule = get_matching_dosage_rule(db, medicine_id, age_months, weight_kg)
    plan = None
    if plan_id:
        plan = db.query(MedicationPlan).filter(MedicationPlan.id == plan_id).first()

    if not plan and not rule:
        return DosageCheckResult(
            baby_id=baby_id, medicine_id=medicine_id,
            risks=[DosageRiskInfo(
                risk_type="NO_RULE", risk_level=RISK_LEVEL_MEDIUM,
                message="未找到匹配的剂量规则，请手动确认剂量"
            )],
            is_safe=True
        )

    recommended_dose = None
    dose_unit = None
    max_single_dose = None
    daily_max_times = None
    min_interval_hours = None
    course_days = None
    start_date = None

    if plan:
        recommended_dose = plan.recommended_single_dose
        dose_unit = plan.dose_unit
        daily_max_times = plan.daily_times
        min_interval_hours = plan.min_interval_hours
        course_days = plan.course_days
        start_date = plan.start_date
    elif rule:
        recommended_dose = calculate_recommended_dose(rule, weight_kg)
        dose_unit = rule.dose_unit
        max_single_dose = rule.max_single_dose
        daily_max_times = rule.daily_max_times
        min_interval_hours = rule.min_interval_hours
        course_days = rule.course_days

    if administration_time is None:
        administration_time = datetime.now(timezone.utc)

    if dose_value is not None and recommended_dose is not None:
        upper_limit = max_single_dose or recommended_dose * 1.5
        if dose_value > upper_limit:
            risks.append(DosageRiskInfo(
                risk_type=ALERT_TYPE_SINGLE_OVERDOSE,
                risk_level=RISK_LEVEL_HIGH,
                message=f"单次剂量 {dose_value}{dose_unit} 超过安全上限 {upper_limit}{dose_unit}，存在超量风险",
                detail={"dose_value": dose_value, "upper_limit": upper_limit, "dose_unit": dose_unit}
            ))
        elif dose_value > recommended_dose:
            risks.append(DosageRiskInfo(
                risk_type=ALERT_TYPE_SINGLE_OVERDOSE,
                risk_level=RISK_LEVEL_MEDIUM,
                message=f"单次剂量 {dose_value}{dose_unit} 超过推荐剂量 {recommended_dose}{dose_unit}，请注意观察",
                detail={"dose_value": dose_value, "recommended_dose": recommended_dose, "dose_unit": dose_unit}
            ))

    if daily_max_times is not None:
        window_start = administration_time - timedelta(hours=24)
        recent_records = db.query(MedicationRecord).filter(
            MedicationRecord.baby_id == baby_id,
            MedicationRecord.medicine_id == medicine_id,
            MedicationRecord.administration_time >= window_start,
            MedicationRecord.administration_time < administration_time
        ).all()

        count_24h = len(recent_records) + 1
        if count_24h > daily_max_times:
            risks.append(DosageRiskInfo(
                risk_type=ALERT_TYPE_DAILY_OVERDOSE,
                risk_level=RISK_LEVEL_HIGH,
                message=f"24小时内已给药/拟给药 {count_24h} 次，超过每日最大 {daily_max_times} 次",
                detail={"count_24h": count_24h, "daily_max_times": daily_max_times}
            ))
        elif count_24h == daily_max_times:
            risks.append(DosageRiskInfo(
                risk_type=ALERT_TYPE_DAILY_OVERDOSE,
                risk_level=RISK_LEVEL_MEDIUM,
                message=f"24小时内已达到每日最大给药次数 {daily_max_times} 次，请勿再给",
                detail={"count_24h": count_24h, "daily_max_times": daily_max_times}
            ))

    if min_interval_hours is not None:
        last_record = db.query(MedicationRecord).filter(
            MedicationRecord.baby_id == baby_id,
            MedicationRecord.medicine_id == medicine_id,
            MedicationRecord.administration_time < administration_time
        ).order_by(MedicationRecord.administration_time.desc()).first()

        if last_record and last_record.administration_time:
            interval_hours = (administration_time - last_record.administration_time).total_seconds() / 3600
            if interval_hours < min_interval_hours:
                risks.append(DosageRiskInfo(
                    risk_type=ALERT_TYPE_INTERVAL_CONFLICT,
                    risk_level=RISK_LEVEL_HIGH,
                    message=f"距上次给药仅 {round(interval_hours, 1)} 小时，不足最小间隔 {min_interval_hours} 小时",
                    detail={
                        "interval_hours": round(interval_hours, 1),
                        "min_interval_hours": min_interval_hours,
                        "last_time": last_record.administration_time.isoformat()
                    }
                ))
            elif interval_hours < min_interval_hours * 1.2:
                risks.append(DosageRiskInfo(
                    risk_type=ALERT_TYPE_INTERVAL_CONFLICT,
                    risk_level=RISK_LEVEL_MEDIUM,
                    message=f"距上次给药 {round(interval_hours, 1)} 小时，接近最小间隔 {min_interval_hours} 小时，请确认",
                    detail={
                        "interval_hours": round(interval_hours, 1),
                        "min_interval_hours": min_interval_hours,
                        "last_time": last_record.administration_time.isoformat()
                    }
                ))

    if course_days is not None and start_date is not None:
        course_end = start_date + timedelta(days=course_days)
        admin_date = administration_time.date() if hasattr(administration_time, 'date') else administration_time
        if admin_date > course_end:
            risks.append(DosageRiskInfo(
                risk_type=ALERT_TYPE_COURSE_EXCEEDED,
                risk_level=RISK_LEVEL_HIGH,
                message=f"用药已超过疗程 {course_days} 天（疗程结束于 {course_end.isoformat()}），请咨询医生",
                detail={"course_days": course_days, "course_end": course_end.isoformat(), "current_date": admin_date.isoformat()}
            ))
        elif admin_date == course_end:
            risks.append(DosageRiskInfo(
                risk_type=ALERT_TYPE_COURSE_EXCEEDED,
                risk_level=RISK_LEVEL_MEDIUM,
                message=f"今日是疗程最后一天（共 {course_days} 天），请确认是否继续用药",
                detail={"course_days": course_days, "course_end": course_end.isoformat()}
            ))

    is_safe = not any(r.risk_level in [RISK_LEVEL_HIGH, RISK_LEVEL_CRITICAL] for r in risks)

    return DosageCheckResult(
        baby_id=baby_id,
        medicine_id=medicine_id,
        plan_id=plan_id if plan else None,
        recommended_dose=recommended_dose,
        dose_unit=dose_unit,
        risks=risks,
        is_safe=is_safe
    )
