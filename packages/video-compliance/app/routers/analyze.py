"""
routers/analyze.py
POST /analyze  — รับไฟล์วีดีโอ + ขั้นตอน → วิเคราะห์ → บันทึก DB (ถ้าพบความผิดปกติ)
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.analyzer import analyze_video
from app.database import get_db
from app.models import AnalysisResponse, ProcedureStepsPayload, ViolationRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["Analyze"])

ALLOWED_MIME = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/webm", "video/mpeg", "video/x-matroska",
}
MAX_FILE_MB = 500


@router.post(
    "",
    response_model=AnalysisResponse,
    summary="อัปโหลดวีดีโอและวิเคราะห์การปฏิบัติตามขั้นตอน",
    description="""
**Request**: multipart/form-data  
- `file`       : ไฟล์วีดีโอ (mp4, mov, avi, webm, mkv)  
- `steps`      : JSON array ของขั้นตอน เช่น `["ล้างมือ","สวมถุงมือ"]`  
- `num_frames` : จำนวน frames ที่จะ sample (default 16, range 4-64)

**Response**: JSON ผลการวิเคราะห์ บันทึก violations ลง SQLite อัตโนมัติ
""",
)
async def analyze_endpoint(
    file: UploadFile = File(..., description="ไฟล์วีดีโอ"),
    steps: str = Form(..., description='JSON array เช่น ["ขั้นตอน 1","ขั้นตอน 2"]'),
    num_frames: int = Form(default=16, ge=4, le=64),
    db: Session = Depends(get_db),
) -> AnalysisResponse:

    # ── Validate MIME ───────────────────────────────────────
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"ไฟล์ประเภท '{content_type}' ไม่รองรับ รองรับเฉพาะ: {', '.join(ALLOWED_MIME)}",
        )

    # ── Parse steps ─────────────────────────────────────────
    try:
        steps_list: list[str] = json.loads(steps)
        if not isinstance(steps_list, list) or not steps_list:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="'steps' ต้องเป็น JSON array ของ string เช่น [\"ขั้นตอน 1\",\"ขั้นตอน 2\"]",
        )

    payload = ProcedureStepsPayload(steps=steps_list, num_frames=num_frames)

    # ── Save upload to temp file ─────────────────────────────
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()

        if len(content) > MAX_FILE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"ไฟล์ขนาดใหญ่เกิน {MAX_FILE_MB} MB",
            )

        tmp.write(content)
        tmp_path = tmp.name

    # ── Analyze ──────────────────────────────────────────────
    try:
        result, b64_frames = await analyze_video(
            video_path=tmp_path,
            payload=payload,
            filename=file.filename or "unknown",
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("analyze_video failed")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการวิเคราะห์: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # ── Write violations to DB ────────────────────────────────
    if not result.is_compliant and result.violations:
        for v in result.violations:
            record = ViolationRecord(
                video_filename=result.video_filename,
                analyzed_at=result.analyzed_at,
                is_compliant=int(result.is_compliant),
                violation_type=v.violation_type,
                step_index=v.step_index,
                step_description=v.description,
                detail=v.detail,
                frame_snapshots=b64_frames[:4],    # เก็บแค่ 4 frames แรกเป็น thumbnail
                full_response={
                    "summary": result.summary,
                    "observation": result.observation,
                    "steps": [s.model_dump() for s in result.steps],
                },
            )
            db.add(record)
        db.commit()
        logger.info(
            "Saved %d violation(s) for '%s'",
            len(result.violations),
            result.video_filename,
        )
    else:
        logger.info("'%s' — compliant, no DB write", result.video_filename)

    return result
