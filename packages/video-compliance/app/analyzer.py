"""
analyzer.py
  - สุ่ม sample frames จากวีดีโอด้วย PyAV
  - เรียก Ollama (Qwen2.5-VL-3B) ด้วย multimodal message
  - parse JSON response แล้วคืน AnalysisResponse
"""

from __future__ import annotations
import ollama
from openai import OpenAI
import base64
import io
import json
import logging
import os
import re
from pathlib import Path

import av
import httpx
import numpy as np
from PIL import Image

from app.models import (
    AnalysisResponse,
    ProcedureStepsPayload,
    StepResult,
    ViolationType,
)

openAiClient = OpenAI(base_url="http://localhost:11434/v1",api_key="ollama")
logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b")
OLLAMA_TIMEOUT  = float(os.getenv("OLLAMA_TIMEOUT", "180"))


# ─────────────────────────────────────────────────────────────
# Frame Extraction
# ─────────────────────────────────────────────────────────────

def extract_frames(video_path: str | Path, num_frames: int = 16) -> list[Image.Image]:
    """
    ดึง `num_frames` frames จากวีดีโอ โดยกระจายสม่ำเสมอตลอดคลิป
    คืน list[PIL.Image]
    """
    container = av.open(str(video_path))
    stream = container.streams.video[0]

    # นับ frame จาก metadata ก่อน ถ้าไม่มีให้ scan
    total = stream.frames
    if not total:
        total = sum(1 for _ in container.decode(video=0))
        container.seek(0)

    total = max(total, 1)
    indices = set(np.linspace(0, total - 1, num=min(num_frames, total), dtype=int).tolist())

    frames: list[Image.Image] = []
    for idx, frame in enumerate(container.decode(video=0)):
        if idx in indices:
            frames.append(frame.to_image())
        if len(frames) >= num_frames:
            break

    container.close()
    logger.info("Extracted %d frames from %s", len(frames), video_path)
    return frames


def frames_to_base64(frames: list[Image.Image], max_size: tuple[int, int] = (640, 480)) -> list[str]:
    """แปลง PIL.Image เป็น base64 JPEG string (ลด size เพื่อประหยัด VRAM)"""
    results = []
    for img in frames:
        img.thumbnail(max_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        results.append(base64.b64encode(buf.getvalue()).decode())
    return results


# ─────────────────────────────────────────────────────────────
# Prompt Builder
# ─────────────────────────────────────────────────────────────

VIOLATION_TYPES_DESC = """
ประเภทความผิดปกติ (violation_type):
- "missing_step"        : ขาดขั้นตอนที่กำหนด ไม่ได้ทำเลย
- "wrong_order"         : ทำผิดลำดับ
- "wrong_method"        : วิธีการหรือเครื่องมือไม่ถูกต้อง
- "safety_breach"       : ละเมิดความปลอดภัย (ไม่สวม PPE, กระทำอันตราย)
- "incomplete_action"   : ทำไม่ครบ/ทำแค่บางส่วน
- "unauthorized_action" : กระทำนอกเหนือขั้นตอนที่กำหนด
- "other"               : อื่น ๆ
"""

def build_prompt(steps: list[str]) -> str:
    steps_json = json.dumps(
        [{"index": i, "description": s} for i, s in enumerate(steps)],
        ensure_ascii=False,
        indent=2,
    )

    return f"""คุณเป็นผู้ตรวจสอบขั้นตอนการปฏิบัติงาน (Procedure Compliance Inspector)
วิเคราะห์ภาพวีดีโอที่ให้มา (หลาย frame ตามลำดับเวลา) แล้วตรวจสอบว่าผู้ปฏิบัติงานทำตามขั้นตอนครบถ้วนหรือไม่

{VIOLATION_TYPES_DESC}

ขั้นตอนที่กำหนด:
{steps_json}

ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น โครงสร้างดังนี้:
{{
  "is_compliant": true | false,
  "summary": "สรุปผลการตรวจสอบ 1-2 ประโยค",
  "observation": "ข้อสังเกตเพิ่มเติม",
  "violation_type": null | "missing_step" | "wrong_order" | "wrong_method" | "safety_breach" | "incomplete_action" | "unauthorized_action" | "other",
}}"""


# ─────────────────────────────────────────────────────────────
# OpenAI API Call
# ─────────────────────────────────────────────────────────────

async def call_openai(b64_frames: list[str], prompt: str) -> dict:
    """
    เรียก OpenAI /api/chat ด้วย multimodal message
    คืน dict จาก JSON response
    """
    for idx, b64 in enumerate(b64_frames):
        image_source = {
            "type": "image_url",
                 "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                    }
        }
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    image_source,
                ],
            }
        ],
        "format": "json",               
    }
    with open("payloadOpenAI.json", "w") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)

    response = openAiClient.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    image_source,
                ],
            }
        ],
        max_tokens=300, # Control the response length
        response_format={"type": "json_object"},
        stream=False
    )

    raw_text: str = response["message"]["content"]
    print("Ollama raw response text:", raw_text[:1000])

    # กำจัด markdown fences ถ้ามี
    raw_text = re.sub(r"```json|```", "", raw_text).strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed. raw=%s", raw_text[:500])
        raise ValueError(f"Model returned non-JSON: {raw_text[:200]}") from exc


