from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from collections import defaultdict

from app.models import RiskAlert, DispositionEvent, BabyProfile, Medicine
from app.schemas import (
    DispositionEventCreate, DispositionEventOut,
    DispositionTimelineItem, OverdueAlertItem, DispositionCloseStats,
    ACTION_TO_STATUS, DISPOSITION_STATUS_PENDING, DISPOSITION_STATUS_IN_PROGRESS,
    DISPOSITION_STATUS_COMPLETED, DISPOSITION_ACTION_COMPLETED,
    REQUIRES_DESCRIPTION_ACTIONS, REQUIRES_DESCRIPTION_ALERT_TYPES,
    OVERDUE_HOURS
)


def _utcnow():
    return datetime.now(timezone.utc)


def _make_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def create_disposition_event(
    db: Session,
    data: DispositionEventCreate
) -> dict:
    alert = db.query(RiskAlert).filter(RiskAlert.id == data.risk_alert_id).first()
    if not alert:
        return None, "风险提醒不存在"

    if alert.disposition_status == DISPOSITION_STATUS_COMPLETED and data.action != DISPOSITION_ACTION_COMPLETED:
        return None, "该提醒已处置完成，不能再提交新的处置动作"

    if data.action == DISPOSITION_ACTION_COMPLETED:
        if alert.alert_type in REQUIRES_DESCRIPTION_ALERT_TYPES:
            events = db.query(DispositionEvent).filter(
                DispositionEvent.risk_alert_id == alert.id
            ).all()
            has_description = any(e.description for e in events) or data.description
            if not has_description:
                return None, f"「{alert.alert_type}」类型风险必须填写处置说明后才能关闭"

    event = DispositionEvent(
        risk_alert_id=data.risk_alert_id,
        baby_id=alert.baby_id,
        medicine_id=alert.medicine_id,
        action=data.action,
        description=data.description,
        attachment_url=data.attachment_url,
        event_time=data.event_time or datetime.utcnow()
    )
    db.add(event)

    new_status = ACTION_TO_STATUS.get(data.action, DISPOSITION_STATUS_IN_PROGRESS)
    alert.disposition_status = new_status

    if not alert.is_read:
        alert.is_read = True

    db.commit()
    db.refresh(event)

    return _enrich_event(event, alert, db), None


def get_timeline(
    db: Session,
    baby_id: Optional[int] = None,
    medicine_id: Optional[int] = None,
    alert_type: Optional[str] = None,
    disposition_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
) -> dict:
    query = db.query(RiskAlert)

    if baby_id is not None:
        query = query.filter(RiskAlert.baby_id == baby_id)
    if alert_type is not None:
        query = query.filter(RiskAlert.alert_type == alert_type)
    if disposition_status is not None:
        query = query.filter(RiskAlert.disposition_status == disposition_status)

    if medicine_id is not None:
        query = query.filter(RiskAlert.medicine_id == medicine_id)

    total = query.count()
    alerts = query.order_by(RiskAlert.created_at.desc()).offset(skip).limit(limit).all()

    items = []
    for alert in alerts:
        events = db.query(DispositionEvent).filter(
            DispositionEvent.risk_alert_id == alert.id
        ).order_by(DispositionEvent.event_time).all()

        event_outs = [_enrich_event(e, alert, db) for e in events]

        item = DispositionTimelineItem(
            risk_alert_id=alert.id,
            medicine_id=alert.medicine_id,
            medicine_name=alert.medicine.name if alert.medicine else None,
            baby_id=alert.baby_id,
            baby_name=alert.baby.name if alert.baby else None,
            alert_type=alert.alert_type,
            risk_level=alert.risk_level,
            message=alert.message,
            disposition_status=alert.disposition_status,
            created_at=alert.created_at,
            events=event_outs
        )
        items.append(item)

    return {"total": total, "items": items}


def get_overdue_alerts(db: Session, skip: int = 0, limit: int = 50) -> dict:
    threshold = datetime.utcnow() - timedelta(hours=OVERDUE_HOURS)

    query = db.query(RiskAlert).filter(
        RiskAlert.disposition_status.in_([DISPOSITION_STATUS_PENDING, DISPOSITION_STATUS_IN_PROGRESS]),
        RiskAlert.created_at < threshold
    )

    total = query.count()
    alerts = query.order_by(RiskAlert.created_at.asc()).offset(skip).limit(limit).all()

    items = []
    for alert in alerts:
        created_aware = _make_aware(alert.created_at)
        overdue_hours = (datetime.now(timezone.utc) - created_aware).total_seconds() / 3600
        item = OverdueAlertItem(
            alert_id=alert.id,
            medicine_id=alert.medicine_id,
            medicine_name=alert.medicine.name if alert.medicine else None,
            baby_id=alert.baby_id,
            baby_name=alert.baby.name if alert.baby else None,
            alert_type=alert.alert_type,
            risk_level=alert.risk_level,
            message=alert.message,
            disposition_status=alert.disposition_status,
            created_at=alert.created_at,
            overdue_hours=round(overdue_hours, 1)
        )
        items.append(item)

    return {"total": total, "overdue_hours_threshold": OVERDUE_HOURS, "items": items}


