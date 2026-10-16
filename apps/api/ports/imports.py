from typing import Any, Protocol
from uuid import UUID

from storeops_contracts.models import Import, Kind2


class ImportRepositoryPort(Protocol):
    async def save_import(
        self,
        import_record: Import,
        staged_rows: list[dict[str, Any]] | None = None,
    ) -> Import:
        """Upsert an import; replace staged rows only when staged_rows is not None."""
        ...

    async def get_import(self, workspace_id: UUID, import_id: UUID) -> Import | None: ...

    async def get_staged_rows(self, import_id: UUID) -> list[dict[str, Any]] | None:
        """Rows staged at validation time; None when never staged."""
        ...

    async def find_committed_import(
        self, workspace_id: UUID, kind: Kind2, source_sha256: str
    ) -> Import | None: ...

    async def list_imports(
        self, workspace_id: UUID, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[Import], str | None]:
        """Page imports ordered by (created_at DESC, id DESC); cursor is the last id seen."""
        ...
