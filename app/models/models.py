from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    medicine_type = Column(String(50), nullable=False)
    applicable_symptoms = Column(Text, nullable=True)
    open_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=False)
    current_stock = Column(Float, nullable=False, default=0)
    stock_unit = Column(String(20), default="瓶")
    min_stock = Column(Float, nullable=False, default=1)
    min_age_months = Column(Integer, nullable=False, default=0)
    max_age_months = Column(Integer, nullable=False, default=216)
    post_open_validity_days = Column(Integer, nullable=False, default=30)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    medication_records = relationship("MedicationRecord", back_populates="medicine")
    restock_records = relationship("RestockRecord", back_populates="medicine")
    risk_alerts = relationship("RiskAlert", back_populates="medicine")


class BabyProfile(Base):
    __tablename__ = "baby_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    birth_date = Column(Date, nullable=False)
    gender = Column(String(10), nullable=True)
    allergies = Column(Text, nullable=True)
    medical_history = Column(Text, nullable=True)
    current_age_months = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MedicationRecord(Base):
    __tablename__ = "medication_records"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    baby_id = Column(Integer, ForeignKey("baby_profiles.id"), nullable=True)
    dose = Column(String(50), nullable=False)
    administration_time = Column(DateTime(timezone=True), server_default=func.now())
    symptoms = Column(Text, nullable=True)
    reaction = Column(Text, nullable=True)
    administered_by = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicine = relationship("Medicine", back_populates="medication_records")


class RestockRecord(Base):
    __tablename__ = "restock_records"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    purchase_date = Column(Date, nullable=False)
    purchase_price = Column(Float, nullable=True)
    supplier = Column(String(100), nullable=True)
    batch_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicine = relationship("Medicine", back_populates="restock_records")


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    risk_level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicine = relationship("Medicine", back_populates="risk_alerts")


class BabyMedicineConfig(Base):
    __tablename__ = "baby_medicine_configs"

    id = Column(Integer, primary_key=True, index=True)
    baby_id = Column(Integer, ForeignKey("baby_profiles.id"), nullable=False, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False, index=True)
    is_disabled = Column(Boolean, default=False, nullable=False)
    disable_reason = Column(Text, nullable=True)
    doctor_advice = Column(Text, nullable=True)
    contraindication_tags = Column(Text, nullable=True)
    remind_days_before = Column(Integer, default=7, nullable=False)
    enable_stock_alert = Column(Boolean, default=True, nullable=False)
    enable_open_alert = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    baby = relationship("BabyProfile", backref="medicine_configs")
    medicine = relationship("Medicine", backref="baby_configs")
