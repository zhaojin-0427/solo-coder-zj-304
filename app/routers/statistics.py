from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import date, timedelta
from collections import defaultdict

from app.database import get_db
from app.models import Medicine, RestockRecord, BabyProfile, BabyMedicineConfig
from app.services.risk_engine import (
    check_expiry,
    check_post_open_validity,
    check_age_appropriateness,
    check_stock_level,
    check_baby_disabled,
    check_recall_risk,
    get_age_group,
    EXPIRING_SOON_DAYS,
    RISK_LEVEL_LOW,
    RISK_LEVEL_MEDIUM,
    RISK_LEVEL_HIGH,
    RISK_LEVEL_CRITICAL
)
from app.utils import success_response, error_response, MEDICINE_TYPES

router = APIRouter(prefix="/api/statistics", tags=["统计分析"])


@router.get("/overview", response_model=dict)
def get_statistics_overview(
    baby_id: Optional[int] = Query(None),
    age_months: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    today = date.today()
    medicines = db.query(Medicine).all()
    total = len(medicines)

    expiring_soon_count = 0
    expired_count = 0
    post_open_expired_count = 0
    low_stock_count = 0
    age_mismatch_count = 0

    baby = None
    if baby_id:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")

    for med in medicines:
        baby_config = None
        if baby:
            baby_config = db.query(BabyMedicineConfig).filter(
                BabyMedicineConfig.baby_id == baby.id,
                BabyMedicineConfig.medicine_id == med.id
            ).first()

        expiring_soon_days = EXPIRING_SOON_DAYS
        if baby_config and baby_config.remind_days_before:
            expiring_soon_days = baby_config.remind_days_before

        expiry_risk = check_expiry(med, today, expiring_soon_days=expiring_soon_days)
        if expiry_risk:
            days_to = (med.expiry_date - today).days
            if days_to < 0:
                expired_count += 1
            else:
                expiring_soon_count += 1

        if baby_config is None or baby_config.enable_open_alert:
            post_open_risk = check_post_open_validity(med, today)
            if post_open_risk and post_open_risk.risk_level == RISK_LEVEL_CRITICAL:
                post_open_expired_count += 1

        if baby_config is None or baby_config.enable_stock_alert:
            stock_risk = check_stock_level(med)
            if stock_risk:
                low_stock_count += 1

        if baby or age_months is not None:
            age_risk = check_age_appropriateness(med, baby=baby, age_months=age_months)
            if age_risk and age_risk.risk_level in [RISK_LEVEL_HIGH, RISK_LEVEL_CRITICAL]:
                age_mismatch_count += 1

    avg_turnover = _calculate_avg_turnover(db)
    age_distribution = _get_age_risk_distribution(medicines, baby, age_months)
    high_freq_restock = _get_high_frequency_restock(db)
    baby_disabled_medicines = _get_baby_disabled_medicines(db, baby_id)
    baby_high_risk_alerts = _get_baby_high_risk_alerts(db, baby_id)
    baby_subscription_coverage = _get_baby_subscription_coverage(db, baby_id)

    from app.services.recall_service import get_unhandled_recall_count, get_recall_stats_by_manufacturer
    recall_stats = get_recall_stats_by_manufacturer(db)
    unhandled_recall_count = get_unhandled_recall_count(db)

    result = {
        "total_medicines": total,
        "expiring_soon_count": expiring_soon_count,
        "expired_count": expired_count,
        "post_open_expired_count": post_open_expired_count,
        "low_stock_count": low_stock_count,
        "age_mismatch_count": age_mismatch_count,
        "avg_turnover_cycles": avg_turnover,
        "age_risk_distribution": age_distribution,
        "high_frequency_restock": high_freq_restock,
        "baby_disabled_medicines": baby_disabled_medicines,
        "baby_high_risk_alerts": baby_high_risk_alerts,
        "baby_subscription_coverage": baby_subscription_coverage,
        "unhandled_recall_count": unhandled_recall_count,
        "recall_stats_by_manufacturer": recall_stats
    }
    return success_response(data=result, message="统计数据获取成功")


@router.get("/turnover", response_model=dict)
def get_turnover_cycles(db: Session = Depends(get_db)):
    data = _calculate_avg_turnover(db)
    return success_response(data=data, message="周转周期统计成功")


@router.get("/alerts/summary", response_model=dict)
def get_alert_summary(
    baby_id: Optional[int] = Query(None),
    age_months: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    today = date.today()
    medicines = db.query(Medicine).all()

    baby = None
    if baby_id:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")

    alert_summary = {
        "total_alerts": 0,
        "by_type": {
            "EXPIRY": 0,
            "POST_OPEN": 0,
            "AGE_MISMATCH": 0,
            "LOW_STOCK": 0,
            "RECALL": 0
        },
        "by_level": {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0
        },
        "expiring_7_days": 0,
        "expiring_30_days": 0,
        "expired": 0
    }

    for med in medicines:
        expiry_risk = check_expiry(med, today)
        if expiry_risk:
            alert_summary["total_alerts"] += 1
            alert_summary["by_type"]["EXPIRY"] += 1
            alert_summary["by_level"][expiry_risk.risk_level] += 1

            days_to = (med.expiry_date - today).days
            if days_to < 0:
                alert_summary["expired"] += 1
            elif days_to <= 7:
                alert_summary["expiring_7_days"] += 1
                alert_summary["expiring_30_days"] += 1
            elif days_to <= 30:
                alert_summary["expiring_30_days"] += 1

        post_open_risk = check_post_open_validity(med, today)
        if post_open_risk:
            alert_summary["total_alerts"] += 1
            alert_summary["by_type"]["POST_OPEN"] += 1
            alert_summary["by_level"][post_open_risk.risk_level] += 1

        stock_risk = check_stock_level(med)
        if stock_risk:
            alert_summary["total_alerts"] += 1
            alert_summary["by_type"]["LOW_STOCK"] += 1
            alert_summary["by_level"][stock_risk.risk_level] += 1

        if baby or age_months is not None:
            age_risk = check_age_appropriateness(med, baby=baby, age_months=age_months)
            if age_risk:
                alert_summary["total_alerts"] += 1
                alert_summary["by_type"]["AGE_MISMATCH"] += 1
                alert_summary["by_level"][age_risk.risk_level] += 1

        recall_risk = check_recall_risk(med, db=db)
        if recall_risk:
            alert_summary["total_alerts"] += 1
            alert_summary["by_type"]["RECALL"] += 1
            alert_summary["by_level"][recall_risk.risk_level] += 1

    return success_response(data=alert_summary, message="告警统计成功")


@router.get("/age-distribution", response_model=dict)
def get_age_risk_distribution(
    baby_id: Optional[int] = Query(None),
    age_months: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    medicines = db.query(Medicine).all()

    baby = None
    if baby_id:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")

    data = _get_age_risk_distribution(medicines, baby, age_months)
    return success_response(data=data, message="月龄风险分布统计成功")


@router.get("/high-frequency-restock", response_model=dict)
def get_high_frequency_restock(
    top_n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    data = _get_high_frequency_restock(db, top_n)
    return success_response(data=data, message="高频补货统计成功")


@router.get("/medicine-types", response_model=dict)
def get_medicine_type_stats(db: Session = Depends(get_db)):
    medicines = db.query(Medicine).all()
    type_stats = defaultdict(lambda: {"count": 0, "expiring": 0, "low_stock": 0})

    today = date.today()
    for med in medicines:
        t = med.medicine_type
        type_stats[t]["count"] += 1

        expiry_risk = check_expiry(med, today)
        if expiry_risk:
            type_stats[t]["expiring"] += 1

        stock_risk = check_stock_level(med)
        if stock_risk:
            type_stats[t]["low_stock"] += 1

    result = []
    for type_key, stats in type_stats.items():
        result.append({
            "type": type_key,
            "type_name": MEDICINE_TYPES.get(type_key, type_key),
            "count": stats["count"],
            "expiring_count": stats["expiring"],
            "low_stock_count": stats["low_stock"]
        })

    result.sort(key=lambda x: x["count"], reverse=True)
    return success_response(data=result, message="药品类型统计成功")


def _calculate_avg_turnover(db: Session) -> List[dict]:
    restocks = db.query(RestockRecord).all()

    type_restocks = defaultdict(list)
    for rs in restocks:
        med = db.query(Medicine).filter(Medicine.id == rs.medicine_id).first()
        if med:
            type_restocks[med.medicine_type].append(rs)

    result = []
    for med_type, rs_list in type_restocks.items():
        if len(rs_list) < 2:
            result.append({
                "medicine_type": med_type,
                "medicine_type_name": MEDICINE_TYPES.get(med_type, med_type),
                "avg_turnover_days": 0,
                "sample_count": len(rs_list)
            })
            continue

        rs_list.sort(key=lambda x: x.purchase_date)

        intervals = []
        for i in range(1, len(rs_list)):
            delta = (rs_list[i].purchase_date - rs_list[i - 1].purchase_date).days
            if delta > 0:
                intervals.append(delta)

        if intervals:
            avg_days = sum(intervals) / len(intervals)
        else:
            avg_days = 0

        result.append({
            "medicine_type": med_type,
            "medicine_type_name": MEDICINE_TYPES.get(med_type, med_type),
            "avg_turnover_days": round(avg_days, 1),
            "sample_count": len(rs_list)
        })

    result.sort(key=lambda x: x["avg_turnover_days"])
    return result


def _get_age_risk_distribution(medicines, baby=None, age_months=None):
    age_groups = ["0-3月", "3-6月", "6-12月", "1-2岁", "2-3岁", "3岁以上"]

    if not baby and age_months is None:
        result = []
        for group in age_groups:
            result.append({
                "age_group": group,
                "risk_count": 0,
                "risk_level": "LOW"
            })
        return result

    from dateutil.relativedelta import relativedelta
    if baby:
        delta = relativedelta(date.today(), baby.birth_date)
        actual_age = delta.years * 12 + delta.months
    else:
        actual_age = age_months

    current_group = get_age_group(actual_age)

    result = []
    for group in age_groups:
        risk_count = 0
        risk_level = "LOW"

        if group == current_group:
            for med in medicines:
                age_risk = check_age_appropriateness(med, age_months=_age_group_to_months(group))
                if age_risk and age_risk.risk_level in [RISK_LEVEL_HIGH, RISK_LEVEL_CRITICAL]:
                    risk_count += 1
                    if _risk_priority(age_risk.risk_level) < _risk_priority(risk_level):
                        risk_level = age_risk.risk_level

        result.append({
            "age_group": group,
            "risk_count": risk_count,
            "risk_level": risk_level,
            "is_current": group == current_group
        })

    return result


def _get_high_frequency_restock(db: Session, top_n: int = 10) -> List[dict]:
    from sqlalchemy import func

    results = db.query(
        RestockRecord.medicine_id,
        func.count(RestockRecord.id).label("restock_count"),
        func.sum(RestockRecord.quantity).label("total_quantity")
    ).group_by(RestockRecord.medicine_id).order_by(func.count(RestockRecord.id).desc()).limit(top_n).all()

    data = []
    for med_id, count, total_qty in results:
        med = db.query(Medicine).filter(Medicine.id == med_id).first()
        if med:
            data.append({
                "medicine_id": med.id,
                "medicine_name": med.name,
                "medicine_type": med.medicine_type,
                "medicine_type_name": MEDICINE_TYPES.get(med.medicine_type, med.medicine_type),
                "restock_count": count,
                "total_quantity": float(total_qty) if total_qty else 0
            })

    return data


def _age_group_to_months(group: str) -> int:
    mapping = {
        "0-3月": 1,
        "3-6月": 4,
        "6-12月": 9,
        "1-2岁": 18,
        "2-3岁": 30,
        "3岁以上": 48
    }
    return mapping.get(group, 12)


def _risk_priority(risk_level: str) -> int:
    priority = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3
    }
    return priority.get(risk_level, 99)


def _get_baby_disabled_medicines(db: Session, baby_id: Optional[int] = None) -> List[dict]:
    query = db.query(BabyMedicineConfig).filter(BabyMedicineConfig.is_disabled == True)
    if baby_id:
        query = query.filter(BabyMedicineConfig.baby_id == baby_id)

    configs = query.all()
    baby_map = {}
    for c in configs:
        if c.baby_id not in baby_map:
            baby_map[c.baby_id] = {
                "baby_id": c.baby_id,
                "baby_name": c.baby.name if c.baby else None,
                "disabled_medicines": []
            }
        med_name = c.medicine.name if c.medicine else None
        baby_map[c.baby_id]["disabled_medicines"].append({
            "medicine_id": c.medicine_id,
            "medicine_name": med_name,
            "disable_reason": c.disable_reason,
            "contraindication_tags": c.contraindication_tags,
            "doctor_advice": c.doctor_advice
        })

    result = []
    for bid, data in baby_map.items():
        result.append({
            "baby_id": data["baby_id"],
            "baby_name": data["baby_name"],
            "disabled_medicine_count": len(data["disabled_medicines"]),
            "disabled_medicines": data["disabled_medicines"]
        })
    return result


def _get_baby_high_risk_alerts(db: Session, baby_id: Optional[int] = None) -> List[dict]:
    babies = db.query(BabyProfile).all()
    if baby_id:
        babies = [b for b in babies if b.id == baby_id]

    medicines = db.query(Medicine).all()
    result = []

    for baby in babies:
        high_risk_count = 0
        critical_risk_count = 0

        for med in medicines:
            config = db.query(BabyMedicineConfig).filter(
                BabyMedicineConfig.baby_id == baby.id,
                BabyMedicineConfig.medicine_id == med.id
            ).first()

            disabled_risk = check_baby_disabled(med, config)
            if disabled_risk:
                critical_risk_count += 1
                continue

            from app.services.risk_engine import assess_medicine_risk
            assessment = assess_medicine_risk(med, baby=baby, baby_config=config, db=db)
            if assessment.overall_risk == RISK_LEVEL_CRITICAL:
                critical_risk_count += 1
            elif assessment.overall_risk == RISK_LEVEL_HIGH:
                high_risk_count += 1

        result.append({
            "baby_id": baby.id,
            "baby_name": baby.name,
            "high_risk_alert_count": high_risk_count,
            "critical_risk_alert_count": critical_risk_count
        })

    return result


def _get_baby_subscription_coverage(db: Session, baby_id: Optional[int] = None) -> List[dict]:
    babies = db.query(BabyProfile).all()
    if baby_id:
        babies = [b for b in babies if b.id == baby_id]

    total_medicines = db.query(Medicine).count()
    result = []

    for baby in babies:
        configs = db.query(BabyMedicineConfig).filter(
            BabyMedicineConfig.baby_id == baby.id
        ).all()

        subscribed = len(configs)
        coverage_rate = round(subscribed / total_medicines, 4) if total_medicines > 0 else 0

        result.append({
            "baby_id": baby.id,
            "baby_name": baby.name,
            "total_medicines": total_medicines,
            "subscribed_medicines": subscribed,
            "coverage_rate": coverage_rate
        })

    return result


@router.get("/baby-summary", response_model=dict)
def get_baby_summary(
    baby_id: Optional[int] = Query(None, description="宝宝ID，不传则返回所有宝宝的汇总"),
    db: Session = Depends(get_db)
):
    if baby_id is not None:
        baby = db.query(BabyProfile).filter(BabyProfile.id == baby_id).first()
        if not baby:
            return error_response(code=404, message="宝宝档案不存在")

    baby_disabled = _get_baby_disabled_medicines(db, baby_id)
    baby_risks = _get_baby_high_risk_alerts(db, baby_id)
    baby_coverage = _get_baby_subscription_coverage(db, baby_id)

    result = {
        "baby_disabled_medicines": baby_disabled,
        "baby_high_risk_alerts": baby_risks,
        "baby_subscription_coverage": baby_coverage
    }
    return success_response(data=result, message="宝宝个性化统计汇总获取成功")
