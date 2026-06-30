# Infrastructure Structure

This project follows Clean Architecture boundaries. Infrastructure is ready, while business logic and database models are intentionally absent.

## Root

- `app/` - Python application package.
- `tests/` - pytest suites for infrastructure and future modules.
- `migrations/` - Alembic migration environment and generated revisions.
- `scripts/` - local operational scripts.
- `docker/` - Docker-adjacent support files.
- `docs/` - architecture and operational documentation.

## Application Package

- `app/api/` - HTTP routers, request middleware, and API dependencies. Only system endpoints exist now.
- `app/core/` - cross-cutting configuration, logging, Redis, and other process-level infrastructure.
- `app/database/` - SQLAlchemy base, async engine setup, session management, and database health checks.
- `app/repositories/` - repository contracts and future persistence adapters.
- `app/services/` - application service orchestration for future use cases.
- `app/entities/` - domain entities once business modeling begins.
- `app/models/` - SQLAlchemy ORM models once database modeling begins.
- `app/collectors/` - collector interfaces and future collector implementations.
- `app/extraction/` - extraction interfaces and future extraction logic.
- `app/relevance/` - relevance interfaces and future scoring logic.
- `app/classification/` - classification interfaces and future classification logic.
- `app/workers/` - background worker interfaces and runtime helpers.
- `app/scheduler/` - APScheduler creation and future job registration.
- `app/prompts/` - prompt templates and loading utilities for later AI workflows.
- `app/utils/` - shared utility helpers that do not belong to a domain module.

## Runtime Infrastructure

- `app/main.py` creates the FastAPI app, configures logging, installs middleware, registers routers, and manages startup/shutdown resources.
- `app/api/middleware.py` adds request IDs, request logging, and JSON error responses.
- `app/api/routes/system.py` provides `/health`, `/version`, and `/ready`.
- `app/database/session.py` owns async database engine lifecycle and request-scoped sessions.
- `app/core/redis.py` owns async Redis connection pooling.
- `migrations/env.py` configures Alembic against SQLAlchemy metadata without defining models.

## Docker

- `Dockerfile` builds the backend image with Python 3.12 and uv.
- `docker-compose.yml` runs backend, PostgreSQL, and Redis with health checks and persistent volumes.
