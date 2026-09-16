import pytest
from storeops_contracts.models import Health


@pytest.mark.asyncio
async def test_get_health(api_client):
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()

    # Validate against frozen Health schema
    health = Health.model_validate(data)
    assert health.status.value == "READY"
    assert health.profile.value == "LOCAL"
    assert health.ai_mode.value in ["STUB", "LIVE"]
    assert "X-Request-Id" in response.headers
