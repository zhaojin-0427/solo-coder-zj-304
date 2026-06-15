from datetime import date
from sqlalchemy.orm import Session
from app.models import Medicine, BabyProfile, RiskAlert, BabyMedicineConfig
from app.services.risk_engine import (
    assess_medicine_risk,
    RiskAssessment
)


def _get_baby_config(db: Session, baby_id: int, medicine_id: int):
    return db.query(BabyMedicineConfig).filter(
        BabyMedicineConfig.baby_id == baby_id,
        BabyMedicineConfig.medicine_id == medicine_id
    ).first()


def sync_alerts_for_medicine(
    db: Session,
    medicine: Medicine,
    baby: BabyProfile = None,
    age_months: int = None,
    today: date = None,
    baby_config: BabyMedicineConfig = None
) -> RiskAssessment:
    if today is None:
        today = date.today()

    assessment = assess_medicine_risk(
        medicine, baby=baby, age_months=age_months, today=today, baby_config=baby_config, db=db
    )

    baby_id = baby.id if baby else None

    for risk in assessment.risks:
        existing = db.query(RiskAlert).filter(
            RiskAlert.medicine_id == medicine.id,
            RiskAlert.baby_id == baby_id,
            RiskAlert.alert_type == risk.alert_type,
            RiskAlert.risk_level == risk.risk_level,
            RiskAlert.is_read == False
        ).first()

        if not existing:
            alert = RiskAlert(
                medicine_id=medicine.id,
                baby_id=baby_id,
                alert_type=risk.alert_type,
                risk_level=risk.risk_level,
                message=risk.message,
                is_read=False,
                disposition_status="PENDING"
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
        baby_config = None
        if baby:
            baby_config = _get_baby_config(db, baby.id, med.id)

        assessment = sync_alerts_for_medicine(
            db, med, baby=baby, age_months=age_months, today=today, baby_config=baby_config
        )
        results.append(assessment)

    return results
