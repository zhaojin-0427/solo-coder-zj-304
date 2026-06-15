from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import BatchProfile, RecallAnnouncement, Medicine, RiskAlert
from app.schemas import (
    BatchProfileCreate, BatchProfileUpdate, BatchProfileOut,
    RecallAnnouncementCreate, RecallAnnouncementUpdate, RecallAnnouncementOut
)
from app.services.recall_service import (
    check_batch_against_recalls,
    detect_all_recall_hits,
    detect_recall_for_announcement,
    generate_recall_alerts_for_hits,
    get_unhandled_recall_count,
    get_recall_stats_by_manufacturer,
    get_medicine_recall_info,
    check_restock_recall_risk,
    check_medicine_recall_risk
)
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/batch", tags=["批次追踪与召回管理"])


@router.post("/profiles", response_model=dict)
def create_batch_profile(batch: BatchProfileCreate, db: Session = Depends(get_db)):
    medicine = db.query(Medicine).filter(Medicine.id == batch.medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    db_batch = BatchProfile(**batch.model_dump())
    db.add(db_batch)
    db.commit()
    db.refresh(db_batch)

    hits = check_batch_against_recalls(db_batch, db)
    if hits:
        db_batch.is_recalled = True
        db.commit()
        db.refresh(db_batch)

        for hit in hits:
            recall = hit["recall"]
            existing = db.query(RiskAlert).filter(
                RiskAlert.medicine_id == medicine.id,
                RiskAlert.alert_type == "RECALL",
                RiskAlert.is_read == False,
                RiskAlert.message.contains(f"公告编号:{recall.announcement_number or recall.id}")
            ).first()
            if not existing:
                from app.services.risk_engine import RISK_LEVEL_CRITICAL, RISK_LEVEL_HIGH
                risk_level = RISK_LEVEL_CRITICAL if recall.recall_level == "CRITICAL" else RISK_LEVEL_HIGH
                alert = RiskAlert(
                    medicine_id=medicine.id,
                    baby_id=None,
                    alert_type="RECALL",
                    risk_level=risk_level,
                    message=f"药品召回预警：批号 {db_batch.batch_number} 命中召回公告「{recall.title}」(公告编号:{recall.announcement_number or recall.id})，匹配字段:{hit['match_field']}，原因:{recall.recall_reason or '未说明'}",
                    is_read=False
                )
                db.add(alert)
        db.commit()

    return success_response(data=BatchProfileOut.model_validate(db_batch).model_dump(), message="批次档案创建成功")


@router.get("/profiles", response_model=dict)
def list_batch_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    medicine_id: Optional[int] = Query(None, description="按药品ID筛选"),
    is_recalled: Optional[bool] = Query(None, description="是否已命中召回"),
    keyword: Optional[str] = Query(None, description="按批号搜索"),
    db: Session = Depends(get_db)
):
    query = db.query(BatchProfile)

    if medicine_id:
        query = query.filter(BatchProfile.medicine_id == medicine_id)
    if is_recalled is not None:
        query = query.filter(BatchProfile.is_recalled == is_recalled)
    if keyword:
        query = query.filter(BatchProfile.batch_number.contains(keyword))

    total = query.count()
    items = query.order_by(BatchProfile.id.desc()).offset(skip).limit(limit).all()

    result = {
        "total": total,
        "items": [BatchProfileOut.model_validate(item).model_dump() for item in items]
    }
    return success_response(data=result, message="查询成功")


