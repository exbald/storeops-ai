"""AC39 Model Gateway tests for Google Gen AI integration, schema repair, and error handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from apps.api.ai.gateway import (
    DeterministicModelGateway,
    GeminiGateway,
    ModelQuotaError,
    ModelSchemaError,
    ModelTransientError,
)


class SimpleTarget(BaseModel):
    message: str
    count: int


@pytest.mark.asyncio
async def test_deterministic_gateway_returns_exact_response():
    gateway = DeterministicModelGateway()
    expected = SimpleTarget(message="hello", count=42)
    gateway.register_response(SimpleTarget, expected)

    result = await gateway.generate_structured(
        prompt="Tell me something",
        response_schema=SimpleTarget,
    )
    assert result == expected


@pytest.mark.asyncio
async def test_deterministic_gateway_unregistered_schema_raises():
    gateway = DeterministicModelGateway()
    with pytest.raises(ModelSchemaError):
        await gateway.generate_structured(
            prompt="Tell me something",
            response_schema=SimpleTarget,
        )


@pytest.mark.asyncio
async def test_gemini_gateway_success_parsing():
    gateway = GeminiGateway(api_key="test-key", model_id="gemini-2.5-flash")

    # Mock the underlying client
    mock_response = MagicMock()
    mock_response.text = '{"message": "success", "count": 10}'

    with patch.object(gateway, "_invoke_api", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        result = await gateway.generate_structured(
            prompt="Summarize",
            response_schema=SimpleTarget,
        )
        assert result.message == "success"
        assert result.count == 10
        assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_gemini_gateway_one_shot_repair_success():
    """If first attempt is invalid JSON, gateway attempts one repair before failing."""
    gateway = GeminiGateway(api_key="test-key", model_id="gemini-2.5-flash")

    mock_bad = MagicMock()
    mock_bad.text = '{"message": "missing count"}'  # Missing required field count

    mock_fixed = MagicMock()
    mock_fixed.text = '{"message": "repaired", "count": 5}'

    with patch.object(gateway, "_invoke_api", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [mock_bad, mock_fixed]
        result = await gateway.generate_structured(
            prompt="Summarize",
            response_schema=SimpleTarget,
        )
        assert result.message == "repaired"
        assert result.count == 5
        assert mock_call.call_count == 2  # Original call + 1 repair call


@pytest.mark.asyncio
async def test_gemini_gateway_repair_failure_raises_schema_error():
    """If repair also fails, raises ModelSchemaError (no fallback to fake success)."""
    gateway = GeminiGateway(api_key="test-key", model_id="gemini-2.5-flash")

    mock_bad1 = MagicMock()
    mock_bad1.text = "NOT JSON"

    mock_bad2 = MagicMock()
    mock_bad2.text = "STILL NOT JSON"

    with patch.object(gateway, "_invoke_api", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [mock_bad1, mock_bad2]
        with pytest.raises(ModelSchemaError) as exc_info:
            await gateway.generate_structured(
                prompt="Summarize",
                response_schema=SimpleTarget,
            )
        assert "Schema validation failed after repair" in str(exc_info.value)
        assert mock_call.call_count == 2


@pytest.mark.asyncio
async def test_gemini_gateway_error_mapping():
    gateway = GeminiGateway(api_key="test-key", model_id="gemini-2.5-flash")

    # Quota error (429)
    with patch.object(gateway, "_invoke_api", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("ResourceExhausted: 429 Quota exceeded")
        with pytest.raises(ModelQuotaError):
            await gateway.generate_structured(
                prompt="test", response_schema=SimpleTarget
            )

    # Transient error (503 / unavailable)
    with patch.object(gateway, "_invoke_api", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("ServiceUnavailable: 503 Backend down")
        with pytest.raises(ModelTransientError):
            await gateway.generate_structured(
                prompt="test", response_schema=SimpleTarget
            )


@pytest.mark.asyncio
async def test_gemini_gateway_multimodal_parts_construction():
    gateway = GeminiGateway(api_key="test-key")
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    pdf_bytes = b"%PDF-1.5" + b"\x00" * 20

    parts = gateway._build_multimodal_parts(
        prompt="Analyze media",
        images=[image_bytes],
        pdfs=[pdf_bytes],
    )
    assert len(parts) == 3
    # First part is prompt
    assert parts[0].text == "Analyze media"
    # Second part is image inline data
    assert parts[1].inline_data.mime_type == "image/png"
    # Third part is pdf inline data
    assert parts[2].inline_data.mime_type == "application/pdf"


@pytest.mark.asyncio
async def test_gemini_gateway_system_instruction_extraction():
    gateway = GeminiGateway(api_key="test-key")
    prompt = (
        "<system_instruction>\nYou are a retail audit expert.\n</system_instruction>\n\n"
        "Analyze this store."
    )

    clean_prompt, sys_inst = gateway._extract_system_instruction(prompt)
    assert sys_inst == "You are a retail audit expert."
    assert clean_prompt == "Analyze this store."


def test_gemini_gateway_sanitize_error_masks_credentials():
    from apps.api.ai.gateway import _sanitize_error

    raw = "Request failed: https://generativelanguage.googleapis.com?key=AIzaSyA_testkey123 and token=my-secret-token"
    sanitized = _sanitize_error(raw)
    assert "AIzaSyA_testkey123" not in sanitized
    assert "my-secret-token" not in sanitized
    assert "[MASKED]" in sanitized


@pytest.mark.asyncio
async def test_gemini_gateway_repair_prompt_backtick_escaping():
    gateway = GeminiGateway(api_key="test-key")

    with patch.object(gateway, "_invoke_api", new_callable=AsyncMock) as mock_call:
        # First call returns malformed JSON with internal code fences
        resp1 = MagicMock()
        resp1.text = '```json\n{"broken": true ```something```}\n```'
        # Second call returns fixed valid JSON
        resp2 = MagicMock()
        resp2.text = '{"message": "fixed", "count": 2}'
        mock_call.side_effect = [resp1, resp2]

        result = await gateway.generate_structured(
            prompt="Generate object",
            response_schema=SimpleTarget,
        )
        assert result.message == "fixed"
        assert result.count == 2
        # Check that repair prompt escaped backticks
        call_kwargs = mock_call.call_args_list[1][1]
        repair_parts = call_kwargs.get("contents") or mock_call.call_args_list[1][0][0]
        repair_prompt = getattr(repair_parts[0], "text", str(repair_parts[0]))
        assert "```something```" not in repair_prompt
        assert "'''something'''" in repair_prompt
