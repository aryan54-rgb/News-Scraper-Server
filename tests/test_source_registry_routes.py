from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_source_registry_routes_are_in_openapi(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/sources" in paths
    assert "/sources/{source_id}/enable" in paths
    assert "/sources/{source_id}/disable" in paths
    assert "/sources/{source_id}/test" in paths
    assert "/source-types" in paths
    assert "/source-groups" in paths

