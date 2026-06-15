from datetime import date
from sqlalchemy.orm import Session
from app.models import Medicine, BabyProfile, RiskAlert
from app.services.risk_engine import (
    assess_medicine_risk,
    RiskAssessment
)


def sync_alerts_for_medicine(
    db: Session,
    medicine: Medicine,
    baby: BabyProfile = None,
    age_months: int = None,
    today: date = None
) -> RiskAssessment:
    if today is None:
        today = date.today()

    assessment = assess_medicine_risk(medicine, baby=baby, age_months=age_months, today=today)

    for risk in assessment.risks:
        existing = db.query(RiskAlert).filter(
            RiskAlert.medicine_id == medicine.id,
            RiskAlert.alert_type == risk.alert_type,
            RiskAlert.risk_level == risk.risk_level,
            RiskAlert.is_read == False
        ).first()

        if not existing:
            alert = RiskAlert(
                medicine_id=medicine.id,
                alert_type=risk.alert_type,
                risk_level=risk.risk_level,
                message=risk.message,
                is_read=False
            )
            db.add(alert)

    db.commit()
    return assessment


def sync_alerts_for_all(
    db: Session,
    baby: BabyProfile = None,
    age_months: int = None
) -> list:
    today = date.today()
    medicines = db.query(Medicine).all()
    results = []

    for med in medicines:
        assessment = sync_alerts_for_medicine(db, med, baby=baby, age_months=age_months, today=today)
        results.append(assessment)

    return results
