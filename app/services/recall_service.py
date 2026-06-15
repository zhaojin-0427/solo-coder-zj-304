from sqlalchemy.orm import Session
from typing import List, Optional
from collections import defaultdict

from app.models import BatchProfile, RecallAnnouncement, Medicine, RiskAlert, RestockRecord
from app.schemas import RecallHitItem
from app.services.risk_engine import (
    RISK_LEVEL_HIGH,
    RISK_LEVEL_CRITICAL,
    ALERT_TYPE_RECALL
)


def check_batch_against_recalls(batch: BatchProfile, db: Session) -> List[dict]:
    active_recalls = db.query(RecallAnnouncement).filter(
        RecallAnnouncement.status == "ACTIVE"
    ).all()

    hits = []
    for recall in active_recalls:
        match_field = _match_batch(batch, recall)
        if match_field:
            hits.append({
                "recall": recall,
                "match_field": match_field
            })
    return hits


def check_medicine_recall_risk(medicine: Medicine, db: Session) -> List[RiskAlert]:
    batches = db.query(BatchProfile).filter(
        BatchProfile.medicine_id == medicine.id
    ).all()

    alerts = []
    for batch in batches:
        hits = check_batch_against_recalls(batch, db)
        for hit in hits:
            recall = hit["recall"]
            match_field = hit["match_field"]

            existing = db.query(RiskAlert).filter(
                RiskAlert.medicine_id == medicine.id,
                RiskAlert.alert_type == ALERT_TYPE_RECALL,
                RiskAlert.is_read == False,
                RiskAlert.message.contains(f"公告编号:{recall.announcement_number or recall.id}")
            ).first()

            if not existing:
                risk_level = RISK_LEVEL_CRITICAL if recall.recall_level == "CRITICAL" else RISK_LEVEL_HIGH
                alert = RiskAlert(
                    medicine_id=medicine.id,
                    baby_id=None,
                    alert_type=ALERT_TYPE_RECALL,
                    risk_level=risk_level,
                    message=f"药品召回预警：批号 {batch.batch_number} 命中召回公告「{recall.title}」(公告编号:{recall.announcement_number or recall.id})，匹配字段:{match_field}，原因:{recall.recall_reason or '未说明'}",
                    is_read=False,
                    disposition_status="PENDING"
                )
                db.add(alert)
                alerts.append(alert)

            if not batch.is_recalled:
                batch.is_recalled = True

    if alerts:
        db.commit()

    return alerts


def detect_all_recall_hits(db: Session) -> List[RecallHitItem]:
    batches = db.query(BatchProfile).all()
    hits = []

    for batch in batches:
        batch_hits = check_batch_against_recalls(batch, db)
        medicine = db.query(Medicine).filter(Medicine.id == batch.medicine_id).first()
        if not medicine:
            continue

        for hit in batch_hits:
            recall = hit["recall"]
            hits.append(RecallHitItem(
                batch_id=batch.id,
                batch_number=batch.batch_number,
                medicine_id=medicine.id,
                medicine_name=medicine.name,
                manufacturer=batch.manufacturer,
                approval_number=batch.approval_number,
                recall_id=recall.id,
                recall_title=recall.title,
                recall_level=recall.recall_level,
                recall_reason=recall.recall_reason,
                match_field=hit["match_field"]
            ))

    return hits


def detect_recall_for_announcement(recall_id: int, db: Session) -> List[RecallHitItem]:
    recall = db.query(RecallAnnouncement).filter(RecallAnnouncement.id == recall_id).first()
    if not recall or recall.status != "ACTIVE":
        return []

    batches = db.query(BatchProfile).all()
    hits = []

    for batch in batches:
        match_field = _match_batch(batch, recall)
        if match_field:
            medicine = db.query(Medicine).filter(Medicine.id == batch.medicine_id).first()
            if not medicine:
                continue

            hits.append(RecallHitItem(
                batch_id=batch.id,
                batch_number=batch.batch_number,
                medicine_id=medicine.id,
                medicine_name=medicine.name,
                manufacturer=batch.manufacturer,
                approval_number=batch.approval_number,
                recall_id=recall.id,
                recall_title=recall.title,
                recall_level=recall.recall_level,
                recall_reason=recall.recall_reason,
                match_field=match_field
            ))

    return hits


def generate_recall_alerts_for_hits(hits: List[RecallHitItem], db: Session):
    for hit in hits:
        existing = db.query(RiskAlert).filter(
            RiskAlert.medicine_id == hit.medicine_id,
            RiskAlert.alert_type == ALERT_TYPE_RECALL,
            RiskAlert.is_read == False,
            RiskAlert.message.contains(f"公告编号:{hit.recall_id}")
        ).first()

        if not existing:
            risk_level = RISK_LEVEL_CRITICAL if hit.recall_level == "CRITICAL" else RISK_LEVEL_HIGH
            alert = RiskAlert(
                medicine_id=hit.medicine_id,
                baby_id=None,
                alert_type=ALERT_TYPE_RECALL,
                risk_level=risk_level,
                message=f"药品召回预警：批号 {hit.batch_number} 命中召回公告「{hit.recall_title}」(公告编号:{hit.recall_id})，匹配字段:{hit.match_field}，原因:{hit.recall_reason or '未说明'}",
                is_read=False,
                disposition_status="PENDING"
            )
            db.add(alert)

        batch = db.query(BatchProfile).filter(BatchProfile.id == hit.batch_id).first()
        if batch and not batch.is_recalled:
            batch.is_recalled = True

    db.commit()


