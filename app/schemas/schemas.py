from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import Optional, List


class MedicineBase(BaseModel):
    name: str = Field(..., max_length=100, description="药品名称")
    medicine_type: str = Field(..., max_length=50, description="药品类型")
    applicable_symptoms: Optional[str] = Field(None, description="适用症状")
    open_date: Optional[date] = Field(None, description="开封日期")
    expiry_date: date = Field(..., description="有效期至")
    current_stock: float = Field(..., ge=0, description="当前库存")
    stock_unit: str = Field("瓶", max_length=20, description="库存单位")
    min_stock: float = Field(1.0, ge=0, description="最低库存警戒线")
    min_age_months: int = Field(0, ge=0, description="最小适用月龄")
    max_age_months: int = Field(216, ge=0, description="最大适用月龄")
    post_open_validity_days: int = Field(30, gt=0, description="开封后有效天数")
    notes: Optional[str] = Field(None, description="备注")


class MedicineCreate(MedicineBase):
    pass


class MedicineUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    medicine_type: Optional[str] = Field(None, max_length=50)
    applicable_symptoms: Optional[str] = None
    open_date: Optional[date] = None
    expiry_date: Optional[date] = None
    current_stock: Optional[float] = Field(None, ge=0)
    stock_unit: Optional[str] = Field(None, max_length=20)
    min_stock: Optional[float] = Field(None, ge=0)
    min_age_months: Optional[int] = Field(None, ge=0)
    max_age_months: Optional[int] = Field(None, ge=0)
    post_open_validity_days: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = None


class MedicineOut(MedicineBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MedicineList(BaseModel):
    total: int
    items: List[MedicineOut]


class BabyProfileBase(BaseModel):
    name: str = Field(..., max_length=50, description="宝宝姓名")
    birth_date: date = Field(..., description="出生日期")
    gender: Optional[str] = Field(None, max_length=10, description="性别")
    allergies: Optional[str] = Field(None, description="过敏史")
    medical_history: Optional[str] = Field(None, description="病史")

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("出生日期不能晚于今天")
        return v


class BabyProfileCreate(BabyProfileBase):
    pass


class BabyProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    birth_date: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=10)
    allergies: Optional[str] = None
    medical_history: Optional[str] = None

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("出生日期不能晚于今天")
        return v


class BabyProfileOut(BabyProfileBase):
    id: int
    current_age_months: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MedicationRecordBase(BaseModel):
    medicine_id: int = Field(..., description="药品ID")
    baby_id: Optional[int] = Field(None, description="宝宝ID")
    dose: str = Field(..., max_length=50, description="剂量")
    symptoms: Optional[str] = Field(None, description="症状")
    reaction: Optional[str] = Field(None, description="反应")
    administered_by: Optional[str] = Field(None, max_length=50, description="给药人")
    notes: Optional[str] = Field(None, description="备注")


class MedicationRecordCreate(MedicationRecordBase):
    administration_time: Optional[datetime] = Field(None, description="给药时间")


class MedicationRecordOut(MedicationRecordBase):
    id: int
    administration_time: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class RestockRecordBase(BaseModel):
    medicine_id: int = Field(..., description="药品ID")
    quantity: float = Field(..., gt=0, description="补货数量")
    purchase_date: date = Field(..., description="购买日期")
    purchase_price: Optional[float] = Field(None, description="购买价格")
    supplier: Optional[str] = Field(None, max_length=100, description="供应商")
    batch_number: Optional[str] = Field(None, max_length=100, description="批号")
    notes: Optional[str] = Field(None, description="备注")


class RestockRecordCreate(RestockRecordBase):
    pass


