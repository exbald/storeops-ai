"""AC39 Live provider probe tests: honesty check on missing credentials vs real connection."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from apps.api.ai.probe import probe_live_gemini


@pytest.mark.asyncio
async def test_probe_without_credentials_reports_blocked():
    with patch.dict(os.environ, {}, clear=True):
        result = await probe_live_gemini()
        assert result["status"] == "blocked"
        assert "Missing GEMINI_API_KEY" in result["reason"]
        assert result.get("live_accepted") is False


@pytest.mark.asyncio
async def test_probe_with_credentials_calls_client():
    mock_response = {"status": "ok", "model": "gemini-2.5-flash", "live_accepted": True}
    with (
        patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}),
        patch("apps.api.ai.probe._execute_probe", new_callable=AsyncMock) as mock_exec,
    ):
        mock_exec.return_value = mock_response
        result = await probe_live_gemini()
        assert result["status"] == "ok"
        assert result["live_accepted"] is True