def get_unhandled_recall_count(db: Session) -> int:
    return db.query(RiskAlert).filter(
        RiskAlert.alert_type == ALERT_TYPE_RECALL,
        RiskAlert.is_read == False
    ).count()


def get_recall_stats_by_manufacturer(db: Session) -> List[dict]:
    batches = db.query(BatchProfile).filter(BatchProfile.is_recalled == True).all()

    manufacturer_map = defaultdict(lambda: {
        "recall_count": 0,
        "medicine_ids": set(),
        "batch_count": 0
    })

    active_recalls = db.query(RecallAnnouncement).filter(
        RecallAnnouncement.status == "ACTIVE"
    ).all()
    recall_manufacturers = set()
    for r in active_recalls:
        if r.match_manufacturer:
            recall_manufacturers.add(r.match_manufacturer)

    for batch in batches:
        mfr = batch.manufacturer or "未知厂家"
        manufacturer_map[mfr]["batch_count"] += 1
        manufacturer_map[mfr]["medicine_ids"].add(batch.medicine_id)

    for mfr in recall_manufacturers:
        if mfr not in manufacturer_map:
            manufacturer_map[mfr] = {
                "recall_count": 0,
                "medicine_ids": set(),
                "batch_count": 0
            }

    for r in active_recalls:
        mfr = r.match_manufacturer or "未知厂家"
        if mfr in manufacturer_map:
            manufacturer_map[mfr]["recall_count"] += 1

    result = []
    for mfr, data in manufacturer_map.items():
        result.append({
            "manufacturer": mfr,
            "recall_count": data["recall_count"],
            "affected_medicine_count": len(data["medicine_ids"]),
            "affected_batch_count": data["batch_count"]
        })

    result.sort(key=lambda x: x["affected_batch_count"], reverse=True)
    return result


def get_medicine_recall_info(medicine_id: int, db: Session) -> Optional[dict]:
    batches = db.query(BatchProfile).filter(
        BatchProfile.medicine_id == medicine_id
    ).all()

    recalled_batches = [b for b in batches if b.is_recalled]
    recall_alerts = db.query(RiskAlert).filter(
        RiskAlert.medicine_id == medicine_id,
        RiskAlert.alert_type == ALERT_TYPE_RECALL,
        RiskAlert.is_read == False
    ).all()

    if not recalled_batches and not recall_alerts:
        return None

    recall_details = []
    seen_recall_ids = set()
    for batch in recalled_batches:
        hits = check_batch_against_recalls(batch, db)
        for hit in hits:
            recall = hit["recall"]
            if recall.id not in seen_recall_ids:
                seen_recall_ids.add(recall.id)
                recall_details.append({
                    "recall_id": recall.id,
                    "title": recall.title,
                    "recall_level": recall.recall_level,
                    "recall_reason": recall.recall_reason,
                    "match_field": hit["match_field"],
                    "batch_number": batch.batch_number
                })

    return {
        "medicine_id": medicine_id,
        "has_recall_risk": True,
        "recalled_batch_count": len(recalled_batches),
        "total_batch_count": len(batches),
        "unhandled_alert_count": len(recall_alerts),
        "recall_details": recall_details
    }


def check_restock_recall_risk(medicine_id: int, batch_number: Optional[str], db: Session) -> Optional[dict]:
    if not batch_number:
        return None

    batch = db.query(BatchProfile).filter(
        BatchProfile.medicine_id == medicine_id,
        BatchProfile.batch_number == batch_number
    ).first()

    if not batch:
        return None

    hits = check_batch_against_recalls(batch, db)
    if not hits:
        return None

    return {
        "has_recall_risk": True,
        "batch_number": batch_number,
        "matched_recalls": [
            {
                "recall_id": h["recall"].id,
                "title": h["recall"].title,
                "recall_level": h["recall"].recall_level,
                "match_field": h["match_field"]
            }
            for h in hits
        ]
    }


def _match_batch(batch: BatchProfile, recall: RecallAnnouncement) -> Optional[str]:
    if recall.match_batch_number and batch.batch_number:
        if batch.batch_number == recall.match_batch_number:
            return "批号"
        if recall.match_batch_number and batch.batch_number.startswith(recall.match_batch_number):
            return "批号(前缀匹配)"

    if recall.match_manufacturer and batch.manufacturer:
        if batch.manufacturer == recall.match_manufacturer:
            return "厂家"

    if recall.match_approval_number and batch.approval_number:
        if batch.approval_number == recall.match_approval_number:
            return "批准文号"

    if recall.match_medicine_name and batch.medicine:
        if batch.medicine.name == recall.match_medicine_name:
            return "药品名称"
        if recall.match_medicine_name and recall.match_medicine_name in batch.medicine.name:
            return "药品名称(模糊匹配)"

    return None