def get_disposition_stats(db: Session, baby_id: Optional[int] = None) -> DispositionCloseStats:
    query = db.query(RiskAlert)
    if baby_id is not None:
        query = query.filter(RiskAlert.baby_id == baby_id)

    alerts = query.all()

    pending_count = 0
    in_progress_count = 0
    completed_count = 0
    overdue_count = 0
    total_disposition_seconds = 0
    disposition_completed_count = 0

    threshold = datetime.utcnow() - timedelta(hours=OVERDUE_HOURS)

    type_stats = defaultdict(lambda: {"total": 0, "completed": 0})

    for alert in alerts:
        type_stats[alert.alert_type]["total"] += 1

        if alert.disposition_status == DISPOSITION_STATUS_PENDING:
            pending_count += 1
        elif alert.disposition_status == DISPOSITION_STATUS_IN_PROGRESS:
            in_progress_count += 1
        elif alert.disposition_status == DISPOSITION_STATUS_COMPLETED:
            completed_count += 1
            type_stats[alert.alert_type]["completed"] += 1

            completed_event = db.query(DispositionEvent).filter(
                DispositionEvent.risk_alert_id == alert.id,
                DispositionEvent.action == DISPOSITION_ACTION_COMPLETED
            ).order_by(DispositionEvent.event_time.desc()).first()

            if completed_event and alert.created_at:
                event_time = _make_aware(completed_event.event_time)
                alert_time = _make_aware(alert.created_at)
                delta = (event_time - alert_time).total_seconds()
                if delta > 0:
                    total_disposition_seconds += delta
                    disposition_completed_count += 1

        if alert.disposition_status in [DISPOSITION_STATUS_PENDING, DISPOSITION_STATUS_IN_PROGRESS]:
            if alert.created_at and alert.created_at < threshold:
                overdue_count += 1

    avg_disposition_hours = None
    if disposition_completed_count > 0:
        avg_disposition_hours = round(
            (total_disposition_seconds / disposition_completed_count) / 3600, 2
        )

    close_rate_by_type = {}
    for alert_type, stats in type_stats.items():
        rate = round(stats["completed"] / stats["total"], 4) if stats["total"] > 0 else 0
        close_rate_by_type[alert_type] = {
            "total": stats["total"],
            "completed": stats["completed"],
            "close_rate": rate
        }

    baby_overview = _get_baby_disposition_overview(db, baby_id)

    return DispositionCloseStats(
        pending_count=pending_count,
        in_progress_count=in_progress_count,
        completed_count=completed_count,
        overdue_count=overdue_count,
        avg_disposition_hours=avg_disposition_hours,
        close_rate_by_type=close_rate_by_type,
        baby_disposition_overview=baby_overview
    )


def _get_baby_disposition_overview(db: Session, baby_id: Optional[int] = None) -> List[dict]:
    babies = db.query(BabyProfile).all()
    if baby_id is not None:
        babies = [b for b in babies if b.id == baby_id]

    threshold = datetime.utcnow() - timedelta(hours=OVERDUE_HOURS)

    result = []
    for baby in babies:
        alerts = db.query(RiskAlert).filter(RiskAlert.baby_id == baby.id).all()

        pending = sum(1 for a in alerts if a.disposition_status == DISPOSITION_STATUS_PENDING)
        in_progress = sum(1 for a in alerts if a.disposition_status == DISPOSITION_STATUS_IN_PROGRESS)
        completed = sum(1 for a in alerts if a.disposition_status == DISPOSITION_STATUS_COMPLETED)

        overdue = sum(
            1 for a in alerts
            if a.disposition_status in [DISPOSITION_STATUS_PENDING, DISPOSITION_STATUS_IN_PROGRESS]
            and a.created_at and a.created_at < threshold
        )

        close_rate = round(completed / len(alerts), 4) if alerts else 0

        result.append({
            "baby_id": baby.id,
            "baby_name": baby.name,
            "total_alerts": len(alerts),
            "pending_count": pending,
            "in_progress_count": in_progress,
            "completed_count": completed,
            "overdue_count": overdue,
            "close_rate": close_rate
        })

    return result


def _enrich_event(event: DispositionEvent, alert: RiskAlert, db: Session) -> DispositionEventOut:
    medicine_name = None
    if event.medicine_id:
        med = db.query(Medicine).filter(Medicine.id == event.medicine_id).first()
        if med:
            medicine_name = med.name

    baby_name = None
    if event.baby_id:
        baby = db.query(BabyProfile).filter(BabyProfile.id == event.baby_id).first()
        if baby:
            baby_name = baby.name

    return DispositionEventOut(
        id=event.id,
        risk_alert_id=event.risk_alert_id,
        baby_id=event.baby_id,
        medicine_id=event.medicine_id,
        action=event.action,
        description=event.description,
        attachment_url=event.attachment_url,
        event_time=event.event_time,
        created_at=event.created_at,
        medicine_name=medicine_name,
        baby_name=baby_name,
        alert_type=alert.alert_type if alert else None,
        disposition_status=alert.disposition_status if alert else None
    )
