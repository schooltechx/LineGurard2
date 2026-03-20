"""
main.py — FastAPI application entrypoint
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.routers.analyze import router as analyze_router
from app.routers.violations import router as violations_router

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting up — initialising SQLite database …")
    init_db()
    logger.info("✅ Database ready")
    yield
    logger.info("🛑 Shutting down")


app = FastAPI(
    title="Video Compliance API",
    description="""
## วิเคราะห์วีดีโอว่าการทำงานเป็นไปตามขั้นตอนหรือไม่

ใช้ **Qwen3-VL-4B** ผ่าน Ollama สำหรับ multimodal video analysis  
บันทึกความผิดปกติลง **SQLite** พร้อม filter และ pagination

### Endpoints หลัก
| Method | Path | คำอธิบาย |
|--------|------|-----------|
| `POST` | `/analyze` | อัปโหลดวีดีโอ + ขั้นตอน → วิเคราะห์ |
| `GET` | `/violations` | รายการความผิดปกติ |
| `GET` | `/violations/summary` | สถิติแยกตามประเภท |
| `GET` | `/violations/{id}` | รายการเดี่ยว |
| `DELETE` | `/violations/{id}` | ลบรายการ |
""",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(violations_router)


@app.get("/health", tags=["Health"])
async def health():
    """ตรวจสอบสถานะ API"""
    import httpx, os
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ollama_url}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        ollama_ok = False

    return JSONResponse({
        "status": "ok",
        "ollama": "reachable" if ollama_ok else "unreachable",
        "ollama_url": ollama_url,
    })
