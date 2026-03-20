# Video Compliance API

วิเคราะห์วีดีโอว่าการทำงานเป็นไปตามขั้นตอนที่กำหนดหรือไม่  
ใช้ **Qwen3-VL-2B** ผ่าน Ollama + **FastAPI** + **SQLite**

---

## 🚀 Deploy ด้วย Docker Compose

```bash
# 1. Clone หรือวางไฟล์ทั้งหมดในโฟลเดอร์เดียวกัน
# 2. รัน
docker compose up --build -d

# ดู log
docker compose logs -f api
docker compose logs -f ollama

# Test ollama
curl http://localhost:11434/api/chat -d '{
  "model": "qwen3-vl:2b",
  "messages": [{ "role": "user", "content": "Hello!" }],
  "stream": false
}'


```

> ครั้งแรก Ollama จะดึง model Qwen2.5-VL-3B (~2GB) อัตโนมัติ รอสักครู่

API พร้อมใช้ที่ `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`

---

## 📡 API Endpoints

### POST `/analyze` — วิเคราะห์วีดีโอ

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@../test_api/wash-hand1-480p.mp4;type=video/mp4" \
  -F 'steps=["ประกบฝ่ามือถูกกัน","ประกบฝ่ามือถูซอกนิ้ว","ถูหลังมือและซอกนิ้ว","กำมือและขัดหลังนิ้ว","ขัดฝ่ามือด้วยปลายนิ้ว","ถูนิ้วหัวแม่โป้ง","ถูรอบข้อมือ"]' \
  -F "num_frames=4"

curl -X POST http://localhost:8000/analyze \
  -F "file=@../test_api/wash-hand1-480p.mp4;type=video/mp4" \
  -F 'steps=["ประกบฝ่ามือถูกกัน","กำมือและขัดหลังนิ้ว","ถูรอบข้อมือ"]' \
  -F "num_frames=4"


```
**Response:**
```json
{
  "video_filename": "video.mp4",
  "analyzed_at": "2025-03-19T10:00:00Z",
  "is_compliant": false,
  "summary": "พบว่าผู้ปฏิบัติงานไม่ได้สวมถุงมือก่อนเริ่มงาน",
  "observation": "ควรเพิ่มการตรวจสอบ PPE ก่อนทุกครั้ง",
  "frames_used": 16,
  "steps": [
    { "step_index": 0, "description": "ล้างมือด้วยสบู่", "found": true, "violation_type": null, "detail": "พบการล้างมือในช่วงต้นวีดีโอ" },
    { "step_index": 1, "description": "สวมถุงมือ", "found": false, "violation_type": "missing_step", "detail": "ไม่พบการสวมถุงมือตลอดวีดีโอ" }
  ],
  "violations": [
    { "step_index": 1, "description": "สวมถุงมือ", "found": false, "violation_type": "missing_step", "detail": "ไม่พบการสวมถุงมือตลอดวีดีโอ" }
  ]
}
```
---

### GET `/violations` — รายการความผิดปกติ

```bash
# ทั้งหมด
curl http://localhost:8000/violations

# กรองตามประเภท
curl "http://localhost:8000/violations?violation_type=safety_breach"

# กรองตามชื่อไฟล์ + pagination
curl "http://localhost:8000/violations?filename=factory&skip=0&limit=20"

# กรองตามช่วงวันที่
curl "http://localhost:8000/violations?date_from=2025-01-01T00:00:00&date_to=2025-12-31T23:59:59"
```

---

### GET `/violations/summary` — สถิติแยกประเภท

```bash
curl http://localhost:8000/violations/summary
```

```json
{
  "total_violations": 42,
  "by_type": {
    "missing_step": 18,
    "safety_breach": 12,
    "wrong_order": 7,
    "incomplete_action": 5
  }
}
```

---

### GET `/violations/{id}` — รายการเดี่ยว

```bash
curl http://localhost:8000/violations/1
```

---

### DELETE `/violations/{id}` — ลบรายการ

```bash
curl -X DELETE http://localhost:8000/violations/1
```

---

## ⚙️ Environment Variables

| ตัวแปร | ค่า default | คำอธิบาย |
|--------|------------|-----------|
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL ของ Ollama |
| `OLLAMA_MODEL` | `qwen2.5vl:3b` | ชื่อ model |
| `OLLAMA_TIMEOUT` | `180` | timeout (วินาที) |

---

## 🏷️ ประเภทความผิดปกติ (ViolationType)

| ค่า | ความหมาย |
|-----|----------|
| `missing_step` | ขาดขั้นตอนที่กำหนด |
| `wrong_order` | ทำผิดลำดับ |
| `wrong_method` | วิธีการหรือเครื่องมือไม่ถูกต้อง |
| `safety_breach` | ละเมิดความปลอดภัย |
| `incomplete_action` | ทำไม่ครบ/ทำแค่บางส่วน |
| `unauthorized_action` | กระทำนอกเหนือขั้นตอนที่กำหนด |
| `other` | อื่น ๆ |

---

## 🖥️ รัน local (ไม่ใช้ Docker)

```bash
uv init
uv venv
source .venv/bin/activate
# ติดตั้ง
uv pip install -r requirements.txt
# รัน Ollama แยก แล้ว pull model
ollama pull qwen2.5vl:3b
# Start API
export OLLAMA_BASE_URL=http://localhost:11434
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
