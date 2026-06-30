$env:APP_ENV = if ($env:APP_ENV) { $env:APP_ENV } else { "development" }
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
