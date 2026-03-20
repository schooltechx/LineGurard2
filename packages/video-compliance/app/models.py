"""
models.py — SQLAlchemy ORM table + Pydantic schemas
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum, Integer, JSON, String, Text

from app.database import Base


# ─────────────────────────────────────────────────────────────
# Violation type enum
# ─────────────────────────────────────────────────────────────
class ViolationType(str, enum.Enum):
    MISSING_STEP        = "missing_step"        # ขาดขั้นตอน
    WRONG_ORDER         = "wrong_order"         # ทำผิดลำดับ
    WRONG_METHOD        = "wrong_method"        # วิธีการไม่ถูกต้อง
    SAFETY_BREACH       = "safety_breach"       # ละเมิดความปลอดภัย
    INCOMPLETE_ACTION   = "incomplete_action"   # ทำไม่ครบ
    UNAUTHORIZED_ACTION = "unauthorized_action" # กระทำนอกขอบเขต
    OTHER               = "other"               # อื่น ๆ


# ─────────────────────────────────────────────────────────────
# SQLAlchemy ORM model
# ─────────────────────────────────────────────────────────────
class ViolationRecord(Base):
    __tablename__ = "violations"

    id              = Column(Integer, primary_key=True, index=True)
    video_filename  = Column(String(255), nullable=False)
    analyzed_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_compliant    = Column(Integer, default=0)           # 0 = fail, 1 = pass
    violation_type  = Column(Enum(ViolationType), nullable=True)
    step_index      = Column(Integer, nullable=True)       # ขั้นตอนที่พบปัญหา (0-based)
    step_description= Column(Text, nullable=True)
    detail          = Column(Text, nullable=True)          # คำอธิบายละเอียด
    frame_snapshots = Column(JSON, nullable=True)          # list of base64 thumbnails
    full_response   = Column(JSON, nullable=True)          # raw JSON จาก Ollama


# ─────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────

class StepResult(BaseModel):
    step_index:   int
    description:  str
    found:        bool
    violation_type: ViolationType | None = None
    detail:       str = ""


class AnalysisResponse(BaseModel):
    video_filename:  str
    analyzed_at:     datetime
    is_compliant:    bool
    summary:         str
    steps:           list[StepResult]
    violations:      list[StepResult]          # filtered list ของ steps ที่ไม่ผ่าน
    observation:     str = ""
    frames_used:     int


class ViolationOut(BaseModel):
    id:              int
    video_filename:  str
    analyzed_at:     datetime
    is_compliant:    bool
    violation_type:  ViolationType | None
    step_index:      int | None
    step_description:str | None
    detail:          str | None
    full_response:   Any | None

    model_config = {"from_attributes": True}


class ViolationListResponse(BaseModel):
    total:      int
    items:      list[ViolationOut]


# ─────────────────────────────────────────────────────────────
# Request body schema (procedure steps)
# ─────────────────────────────────────────────────────────────
class ProcedureStepsPayload(BaseModel):
    steps: list[str] = Field(
        ...,
        min_length=1,
        examples=[["ล้างมือ", "สวมถุงมือ", "ตรวจสอบอุปกรณ์"]],
    )
    num_frames: int = Field(default=16, ge=4, le=64)