class RestockRecordOut(RestockRecordBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class BabyMedicineConfigBase(BaseModel):
    baby_id: int = Field(..., description="宝宝ID")
    medicine_id: int = Field(..., description="药品ID")
    is_disabled: bool = Field(False, description="是否禁用该药品")
    disable_reason: Optional[str] = Field(None, description="禁用原因")
    doctor_advice: Optional[str] = Field(None, description="医生建议备注")
    contraindication_tags: Optional[str] = Field(None, description="用药禁忌标签，多个以逗号分隔")
    remind_days_before: int = Field(7, ge=1, le=90, description="提醒提前天数")
    enable_stock_alert: bool = Field(True, description="是否启用库存提醒")
    enable_open_alert: bool = Field(True, description="是否启用开封提醒")


class BabyMedicineConfigCreate(BabyMedicineConfigBase):
    pass


class BabyMedicineConfigUpdate(BaseModel):
    is_disabled: Optional[bool] = None
    disable_reason: Optional[str] = None
    doctor_advice: Optional[str] = None
    contraindication_tags: Optional[str] = None
    remind_days_before: Optional[int] = Field(None, ge=1, le=90)
    enable_stock_alert: Optional[bool] = None
    enable_open_alert: Optional[bool] = None


class BabyMedicineConfigOut(BabyMedicineConfigBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RiskAlertOut(BaseModel):
    id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    baby_id: Optional[int] = None
    baby_name: Optional[str] = None
    alert_type: str
    risk_level: str
    message: str
    is_read: bool
    disposition_status: str = "PENDING"
    created_at: datetime

    class Config:
        from_attributes = True


class RiskItem(BaseModel):
    alert_type: str
    risk_level: str
    message: str


class RiskAssessment(BaseModel):
    medicine_id: int
    medicine_name: str
    baby_id: Optional[int] = None
    baby_name: Optional[str] = None
    overall_risk: str
    risks: List[RiskItem]
    advice: str
    baby_config: Optional[BabyMedicineConfigOut] = None


class RestockSuggestion(BaseModel):
    medicine_id: int
    medicine_name: str
    medicine_type: str
    current_stock: float
    stock_unit: str
    min_stock: float
    suggested_quantity: float
    reason: str
    urgency: str
    baby_id: Optional[int] = None
    baby_name: Optional[str] = None


class TurnoverCycleItem(BaseModel):
    medicine_type: str
    avg_turnover_days: float
    sample_count: int


class AgeRiskDistributionItem(BaseModel):
    age_group: str
    risk_count: int
    risk_level: str


class HighFrequencyRestockItem(BaseModel):
    medicine_id: int
    medicine_name: str
    medicine_type: str
    restock_count: int
    total_quantity: float


class BabyDisabledMedicineItem(BaseModel):
    baby_id: int
    baby_name: str
    disabled_medicine_count: int
    disabled_medicines: List[dict]


class BabyHighRiskAlertItem(BaseModel):
    baby_id: int
    baby_name: str
    high_risk_alert_count: int
    critical_risk_alert_count: int


class BatchProfileBase(BaseModel):
    medicine_id: int = Field(..., description="药品ID")
    batch_number: str = Field(..., max_length=100, description="生产批号")
    manufacturer: Optional[str] = Field(None, max_length=200, description="生产厂家")
    approval_number: Optional[str] = Field(None, max_length=100, description="批准文号")
    purchase_channel: Optional[str] = Field(None, max_length=200, description="购买渠道")
    batch_notes: Optional[str] = Field(None, description="批次备注")


class BatchProfileCreate(BatchProfileBase):
    pass


class BatchProfileUpdate(BaseModel):
    batch_number: Optional[str] = Field(None, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=200)
    approval_number: Optional[str] = Field(None, max_length=100)
    purchase_channel: Optional[str] = Field(None, max_length=200)
    batch_notes: Optional[str] = None


class BatchProfileOut(BatchProfileBase):
    id: int
    is_recalled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RecallAnnouncementBase(BaseModel):
    announcement_number: Optional[str] = Field(None, max_length=100, description="公告编号")
    title: str = Field(..., max_length=300, description="召回公告标题")
    recall_reason: Optional[str] = Field(None, description="召回原因")
    recall_level: str = Field("HIGH", max_length=20, description="召回等级：HIGH/CRITICAL")
    match_batch_number: Optional[str] = Field(None, max_length=100, description="匹配批号")
    match_manufacturer: Optional[str] = Field(None, max_length=200, description="匹配厂家")
    match_medicine_name: Optional[str] = Field(None, max_length=100, description="匹配药品名称")
    match_approval_number: Optional[str] = Field(None, max_length=100, description="匹配批准文号")
    announcement_date: Optional[date] = Field(None, description="公告日期")
    source: Optional[str] = Field(None, max_length=300, description="公告来源")
    notes: Optional[str] = Field(None, description="备注")


class RecallAnnouncementCreate(RecallAnnouncementBase):
    pass


class RecallAnnouncementUpdate(BaseModel):
    announcement_number: Optional[str] = Field(None, max_length=100)
    title: Optional[str] = Field(None, max_length=300)
    recall_reason: Optional[str] = None
    recall_level: Optional[str] = Field(None, max_length=20)
    match_batch_number: Optional[str] = Field(None, max_length=100)
    match_manufacturer: Optional[str] = Field(None, max_length=200)
    match_medicine_name: Optional[str] = Field(None, max_length=100)
    match_approval_number: Optional[str] = Field(None, max_length=100)
    announcement_date: Optional[date] = None
    source: Optional[str] = Field(None, max_length=300)
    status: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None


class RecallAnnouncementOut(RecallAnnouncementBase):
    id: int
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RecallHitItem(BaseModel):
    batch_id: int
    batch_number: str
    medicine_id: int
    medicine_name: str
    manufacturer: Optional[str] = None
    approval_number: Optional[str] = None
    recall_id: int
    recall_title: str
    recall_level: str
    recall_reason: Optional[str] = None
    match_field: str


class ManufacturerRecallStatItem(BaseModel):
    manufacturer: str
    recall_count: int
    affected_medicine_count: int
    affected_batch_count: int


class BabySubscriptionCoverageItem(BaseModel):
    baby_id: int
    baby_name: str
    total_medicines: int
    subscribed_medicines: int
    coverage_rate: float


class StatisticsData(BaseModel):
    total_medicines: int
    expiring_soon_count: int
    expired_count: int
    post_open_expired_count: int
    low_stock_count: int
    age_mismatch_count: int
    avg_turnover_cycles: List[TurnoverCycleItem]
    age_risk_distribution: List[AgeRiskDistributionItem]
    high_frequency_restock: List[HighFrequencyRestockItem]
    baby_disabled_medicines: List[BabyDisabledMedicineItem] = []
    baby_high_risk_alerts: List[BabyHighRiskAlertItem] = []
    baby_subscription_coverage: List[BabySubscriptionCoverageItem] = []


DISPOSITION_ACTION_PAUSED = "PAUSED"
DISPOSITION_ACTION_CONSULTED = "CONSULTED"
DISPOSITION_ACTION_DISCARDED = "DISCARDED"
DISPOSITION_ACTION_RESTOCKED = "RESTOCKED"
DISPOSITION_ACTION_COMPLETED = "COMPLETED"

DISPOSITION_STATUS_PENDING = "PENDING"
DISPOSITION_STATUS_IN_PROGRESS = "IN_PROGRESS"
DISPOSITION_STATUS_COMPLETED = "COMPLETED"

VALID_DISPOSITION_ACTIONS = [
    DISPOSITION_ACTION_PAUSED,
    DISPOSITION_ACTION_CONSULTED,
    DISPOSITION_ACTION_DISCARDED,
    DISPOSITION_ACTION_RESTOCKED,
    DISPOSITION_ACTION_COMPLETED,
]

ACTION_TO_STATUS = {
    DISPOSITION_ACTION_PAUSED: DISPOSITION_STATUS_IN_PROGRESS,
    DISPOSITION_ACTION_CONSULTED: DISPOSITION_STATUS_IN_PROGRESS,
    DISPOSITION_ACTION_DISCARDED: DISPOSITION_STATUS_IN_PROGRESS,
    DISPOSITION_ACTION_RESTOCKED: DISPOSITION_STATUS_IN_PROGRESS,
    DISPOSITION_ACTION_COMPLETED: DISPOSITION_STATUS_COMPLETED,
}

REQUIRES_DESCRIPTION_ACTIONS = [DISPOSITION_ACTION_COMPLETED]
REQUIRES_DESCRIPTION_ALERT_TYPES = ["RECALL", "BABY_DISABLED"]

OVERDUE_HOURS = 72


class DispositionEventCreate(BaseModel):
    risk_alert_id: int = Field(..., description="关联的风险提醒ID")
    action: str = Field(..., description="处置动作：PAUSED/CONSULTED/DISCARDED/RESTOCKED/COMPLETED")
    description: Optional[str] = Field(None, description="处置说明")
    attachment_url: Optional[str] = Field(None, max_length=500, description="附件链接")
    event_time: Optional[datetime] = Field(None, description="事件时间，不传则为当前时间")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in VALID_DISPOSITION_ACTIONS:
            raise ValueError(f"处置动作必须是以下之一：{', '.join(VALID_DISPOSITION_ACTIONS)}")
        return v


class DispositionEventOut(BaseModel):
    id: int
    risk_alert_id: int
    baby_id: Optional[int] = None
    medicine_id: int
    action: str
    description: Optional[str] = None
    attachment_url: Optional[str] = None
    event_time: datetime
    created_at: datetime
    medicine_name: Optional[str] = None
    baby_name: Optional[str] = None
    alert_type: Optional[str] = None
    disposition_status: Optional[str] = None

    class Config:
        from_attributes = True


class TimelineQueryParams(BaseModel):
    baby_id: Optional[int] = None
    medicine_id: Optional[int] = None
    alert_type: Optional[str] = None
    disposition_status: Optional[str] = None


class DispositionTimelineItem(BaseModel):
    risk_alert_id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    baby_id: Optional[int] = None
    baby_name: Optional[str] = None
    alert_type: str
    risk_level: str
    message: str
    disposition_status: str
    created_at: datetime
    events: List[DispositionEventOut] = []


class OverdueAlertItem(BaseModel):
    alert_id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    baby_id: Optional[int] = None
    baby_name: Optional[str] = None
    alert_type: str
    risk_level: str
    message: str
    disposition_status: str
    created_at: datetime
    overdue_hours: float


class DispositionCloseStats(BaseModel):
    pending_count: int
    in_progress_count: int
    completed_count: int
    overdue_count: int
    avg_disposition_hours: Optional[float] = None
    close_rate_by_type: dict = {}
    baby_disposition_overview: List[dict] = []