@router.get("/profiles/{batch_id}", response_model=dict)
def get_batch_profile(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(BatchProfile).filter(BatchProfile.id == batch_id).first()
    if not batch:
        return error_response(code=404, message="批次档案不存在")
    return success_response(data=BatchProfileOut.model_validate(batch).model_dump(), message="查询成功")


@router.put("/profiles/{batch_id}", response_model=dict)
def update_batch_profile(batch_id: int, batch: BatchProfileUpdate, db: Session = Depends(get_db)):
    db_batch = db.query(BatchProfile).filter(BatchProfile.id == batch_id).first()
    if not db_batch:
        return error_response(code=404, message="批次档案不存在")

    update_data = batch.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_batch, key, value)

    db.commit()
    db.refresh(db_batch)

    hits = check_batch_against_recalls(db_batch, db)
    new_recalled = len(hits) > 0
    if new_recalled != db_batch.is_recalled:
        db_batch.is_recalled = new_recalled
        db.commit()
        db.refresh(db_batch)

    return success_response(data=BatchProfileOut.model_validate(db_batch).model_dump(), message="更新成功")


@router.delete("/profiles/{batch_id}", response_model=dict)
def delete_batch_profile(batch_id: int, db: Session = Depends(get_db)):
    db_batch = db.query(BatchProfile).filter(BatchProfile.id == batch_id).first()
    if not db_batch:
        return error_response(code=404, message="批次档案不存在")

    db.delete(db_batch)
    db.commit()
    return success_response(message="删除成功")


@router.post("/recalls", response_model=dict)
def create_recall_announcement(recall: RecallAnnouncementCreate, db: Session = Depends(get_db)):
    db_recall = RecallAnnouncement(**recall.model_dump())
    db.add(db_recall)
    db.commit()
    db.refresh(db_recall)

    hits = detect_recall_for_announcement(db_recall.id, db)
    if hits:
        generate_recall_alerts_for_hits(hits, db)

    result = RecallAnnouncementOut.model_validate(db_recall).model_dump()
    result["hit_count"] = len(hits)
    return success_response(data=result, message="召回公告创建成功，已自动检测命中批次")


@router.get("/recalls", response_model=dict)
def list_recall_announcements(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="状态筛选：ACTIVE/CLOSED"),
    recall_level: Optional[str] = Query(None, description="召回等级筛选"),
    keyword: Optional[str] = Query(None, description="标题关键词搜索"),
    db: Session = Depends(get_db)
):
    query = db.query(RecallAnnouncement)

    if status:
        query = query.filter(RecallAnnouncement.status == status)
    if recall_level:
        query = query.filter(RecallAnnouncement.recall_level == recall_level)
    if keyword:
        query = query.filter(RecallAnnouncement.title.contains(keyword))

    total = query.count()
    items = query.order_by(RecallAnnouncement.id.desc()).offset(skip).limit(limit).all()

    result_items = []
    for item in items:
        item_dict = RecallAnnouncementOut.model_validate(item).model_dump()
        hit_count = len(detect_recall_for_announcement(item.id, db))
        item_dict["hit_count"] = hit_count
        result_items.append(item_dict)

    result = {
        "total": total,
        "items": result_items
    }
    return success_response(data=result, message="查询成功")


@router.get("/recalls/{recall_id}", response_model=dict)
def get_recall_announcement(recall_id: int, db: Session = Depends(get_db)):
    recall = db.query(RecallAnnouncement).filter(RecallAnnouncement.id == recall_id).first()
    if not recall:
        return error_response(code=404, message="召回公告不存在")

    result = RecallAnnouncementOut.model_validate(recall).model_dump()
    hits = detect_recall_for_announcement(recall_id, db)
    result["hit_count"] = len(hits)
    result["hits"] = [h.model_dump() for h in hits]
    return success_response(data=result, message="查询成功")


@router.put("/recalls/{recall_id}", response_model=dict)
def update_recall_announcement(recall_id: int, recall: RecallAnnouncementUpdate, db: Session = Depends(get_db)):
    db_recall = db.query(RecallAnnouncement).filter(RecallAnnouncement.id == recall_id).first()
    if not db_recall:
        return error_response(code=404, message="召回公告不存在")

    update_data = recall.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_recall, key, value)

    db.commit()
    db.refresh(db_recall)
    return success_response(data=RecallAnnouncementOut.model_validate(db_recall).model_dump(), message="更新成功")


