"""Write-through Firestore persistence for in-memory repositories.

The catalog, policy, visit and verification repositories keep their in-memory logic;
Firestore-backed subclasses (see firestore_write_through.py) persist every mutated
entity here and reload all documents into memory at API startup.

SINGLE-INSTANCE CONSTRAINT: memory is the read path and is only filled at startup.
This is correct only while exactly one API instance serves traffic (Cloud Run
max-instances=1). With more instances, each one would serve a stale view of the
others' writes. Replace with native Firestore repositories before scaling out.

Document layout: one collection per entity type, doc id = entity id:
    {"workspace_id": str, "id": str, "payload": "<model_dump_json>"}
The payload is a JSON string so arbitrary contract models (nested arrays, deep
maps) stay within Firestore value and index-entry limits.

Writes are awaited and errors propagate: a failed write fails the request.
"""

from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def default_firestore_client(project_id: str | None) -> Any:
    from google.cloud import firestore

    return firestore.AsyncClient(project=project_id)


class FirestoreEntityStore:
    def __init__(self, client: Any) -> None:
        self.db = client

    async def put(
        self, collection: str, workspace_id: UUID, entity_id: UUID | str, entity: BaseModel
    ) -> None:
        await self.db.collection(collection).document(str(entity_id)).set(
            {
                "workspace_id": str(workspace_id),
                "id": str(entity_id),
                "payload": entity.model_dump_json(),
            }
        )

    async def put_marker(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        await self.db.collection(collection).document(doc_id).set(data)

    async def delete(self, collection: str, doc_id: str) -> None:
        await self.db.collection(collection).document(doc_id).delete()

    async def load(self, collection: str, model: type[ModelT]) -> list[tuple[UUID, ModelT]]:
        """Return (workspace_id, entity) for every document in the collection."""
        return [
            (UUID(data["workspace_id"]), model.model_validate_json(data["payload"]))
            for data in await self.load_raw(collection)
        ]

    async def load_raw(self, collection: str) -> list[dict[str, Any]]:
        return [doc.to_dict() async for doc in self.db.collection(collection).stream()]


class FirestoreWriteThrough:
    """Mixin for in-memory repositories persisted through FirestoreEntityStore."""

    _loaded: bool = False

    def _init_store(self, client: Any | None, project_id: str | None) -> None:
        if client is None:
            client = default_firestore_client(project_id)
        self._entity_store = FirestoreEntityStore(client)
        self._loaded = False

    async def load(self) -> None:
        """Populate in-memory state from Firestore once (call at startup)."""
        if self._loaded:
            return
        await self._load_entities()
        self._loaded = True

    async def _load_entities(self) -> None:
        raise NotImplementedError
