video-compliance-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entrypoint
│   ├── models.py            # Pydantic schemas + SQLite models
│   ├── database.py          # SQLite setup
│   ├── analyzer.py          # Qwen2.5-VL via Ollama + frame logic
│   └── routers/
│       ├── __init__.py
│       ├── analyze.py       # POST /analyze  (upload video)
│       └── violations.py    # GET /violations
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
