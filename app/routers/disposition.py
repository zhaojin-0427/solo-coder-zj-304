from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.schemas import DispositionEventCreate
from app.services.disposition_service import (
    create_disposition_event,
    get_timeline,
    get_overdue_alerts,
    get_disposition_stats
)
from app.utils import success_response, error_response

router = APIRouter(prefix="/api/disposition", tags=["用药事件时间线与处置闭环"])


@router.post("/events", response_model=dict)
def submit_disposition_event(
    data: DispositionEventCreate,
    db: Session = Depends(get_db)
):
    result, err = create_disposition_event(db, data)
    if err:
        return error_response(code=400, message=err)

    return success_response(data=result.model_dump(), message="处置事件提交成功")


@router.get("/timeline", response_model=dict)
def get_disposition_timeline(
    baby_id: Optional[int] = Query(None, description="按宝宝ID筛选"),
    medicine_id: Optional[int] = Query(None, description="按药品ID筛选"),
    alert_type: Optional[str] = Query(None, description="按风险类型筛选"),
    disposition_status: Optional[str] = Query(None, description="按处置状态筛选：PENDING/IN_PROGRESS/COMPLETED"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    result = get_timeline(
        db,
        baby_id=baby_id,
        medicine_id=medicine_id,
        alert_type=alert_type,
        disposition_status=disposition_status,
        skip=skip,
        limit=limit
    )

    serialized_items = []
    for item in result["items"]:
        item_dict = item.model_dump()
        for ev in item_dict.get("events", []):
            if ev.get("event_time"):
                ev["event_time"] = ev["event_time"].isoformat() if hasattr(ev["event_time"], "isoformat") else ev["event_time"]
            if ev.get("created_at"):
                ev["created_at"] = ev["created_at"].isoformat() if hasattr(ev["created_at"], "isoformat") else ev["created_at"]
        if item_dict.get("created_at"):
            item_dict["created_at"] = item_dict["created_at"].isoformat() if hasattr(item_dict["created_at"], "isoformat") else item_dict["created_at"]
        serialized_items.append(item_dict)

    return success_response(
        data={"total": result["total"], "items": serialized_items},
        message="时间线查询成功"
    )


@router.get("/overdue", response_model=dict)
def get_overdue_disposition_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    result = get_overdue_alerts(db, skip=skip, limit=limit)

    serialized_items = []
    for item in result["items"]:
        item_dict = item.model_dump()
        if item_dict.get("created_at"):
            item_dict["created_at"] = item_dict["created_at"].isoformat() if hasattr(item_dict["created_at"], "isoformat") else item_dict["created_at"]
        serialized_items.append(item_dict)

    return success_response(
        data={
            "total": result["total"],
            "overdue_hours_threshold": result["overdue_hours_threshold"],
            "items": serialized_items
        },
        message="逾期未处理提醒查询成功"
    )


@router.get("/stats", response_model=dict)
def get_disposition_statistics(
    baby_id: Optional[int] = Query(None, description="按宝宝ID筛选统计"),
    db: Session = Depends(get_db)
):
    stats = get_disposition_stats(db, baby_id=baby_id)
    return success_response(data=stats.model_dump(), message="处置闭环统计获取成功")
