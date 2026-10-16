"""Firestore-backed import repository (STATE_BACKEND=firestore).

Layout:
- imports/{import_id}                          Import record (model_dump json) incl. workspace_id
- imports/{import_id}/staging/manifest         {generation, chunk_count, row_count}
- imports/{import_id}/staged_chunks/{gen}-{n}  {index, rows_json: bytes}

Staged rows are JSON-encoded into chunks below Firestore's 1 MiB document limit.
New chunks are written under a fresh generation before the manifest is switched,
so readers never observe a mix of old and new rows.
"""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from storeops_contracts.models import Import, Kind2

from apps.api.modules.imports.repository import paginate_imports
from apps.api.ports.imports import ImportRepositoryPort

IMPORTS_COLLECTION = "imports"
CHUNKS_SUBCOLLECTION = "staged_chunks"
STAGING_SUBCOLLECTION = "staging"
MANIFEST_DOC = "manifest"

# Firestore documents max out at 1 MiB; leave headroom for field names/metadata.
MAX_CHUNK_BYTES = 900_000
# Firestore commit requests max out at 10 MiB.
MAX_CHUNKS_PER_BATCH = 8
MAX_DELETES_PER_BATCH = 450


def _encode_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    raise TypeError(f"Cannot stage value of type {type(value).__name__}")


def _decode_object(obj: dict[str, Any]) -> Any:
    if obj.keys() == {"$uuid"}:
        return UUID(obj["$uuid"])
    if obj.keys() == {"$decimal"}:
        return Decimal(obj["$decimal"])
    return obj


def _chunk_rows(rows: list[dict[str, Any]]) -> list[bytes]:
    chunks: list[bytes] = []
    current: list[bytes] = []
    current_size = 2  # brackets
    for row in rows:
        encoded = json.dumps(row, default=_encode_value, separators=(",", ":")).encode()
        if len(encoded) + 2 > MAX_CHUNK_BYTES:
            raise ValueError(f"Staged row exceeds {MAX_CHUNK_BYTES} bytes and cannot be stored")
        if current and current_size + len(encoded) + 1 > MAX_CHUNK_BYTES:
            chunks.append(b"[" + b",".join(current) + b"]")
            current, current_size = [], 2
        current.append(encoded)
        current_size += len(encoded) + 1
    if current:
        chunks.append(b"[" + b",".join(current) + b"]")
    return chunks


def _decode_chunk(payload: bytes) -> list[dict[str, Any]]:
    return json.loads(payload, object_hook=_decode_object)


class FirestoreImportRepository(ImportRepositoryPort):
    def __init__(self, client: Any | None = None, project_id: str | None = None) -> None:
        if client is None:
            from google.cloud import firestore

            client = firestore.AsyncClient(project=project_id)
        self.db = client

    def _import_ref(self, import_id: UUID) -> Any:
        return self.db.collection(IMPORTS_COLLECTION).document(str(import_id))

    def _manifest_ref(self, import_id: UUID) -> Any:
        return (
            self._import_ref(import_id).collection(STAGING_SUBCOLLECTION).document(MANIFEST_DOC)
        )

    def _chunks(self, import_id: UUID) -> Any:
        return self._import_ref(import_id).collection(CHUNKS_SUBCOLLECTION)

    @staticmethod
    def _chunk_id(generation: str, index: int) -> str:
        return f"{generation}-{index:05d}"

    async def _write_chunks(self, import_id: UUID, generation: str, chunks: list[bytes]) -> None:
        coll = self._chunks(import_id)
        for start in range(0, len(chunks), MAX_CHUNKS_PER_BATCH):
            batch = self.db.batch()
            for index in range(start, min(start + MAX_CHUNKS_PER_BATCH, len(chunks))):
                ref = coll.document(self._chunk_id(generation, index))
                batch.set(ref, {"index": index, "rows_json": chunks[index]})
            await batch.commit()

    async def _delete_stale_chunks(self, import_id: UUID, generation: str) -> None:
        stale = [
            doc.reference
            async for doc in self._chunks(import_id).stream()
            if not doc.id.startswith(f"{generation}-")
        ]
        for start in range(0, len(stale), MAX_DELETES_PER_BATCH):
            batch = self.db.batch()
            for ref in stale[start : start + MAX_DELETES_PER_BATCH]:
                batch.delete(ref)
            await batch.commit()

    async def save_import(
        self,
        import_record: Import,
        staged_rows: list[dict[str, Any]] | None = None,
    ) -> Import:
        record_data = import_record.model_dump(mode="json")
        if staged_rows is None:
            await self._import_ref(import_record.id).set(record_data)
            return import_record

        generation = uuid4().hex
        chunks = _chunk_rows(staged_rows)
        await self._write_chunks(import_record.id, generation, chunks)

        batch = self.db.batch()
        batch.set(self._import_ref(import_record.id), record_data)
        batch.set(
            self._manifest_ref(import_record.id),
            {"generation": generation, "chunk_count": len(chunks), "row_count": len(staged_rows)},
        )
        await batch.commit()

        await self._delete_stale_chunks(import_record.id, generation)
        return import_record

    async def get_import(self, workspace_id: UUID, import_id: UUID) -> Import | None:
        doc = await self._import_ref(import_id).get()
        if not doc.exists:
            return None
        record = Import.model_validate(doc.to_dict())
        return record if record.workspace_id == workspace_id else None

    async def get_staged_rows(self, import_id: UUID) -> list[dict[str, Any]] | None:
        manifest_doc = await self._manifest_ref(import_id).get()
        if not manifest_doc.exists:
            return None
        manifest = manifest_doc.to_dict()
        generation, chunk_count = manifest["generation"], int(manifest["chunk_count"])

        rows: list[dict[str, Any]] = []
        coll = self._chunks(import_id)
        for index in range(chunk_count):
            chunk_doc = await coll.document(self._chunk_id(generation, index)).get()
            if not chunk_doc.exists:
                raise RuntimeError(
                    f"Import {import_id} staged rows are incomplete: chunk {index} missing"
                )
            rows.extend(_decode_chunk(chunk_doc.to_dict()["rows_json"]))
        if len(rows) != int(manifest["row_count"]):
            raise RuntimeError(
                f"Import {import_id} staged rows are inconsistent: "
                f"expected {manifest['row_count']}, read {len(rows)}"
            )
        return rows

    async def find_committed_import(
        self,
        workspace_id: UUID,
        kind: Kind2,
        source_sha256: str,
    ) -> Import | None:
        query = (
            self.db.collection(IMPORTS_COLLECTION)
            .where("workspace_id", "==", str(workspace_id))
            .where("kind", "==", kind.value)
            .where("source_sha256", "==", source_sha256)
            .where("status", "==", "COMMITTED")
        )
        async for doc in query.stream():
            return Import.model_validate(doc.to_dict())
        return None

    async def list_imports(
        self,
        workspace_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Import], str | None]:
        # Equality-only query (no composite index); ordering/paging mirror the in-memory repo.
        query = self.db.collection(IMPORTS_COLLECTION).where(
            "workspace_id", "==", str(workspace_id)
        )
        records = [Import.model_validate(doc.to_dict()) async for doc in query.stream()]
        return paginate_imports(records, cursor, limit)
