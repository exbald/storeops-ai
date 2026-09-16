import asyncio
from typing import Any
from uuid import UUID

from storeops_contracts.models import Import, Kind2


class ImportRepository:
    def __init__(self) -> None:
        self._imports: dict[UUID, Import] = {}
        self._staged_rows: dict[UUID, list[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def save_import(
        self,
        import_record: Import,
        staged_rows: list[dict[str, Any]] | None = None,
    ) -> Import:
        async with self._lock:
            self._imports[import_record.id] = import_record
            if staged_rows is not None:
                self._staged_rows[import_record.id] = staged_rows
            return import_record

    async def get_import(self, workspace_id: UUID, import_id: UUID) -> Import | None:
        async with self._lock:
            imp = self._imports.get(import_id)
            if imp and imp.workspace_id == workspace_id:
                return imp
            return None

    async def get_staged_rows(self, import_id: UUID) -> list[dict[str, Any]] | None:
        async with self._lock:
            return self._staged_rows.get(import_id)

    async def find_committed_import(
        self,
        workspace_id: UUID,
        kind: Kind2,
        source_sha256: str,
    ) -> Import | None:
        async with self._lock:
            for imp in self._imports.values():
                if (
                    imp.workspace_id == workspace_id
                    and imp.kind == kind
                    and imp.source_sha256 == source_sha256
                    and imp.status.value == "COMMITTED"
                ):
                    return imp
            return None

    async def list_imports(
        self,
        workspace_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Import], str | None]:
        async with self._lock:
            ws_imports = [
                imp
                for imp in self._imports.values()
                if imp.workspace_id == workspace_id
            ]
            # Sort descending (created_at DESC, id DESC)
            ws_imports.sort(key=lambda x: (x.created_at, x.id), reverse=True)

            start_idx = 0
            if cursor:
                for idx, imp in enumerate(ws_imports):
                    if str(imp.id) == cursor:
                        start_idx = idx + 1
                        break

            items = ws_imports[start_idx : start_idx + limit]
            next_cursor = None
            if start_idx + limit < len(ws_imports) and items:
                next_cursor = str(items[-1].id)

            return items, next_cursor