@router.delete("/recalls/{recall_id}", response_model=dict)
def delete_recall_announcement(recall_id: int, db: Session = Depends(get_db)):
    db_recall = db.query(RecallAnnouncement).filter(RecallAnnouncement.id == recall_id).first()
    if not db_recall:
        return error_response(code=404, message="召回公告不存在")

    db.delete(db_recall)
    db.commit()
    return success_response(message="删除成功")


@router.post("/detect", response_model=dict)
def detect_recall_hits(db: Session = Depends(get_db)):
    hits = detect_all_recall_hits(db)
    if hits:
        generate_recall_alerts_for_hits(hits, db)

    return success_response(
        data={
            "total_hits": len(hits),
            "hits": [h.model_dump() for h in hits]
        },
        message=f"批次命中检测完成，共发现 {len(hits)} 条命中"
    )


@router.post("/detect/{recall_id}", response_model=dict)
def detect_recall_hits_for_announcement(recall_id: int, db: Session = Depends(get_db)):
    recall = db.query(RecallAnnouncement).filter(RecallAnnouncement.id == recall_id).first()
    if not recall:
        return error_response(code=404, message="召回公告不存在")

    hits = detect_recall_for_announcement(recall_id, db)
    if hits:
        generate_recall_alerts_for_hits(hits, db)

    return success_response(
        data={
            "recall_id": recall_id,
            "recall_title": recall.title,
            "total_hits": len(hits),
            "hits": [h.model_dump() for h in hits]
        },
        message=f"命中检测完成，共发现 {len(hits)} 条命中"
    )


@router.get("/hit-medicines", response_model=dict)
def get_hit_medicine_list(db: Session = Depends(get_db)):
    hits = detect_all_recall_hits(db)

    medicine_map = {}
    for hit in hits:
        if hit.medicine_id not in medicine_map:
            medicine_map[hit.medicine_id] = {
                "medicine_id": hit.medicine_id,
                "medicine_name": hit.medicine_name,
                "recalled_batches": [],
                "recall_count": 0
            }
        medicine_map[hit.medicine_id]["recalled_batches"].append({
            "batch_id": hit.batch_id,
            "batch_number": hit.batch_number,
            "recall_id": hit.recall_id,
            "recall_title": hit.recall_title,
            "recall_level": hit.recall_level,
            "match_field": hit.match_field
        })
        medicine_map[hit.medicine_id]["recall_count"] += 1

    result = list(medicine_map.values())
    return success_response(data=result, message="命中药品清单获取成功")


@router.get("/statistics", response_model=dict)
def get_recall_statistics(db: Session = Depends(get_db)):
    total_recalls = db.query(RecallAnnouncement).count()
    active_recalls = db.query(RecallAnnouncement).filter(
        RecallAnnouncement.status == "ACTIVE"
    ).count()
    total_batches = db.query(BatchProfile).count()
    recalled_batches = db.query(BatchProfile).filter(BatchProfile.is_recalled == True).count()
    unhandled_count = get_unhandled_recall_count(db)
    manufacturer_stats = get_recall_stats_by_manufacturer(db)

    result = {
        "total_recall_announcements": total_recalls,
        "active_recall_announcements": active_recalls,
        "total_batches": total_batches,
        "recalled_batches": recalled_batches,
        "unhandled_recall_count": unhandled_count,
        "manufacturer_recall_stats": manufacturer_stats
    }
    return success_response(data=result, message="召回统计数据获取成功")


@router.get("/medicine-recall/{medicine_id}", response_model=dict)
def get_medicine_recall_detail(medicine_id: int, db: Session = Depends(get_db)):
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        return error_response(code=404, message="药品不存在")

    recall_info = get_medicine_recall_info(medicine_id, db)
    if not recall_info:
        return success_response(data={
            "medicine_id": medicine_id,
            "has_recall_risk": False,
            "recalled_batch_count": 0,
            "total_batch_count": 0,
            "unhandled_alert_count": 0,
            "recall_details": []
        }, message="该药品无召回风险")

    return success_response(data=recall_info, message="药品召回风险信息获取成功")
