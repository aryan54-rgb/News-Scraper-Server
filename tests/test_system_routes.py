from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_version(client: AsyncClient) -> None:
    response = await client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "name": "kumbh-monitor",
        "version": "0.1.0",
        "environment": "testing",
    }


@pytest.mark.asyncio
async def test_ready_when_external_services_disabled(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
