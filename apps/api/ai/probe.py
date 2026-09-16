"""Live provider probe for Gemini API connectivity and honest credentials verification."""

import os
import re
from typing import Any

from pydantic import BaseModel


def _sanitize_error(msg: str) -> str:
    """Mask potential API keys or query params in error strings."""
    sanitized = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[MASKED_KEY]", msg)
    return re.sub(r"key=[^&\s]+", "key=[MASKED]", sanitized)


class ProbePing(BaseModel):
    ping: str


async def _execute_probe(
    api_key: str, model_id: str = "gemini-2.5-flash"
) -> dict[str, Any]:
    from apps.api.ai.gateway import GeminiGateway

    gateway = GeminiGateway(api_key=api_key, model_id=model_id)
    try:
        res = await gateway.generate_structured(
            prompt='Respond with JSON: {"ping": "pong"}',
            response_schema=ProbePing,
        )
        if res.ping == "pong":
            return {"status": "ok", "model": model_id, "live_accepted": True}
        return {
            "status": "failed",
            "reason": f"Unexpected ping response: {res.ping}",
            "live_accepted": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "reason": _sanitize_error(str(exc)),
            "live_accepted": False,
        }


async def probe_live_gemini(model_id: str = "gemini-2.5-flash") -> dict[str, Any]:
    """Honest live provider probe. If credentials missing, returns blocked status without faking success."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "status": "blocked",
            "reason": "Missing GEMINI_API_KEY environment variable. Live provider gate remains blocked.",
            "live_accepted": False,
        }

    return await _execute_probe(api_key=api_key, model_id=model_id)
