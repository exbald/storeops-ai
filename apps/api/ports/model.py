from typing import Any, Protocol


class ModelGateway(Protocol):
    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[Any],
        images: list[bytes] | None = None,
        pdfs: list[bytes] | None = None,
        thinking_budget: str | None = None,
    ) -> Any:
        """Structured inference conforming to Pydantic schema."""
        ...
