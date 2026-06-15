from datetime import date, timedelta
from typing import List, Optional, Tuple
from app.models import Medicine, BabyProfile
from app.schemas import RiskItem, RiskAssessment


EXPIRING_SOON_DAYS = 30
CRITICAL_EXPIRING_DAYS = 7
LOW_STOCK_RATIO = 0.5
CRITICAL_STOCK_RATIO = 0.2

RISK_LEVEL_LOW = "LOW"
RISK_LEVEL_MEDIUM = "MEDIUM"
RISK_LEVEL_HIGH = "HIGH"
RISK_LEVEL_CRITICAL = "CRITICAL"

ALERT_TYPE_EXPIRY = "EXPIRY"
ALERT_TYPE_POST_OPEN = "POST_OPEN"
ALERT_TYPE_AGE_MISMATCH = "AGE_MISMATCH"
ALERT_TYPE_LOW_STOCK = "LOW_STOCK"


MEDICINE_TYPE_POST_OPEN_RULES = {
    "FEVER": 30,
    "COLD": 30,
    "COUGH": 30,
    "ANTIDIARRHEAL": 30,
    "ANTIBIOTIC": 14,
    "VITAMIN": 90,
    "EXTERNAL": 180,
    "OTHER": 30
}


AGE_RULES = {
    "FEVER": [
        {"min_age": 0, "max_age": 2, "warning": "2个月以下婴儿发热应立即就医，慎用退烧药", "level": RISK_LEVEL_CRITICAL},
        {"min_age": 2, "max_age": 6, "warning": "2-6月龄婴儿需在医生指导下使用退烧药", "level": RISK_LEVEL_HIGH},
        {"min_age": 6, "max_age": 216, "warning": "", "level": RISK_LEVEL_LOW}
    ],
    "COLD": [
        {"min_age": 0, "max_age": 3, "warning": "3个月以下婴儿感冒应及时就医，不建议自行用药", "level": RISK_LEVEL_CRITICAL},
        {"min_age": 3, "max_age": 12, "warning": "1岁以下婴儿使用感冒药需谨慎，建议咨询医生", "level": RISK_LEVEL_HIGH},
        {"min_age": 12, "max_age": 216, "warning": "", "level": RISK_LEVEL_LOW}
    ],
    "COUGH": [
        {"min_age": 0, "max_age": 6, "warning": "6个月以下婴儿咳嗽应就医，不建议自行使用止咳药", "level": RISK_LEVEL_CRITICAL},
        {"min_age": 6, "max_age": 24, "warning": "2岁以下幼儿使用止咳药需在医生指导下进行", "level": RISK_LEVEL_HIGH},
        {"min_age": 24, "max_age": 216, "warning": "", "level": RISK_LEVEL_LOW}
    ],
    "ANTIDIARRHEAL": [
        {"min_age": 0, "max_age": 3, "warning": "3个月以下婴儿腹泻应立即就医", "level": RISK_LEVEL_CRITICAL},
        {"min_age": 3, "max_age": 12, "warning": "1岁以下婴儿腹泻需注意补水，用药需谨慎", "level": RISK_LEVEL_HIGH},
        {"min_age": 12, "max_age": 216, "warning": "", "level": RISK_LEVEL_LOW}
    ],
    "ANTIBIOTIC": [
        {"min_age": 0, "max_age": 216, "warning": "抗生素必须在医生指导下使用，切勿自行用药", "level": RISK_LEVEL_HIGH}
    ],
    "VITAMIN": [
        {"min_age": 0, "max_age": 12, "warning": "婴儿补充维生素需按推荐剂量，避免过量", "level": RISK_LEVEL_LOW},
        {"min_age": 12, "max_age": 216, "warning": "", "level": RISK_LEVEL_LOW}
    ],
    "EXTERNAL": [
        {"min_age": 0, "max_age": 3, "warning": "新生儿使用外用药需特别谨慎，建议咨询医生", "level": RISK_LEVEL_MEDIUM},
        {"min_age": 3, "max_age": 216, "warning": "", "level": RISK_LEVEL_LOW}
    ],
    "OTHER": [
        {"min_age": 0, "max_age": 216, "warning": "请仔细阅读药品说明书，必要时咨询医生", "level": RISK_LEVEL_MEDIUM}
    ]
}


