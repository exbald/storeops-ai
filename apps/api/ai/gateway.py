"""Gemini and Deterministic Model Gateways implementing ModelGateway protocol."""

import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class ModelGatewayError(Exception):
    """Base exception for model gateway failures."""


class ModelQuotaError(ModelGatewayError):
    """Raised when provider quota or rate limit is exhausted (HTTP 429)."""


class ModelTimeoutError(ModelGatewayError):
    """Raised when inference exceeds allocated time budget."""


class ModelTransientError(ModelGatewayError):
    """Raised on temporary provider network or server failures (HTTP 503/500)."""


class ModelSchemaError(ModelGatewayError):
    """Raised when model response cannot be parsed or validated into requested schema."""


class ModelBlockedError(ModelGatewayError):
    """Raised when model generation is blocked by safety filters."""


class GeminiGateway:
    """Production Google Gen AI Gemini gateway with structured output, multimodal input, and 1-shot repair."""

    def __init__(
        self, api_key: str | None = None, model_id: str = "gemini-2.5-flash"
    ) -> None:
        self.api_key = api_key
        self.model_id = model_id
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _detect_image_mime(self, data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
            return "image/webp"
        return "image/jpeg"

    def _build_multimodal_parts(
        self,
        prompt: str,
        images: list[bytes] | None = None,
        pdfs: list[bytes] | None = None,
    ) -> list[Any]:
        from google.genai import types

        parts: list[Any] = [types.Part.from_text(text=prompt)]

        if images:
            for img in images:
                mime = self._detect_image_mime(img)
                parts.append(types.Part.from_bytes(data=img, mime_type=mime))

        if pdfs:
            for pdf in pdfs:
                parts.append(
                    types.Part.from_bytes(data=pdf, mime_type="application/pdf")
                )

        return parts

    async def _invoke_api(self, contents: list[Any], config: Any) -> Any:
        client = self._get_client()
        # client.aio exposes async methods in google-genai
        if hasattr(client, "aio") and hasattr(client.aio, "models"):
            return await client.aio.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=config,
            )
        # Fallback to sync call if aio not present
        return client.models.generate_content(
            model=self.model_id,
            contents=contents,
            config=config,
        )

    async def _call_client(self, contents: list[Any], config: Any) -> Any:
        try:
            return await self._invoke_api(contents=contents, config=config)
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "ResourceExhausted" in msg or "quota" in msg.lower():
                raise ModelQuotaError(f"Gemini API quota exceeded: {msg}") from exc
            if (
                "503" in msg
                or "500" in msg
                or "ServiceUnavailable" in msg
                or "Unavailable" in msg
            ):
                raise ModelTransientError(
                    f"Gemini transient provider error: {msg}"
                ) from exc
            if "deadline" in msg.lower() or "timeout" in msg.lower():
                raise ModelTimeoutError(f"Gemini call timed out: {msg}") from exc
            if "blocked" in msg.lower() or "safety" in msg.lower():
                raise ModelBlockedError(f"Gemini response blocked: {msg}") from exc
            raise ModelGatewayError(f"Gemini call failed: {msg}") from exc

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[Any],
        images: list[bytes] | None = None,
        pdfs: list[bytes] | None = None,
        thinking_budget: str | None = None,
        system_instruction: str | None = None,
    ) -> Any:
        from google.genai import types

        parts = self._build_multimodal_parts(prompt=prompt, images=images, pdfs=pdfs)

        thinking_config = None
        if thinking_budget:
            try:
                budget_int = int(thinking_budget)
                thinking_config = types.ThinkingConfig(thinking_budget=budget_int)
            except ValueError:
                logger.warning(
                    f"Invalid thinking_budget '{thinking_budget}', ignoring."
                )

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
            "thinking_config": thinking_config,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_kwargs)

        response = await self._call_client(contents=parts, config=config)
        raw_text = getattr(response, "text", "") or ""

        # Validate with Pydantic
        try:
            if issubclass(response_schema, BaseModel):
                return response_schema.model_validate_json(raw_text)
            parsed = json.loads(raw_text)
            return response_schema(**parsed)
        except (ValidationError, json.JSONDecodeError, ValueError) as first_err:
            logger.info(
                f"Initial schema validation failed ({first_err}). Attempting 1-shot repair..."
            )

            # 1-shot repair attempt per specs/05-ai.md
            # Fence raw output in code blocks to prevent injection reflection
            repair_prompt = (
                f"Your previous response failed schema validation:\n"
                f"Error: {first_err}\n"
                f"Previous output:\n```json\n{raw_text}\n```\n\n"
                f"Please fix the validation error and return strictly valid JSON conforming to schema."
            )
            repair_parts = [types.Part.from_text(text=repair_prompt)]
            try:
                repair_response = await self._call_client(
                    contents=repair_parts, config=config
                )
                repaired_text = getattr(repair_response, "text", "") or ""
                if issubclass(response_schema, BaseModel):
                    return response_schema.model_validate_json(repaired_text)
                repaired_parsed = json.loads(repaired_text)
                return response_schema(**repaired_parsed)
            except Exception as repair_err:
                raise ModelSchemaError(
                    f"Schema validation failed after repair: {repair_err}. Initial error: {first_err}"
                ) from repair_err


class DeterministicModelGateway:
    """In-memory deterministic test double for ModelGateway."""

    def __init__(self) -> None:
        self._registry: dict[type[Any], Any] = {}
        self.call_history: list[dict[str, Any]] = []

    def register_response(self, schema_type: type[Any], response: Any) -> None:
        self._registry[schema_type] = response

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[Any],
        images: list[bytes] | None = None,
        pdfs: list[bytes] | None = None,
        thinking_budget: str | None = None,
        system_instruction: str | None = None,
    ) -> Any:
        self.call_history.append(
            {
                "prompt": prompt,
                "response_schema": response_schema,
                "images_count": len(images) if images else 0,
                "pdfs_count": len(pdfs) if pdfs else 0,
                "thinking_budget": thinking_budget,
                "system_instruction": system_instruction,
            }
        )

        if response_schema in self._registry:
            resp = self._registry[response_schema]
            if isinstance(resp, Exception):
                raise resp
            return resp

        raise ModelSchemaError(
            f"No deterministic response registered for schema {response_schema.__name__} in DeterministicModelGateway."
        )
