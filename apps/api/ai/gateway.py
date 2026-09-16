"""Gemini and Deterministic Model Gateways implementing ModelGateway protocol."""

import asyncio
import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def _sanitize_error(msg: str) -> str:
    """Mask potential API keys or query params in error strings."""
    sanitized = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[MASKED_KEY]", msg)
    return re.sub(r"(key|token|secret|password)=[^&\s]+", r"\1=[MASKED]", sanitized)


class ModelGatewayError(Exception):
    """Base exception for ModelGateway failures."""


class ModelQuotaError(ModelGatewayError):
    """Exceeded provider rate limit or quota (HTTP 429)."""


class ModelTimeoutError(ModelGatewayError):
    """Provider call timed out."""


class ModelTransientError(ModelGatewayError):
    """Transient provider error (HTTP 500, 503)."""


class ModelSchemaError(ModelGatewayError):
    """Output could not be parsed into requested schema even after 1-shot repair."""


class ModelBlockedError(ModelGatewayError):
    """Output blocked by safety filter or policy."""


class GeminiGateway:
    """Production implementation of ModelGateway using Google Gen AI SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_id = model_id
        self._client: Any = None

    def _get_client(self) -> Any:
        if not self._client:
            if not self.api_key:
                raise ModelGatewayError(
                    "Missing GEMINI_API_KEY. Live model inference requires credentials."
                )
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except ImportError as err:
                raise ModelGatewayError("google-genai SDK not installed.") from err
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
        # Non-blocking execution of sync client call
        return await asyncio.to_thread(
            client.models.generate_content,
            model=self.model_id,
            contents=contents,
            config=config,
        )

    async def _call_client(self, contents: list[Any], config: Any) -> Any:
        try:
            return await self._invoke_api(contents=contents, config=config)
        except Exception as exc:
            msg = _sanitize_error(str(exc))
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

    @staticmethod
    def _extract_system_instruction(prompt: str) -> tuple[str, str | None]:
        """Extract embedded system instruction from prompt tags."""
        match = re.search(
            r"<system_instruction>\s*(.*?)\s*</system_instruction>",
            prompt,
            re.DOTALL,
        )
        if match:
            system_instruction = match.group(1).strip()
            cleaned_prompt = re.sub(
                r"<system_instruction>\s*.*?\s*</system_instruction>",
                "",
                prompt,
                flags=re.DOTALL,
            ).strip()
            return cleaned_prompt, system_instruction
        return prompt, None

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[Any],
        images: list[bytes] | None = None,
        pdfs: list[bytes] | None = None,
        thinking_budget: str | None = None,
    ) -> Any:
        from google.genai import types

        # Extract system instruction embedded in prompt tags to preserve ModelGateway protocol signature
        cleaned_prompt, system_instruction = self._extract_system_instruction(prompt)

        parts = self._build_multimodal_parts(
            prompt=cleaned_prompt, images=images, pdfs=pdfs
        )

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
            # Replace inner backticks to prevent markdown code block breakout
            safe_raw_text = raw_text.replace("```", "'''")
            safe_err = str(first_err).replace("```", "'''")
            repair_prompt = (
                f"Your previous response failed schema validation:\n"
                f"Error: {safe_err}\n"
                f"Previous output:\n```json\n{safe_raw_text}\n```\n\n"
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
    ) -> Any:
        self.call_history.append(
            {
                "prompt": prompt,
                "response_schema": response_schema,
                "images_count": len(images) if images else 0,
                "pdfs_count": len(pdfs) if pdfs else 0,
                "thinking_budget": thinking_budget,
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