def check_expiry(medicine: Medicine, today: date = None) -> Optional[RiskItem]:
    if today is None:
        today = date.today()

    days_to_expiry = (medicine.expiry_date - today).days

    if days_to_expiry < 0:
        return RiskItem(
            alert_type=ALERT_TYPE_EXPIRY,
            risk_level=RISK_LEVEL_CRITICAL,
            message=f"药品已过期 {abs(days_to_expiry)} 天，严禁使用！请立即丢弃。"
        )
    elif days_to_expiry <= CRITICAL_EXPIRING_DAYS:
        return RiskItem(
            alert_type=ALERT_TYPE_EXPIRY,
            risk_level=RISK_LEVEL_HIGH,
            message=f"药品将在 {days_to_expiry} 天后过期，请尽快使用或更换。"
        )
    elif days_to_expiry <= EXPIRING_SOON_DAYS:
        return RiskItem(
            alert_type=ALERT_TYPE_EXPIRY,
            risk_level=RISK_LEVEL_MEDIUM,
            message=f"药品将在 {days_to_expiry} 天后过期，请注意使用时效。"
        )
    return None


def check_post_open_validity(medicine: Medicine, today: date = None) -> Optional[RiskItem]:
    if not medicine.open_date:
        return None

    if today is None:
        today = date.today()

    post_open_days = (today - medicine.open_date).days

    validity_days = medicine.post_open_validity_days
    if medicine.medicine_type in MEDICINE_TYPE_POST_OPEN_RULES:
        validity_days = MEDICINE_TYPE_POST_OPEN_RULES[medicine.medicine_type]

    if post_open_days > validity_days:
        return RiskItem(
            alert_type=ALERT_TYPE_POST_OPEN,
            risk_level=RISK_LEVEL_CRITICAL,
            message=f"药品已开封 {post_open_days} 天，超过开封后有效期 {validity_days} 天，建议丢弃不再使用。"
        )
    elif post_open_days > validity_days * 0.8:
        remaining = validity_days - post_open_days
        return RiskItem(
            alert_type=ALERT_TYPE_POST_OPEN,
            risk_level=RISK_LEVEL_MEDIUM,
            message=f"药品已开封 {post_open_days} 天，距开封后有效期还有 {remaining} 天，请尽快用完。"
        )
    return None


def check_age_appropriateness(medicine: Medicine, baby: BabyProfile = None, age_months: int = None) -> Optional[RiskItem]:
    if baby:
        from dateutil.relativedelta import relativedelta
        delta = relativedelta(date.today(), baby.birth_date)
        age_months = delta.years * 12 + delta.months
    elif age_months is None:
        return None

    if age_months < medicine.min_age_months:
        return RiskItem(
            alert_type=ALERT_TYPE_AGE_MISMATCH,
            risk_level=RISK_LEVEL_CRITICAL,
            message=f"宝宝月龄 {age_months} 个月，低于药品最低适用月龄 {medicine.min_age_months} 个月，不适用此药品！"
        )
    elif age_months > medicine.max_age_months:
        return RiskItem(
            alert_type=ALERT_TYPE_AGE_MISMATCH,
            risk_level=RISK_LEVEL_HIGH,
            message=f"宝宝月龄 {age_months} 个月，超过药品最高适用月龄 {medicine.max_age_months} 个月，建议更换更适合的药品。"
        )

    type_rules = AGE_RULES.get(medicine.medicine_type, [])
    for rule in type_rules:
        if rule["min_age"] <= age_months < rule["max_age"]:
            if rule["warning"] and rule["level"] != RISK_LEVEL_LOW:
                return RiskItem(
                    alert_type=ALERT_TYPE_AGE_MISMATCH,
                    risk_level=rule["level"],
                    message=rule["warning"]
                )
            break

    return None