# ─────────────────────────────────────────────────────────────
# Ollama API Call
# ─────────────────────────────────────────────────────────────

async def call_ollama(b64_frames: list[str], prompt: str) -> dict:
    """
    เรียก Ollama /api/chat ด้วย multimodal message
    คืน dict จาก JSON response
    """


    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": b64_frames,   # Ollama multimodal format
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 2048,
        },
        "format": "json",               # บังคับ Ollama ให้ output JSON
    }


    with open("payload.json", "w") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)

    response = ollama.chat(
        model=OLLAMA_MODEL, # Use a capable model for best results
        messages=payload["messages"],
        stream=False,
        format='json'
    )
    # async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
    #     resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
    #     resp.raise_for_status()
    # data = resp.json()
    # print("Ollama response data:", json.dumps(data, ensure_ascii=False)[:1000])

    raw_text: str = response["message"]["content"]
    print("Ollama raw response text:", raw_text[:1000])

    # กำจัด markdown fences ถ้ามี
    raw_text = re.sub(r"```json|```", "", raw_text).strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed. raw=%s", raw_text[:500])
        raise ValueError(f"Model returned non-JSON: {raw_text[:200]}") from exc


# ─────────────────────────────────────────────────────────────
# Main analyze function
# ─────────────────────────────────────────────────────────────

async def analyze_video(
    video_path: str | Path,
    payload: ProcedureStepsPayload,
    filename: str,
) -> tuple[AnalysisResponse, list[str]]:
    """
    วิเคราะห์วีดีโอ คืน (AnalysisResponse, list[b64_thumbnails])
    """
    # 1. Extract & encode frames
    frames = extract_frames(video_path, num_frames=payload.num_frames)
    b64_frames = frames_to_base64(frames)

    # 2. Build prompt
    prompt = build_prompt(payload.steps)

    # 3. Call Ollama
    raw: dict = await call_ollama(b64_frames, prompt)
    logger.debug("Ollama raw response: %s", json.dumps(raw, ensure_ascii=False)[:500])

    # 4. Parse response → StepResult list
    step_results: list[StepResult] = []
    for s in raw.get("steps", []):
        vtype = s.get("violation_type")
        step_results.append(
            StepResult(
                step_index=s.get("step_index", 0),
                description=s.get("description", payload.steps[s.get("step_index", 0)]),
                found=bool(s.get("found", True)),
                violation_type=ViolationType(vtype) if vtype else None,
                detail=s.get("detail", ""),
            )
        )

    violations = [sr for sr in step_results if not sr.found]

    from datetime import datetime, timezone
    result = AnalysisResponse(
        video_filename=filename,
        analyzed_at=datetime.now(timezone.utc),
        is_compliant=bool(raw.get("is_compliant", len(violations) == 0)),
        summary=raw.get("summary", ""),
        observation=raw.get("observation", ""),
        steps=step_results,
        violations=violations,
        frames_used=len(frames),
    )

    return result, b64_frames
