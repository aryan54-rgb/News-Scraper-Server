# Kumbh Monitor

Production-ready FastAPI backend foundation for the Kumbh Monitor Intelligence Platform.

## Local Development

```powershell
uv sync --extra dev
Copy-Item .env.example .env
docker compose up postgres redis
uv run uvicorn app.main:app --reload
```

## System Endpoints

- `GET /health`
- `GET /version`
- `GET /ready`

Business endpoints, collectors, classifiers, database models, and domain logic are intentionally not implemented in this foundation.
