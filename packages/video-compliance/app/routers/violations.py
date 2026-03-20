"""
routers/violations.py
GET /violations        — รายการ violations ทั้งหมด (พร้อม filter / pagination)
GET /violations/{id}   — ดูรายการเดี่ยว
DELETE /violations/{id} — ลบรายการ
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ViolationListResponse, ViolationOut, ViolationRecord, ViolationType

router = APIRouter(prefix="/violations", tags=["Violations"])


@router.get(
    "",
    response_model=ViolationListResponse,
    summary="ดูรายการความผิดปกติทั้งหมด",
)
def list_violations(
    violation_type: ViolationType | None = Query(default=None, description="กรองตามประเภท"),
    filename: str | None = Query(default=None, description="กรองตามชื่อไฟล์ (partial match)"),
    date_from: datetime | None = Query(default=None, description="วันที่เริ่มต้น ISO8601"),
    date_to: datetime | None = Query(default=None, description="วันที่สิ้นสุด ISO8601"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ViolationListResponse:

    q = db.query(ViolationRecord)

    if violation_type:
        q = q.filter(ViolationRecord.violation_type == violation_type)
    if filename:
        q = q.filter(ViolationRecord.video_filename.ilike(f"%{filename}%"))
    if date_from:
        q = q.filter(ViolationRecord.analyzed_at >= date_from)
    if date_to:
        q = q.filter(ViolationRecord.analyzed_at <= date_to)

    total = q.count()
    items = q.order_by(ViolationRecord.analyzed_at.desc()).offset(skip).limit(limit).all()

    return ViolationListResponse(
        total=total,
        items=[ViolationOut.model_validate(r) for r in items],
    )


@router.get(
    "/summary",
    summary="สรุปสถิติ violations แยกตามประเภท",
)
def violation_summary(db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import func

    rows = (
        db.query(ViolationRecord.violation_type, func.count().label("count"))
        .group_by(ViolationRecord.violation_type)
        .all()
    )

    total = db.query(ViolationRecord).count()
    by_type = {(r.violation_type.value if r.violation_type else "unknown"): r.count for r in rows}

    return {
        "total_violations": total,
        "by_type": by_type,
    }


@router.get(
    "/{violation_id}",
    response_model=ViolationOut,
    summary="ดูรายการความผิดปกติเดี่ยว",
)
def get_violation(violation_id: int, db: Session = Depends(get_db)) -> ViolationOut:
    record = db.query(ViolationRecord).filter(ViolationRecord.id == violation_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"ไม่พบ violation id={violation_id}")
    return ViolationOut.model_validate(record)


@router.delete(
    "/{violation_id}",
    summary="ลบรายการความผิดปกติ",
    status_code=204,
)
def delete_violation(violation_id: int, db: Session = Depends(get_db)):
    record = db.query(ViolationRecord).filter(ViolationRecord.id == violation_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"ไม่พบ violation id={violation_id}")
    db.delete(record)
    db.commit()