def check_stock_level(medicine: Medicine) -> Optional[RiskItem]:
    if medicine.current_stock <= 0:
        return RiskItem(
            alert_type=ALERT_TYPE_LOW_STOCK,
            risk_level=RISK_LEVEL_HIGH,
            message=f"药品库存为 0，已断货，请及时补货！"
        )
    elif medicine.current_stock <= medicine.min_stock * CRITICAL_STOCK_RATIO:
        return RiskItem(
            alert_type=ALERT_TYPE_LOW_STOCK,
            risk_level=RISK_LEVEL_HIGH,
            message=f"药品库存严重不足，当前库存 {medicine.current_stock} {medicine.stock_unit}，请立即补货！"
        )
    elif medicine.current_stock <= medicine.min_stock * LOW_STOCK_RATIO + medicine.min_stock:
        return RiskItem(
            alert_type=ALERT_TYPE_LOW_STOCK,
            risk_level=RISK_LEVEL_MEDIUM,
            message=f"药品库存偏低，当前库存 {medicine.current_stock} {medicine.stock_unit}，建议适时补货。"
        )
    return None


def assess_medicine_risk(
    medicine: Medicine,
    baby: BabyProfile = None,
    age_months: int = None,
    today: date = None
) -> RiskAssessment:
    if today is None:
        today = date.today()

    risks: List[RiskItem] = []

    expiry_risk = check_expiry(medicine, today)
    if expiry_risk:
        risks.append(expiry_risk)

    post_open_risk = check_post_open_validity(medicine, today)
    if post_open_risk:
        risks.append(post_open_risk)

    if baby or age_months is not None:
        age_risk = check_age_appropriateness(medicine, baby, age_months)
        if age_risk:
            risks.append(age_risk)

    stock_risk = check_stock_level(medicine)
    if stock_risk:
        risks.append(stock_risk)

    overall_risk = RISK_LEVEL_LOW
    if risks:
        risk_levels = [r.risk_level for r in risks]
        if RISK_LEVEL_CRITICAL in risk_levels:
            overall_risk = RISK_LEVEL_CRITICAL
        elif RISK_LEVEL_HIGH in risk_levels:
            overall_risk = RISK_LEVEL_HIGH
        elif RISK_LEVEL_MEDIUM in risk_levels:
            overall_risk = RISK_LEVEL_MEDIUM

    advice = generate_advice(overall_risk, risks)

    return RiskAssessment(
        medicine_id=medicine.id,
        medicine_name=medicine.name,
        overall_risk=overall_risk,
        risks=risks,
        advice=advice
    )


def generate_advice(overall_risk: str, risks: List[RiskItem]) -> str:
    if overall_risk == RISK_LEVEL_LOW:
        return "药品状态良好，可正常使用。请定期检查有效期和库存。"

    advice_parts = []

    has_critical = any(r.risk_level == RISK_LEVEL_CRITICAL for r in risks)
    has_expiry = any(r.alert_type == ALERT_TYPE_EXPIRY for r in risks)
    has_post_open = any(r.alert_type == ALERT_TYPE_POST_OPEN for r in risks)
    has_age = any(r.alert_type == ALERT_TYPE_AGE_MISMATCH for r in risks)
    has_stock = any(r.alert_type == ALERT_TYPE_LOW_STOCK for r in risks)

    if has_critical:
        advice_parts.append("【重要警示】存在严重风险，请立即处理！")

    if has_expiry:
        advice_parts.append("【有效期提醒】请检查药品有效期，过期药品严禁使用。临期药品建议优先使用或更换。")

    if has_post_open:
        advice_parts.append("【开封提醒】开封后药品药效会逐渐降低，超过开封有效期的药品建议丢弃。")

    if has_age:
        advice_parts.append("【月龄提醒】请根据宝宝月龄选择合适药品，月龄不匹配时请咨询医生后再用药。")

    if has_stock:
        advice_parts.append("【库存提醒】库存不足，请及时补货，避免需要时无药可用。")

    advice_parts.append("【就医提示】宝宝病情严重或持续不缓解时，请及时就医，切勿自行用药延误治疗。")

    return " ".join(advice_parts)


def get_age_group(months: int) -> str:
    if months < 3:
        return "0-3月"
    elif months < 6:
        return "3-6月"
    elif months < 12:
        return "6-12月"
    elif months < 24:
        return "1-2岁"
    elif months < 36:
        return "2-3岁"
    else:
        return "3岁以上"
