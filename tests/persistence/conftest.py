"""In-process fakes for Google Cloud clients used by persistence adapter tests.

No network: each fake implements only the client surface the adapters use.
"""

import copy
import threading
from typing import Any

import pytest
from google.api_core.exceptions import NotFound

FIRESTORE_MAX_DOC_BYTES = 1_048_576
FIRESTORE_MAX_BATCH_WRITES = 500


def _estimate_doc_bytes(data: dict[str, Any]) -> int:
    total = 0
    for key, value in data.items():
        total += len(key) + 1
        if isinstance(value, bytes | str):
            total += len(value)
        else:
            total += len(repr(value))
    return total


# ---------------------------------------------------------------- Firestore


class FakeDocSnapshot:
    def __init__(self, reference: "FakeDocRef", data: dict[str, Any] | None) -> None:
        self.reference = reference
        self.id = reference.id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._data)


class FakeDocRef:
    def __init__(self, db: "FakeAsyncFirestore", path: tuple[str, ...]) -> None:
        self._db = db
        self.path = path
        self.id = path[-1]

    def collection(self, name: str) -> "FakeCollection":
        return FakeCollection(self._db, (*self.path, name))

    async def get(self) -> FakeDocSnapshot:
        return FakeDocSnapshot(self, copy.deepcopy(self._db.docs.get(self.path)))

    async def set(self, data: dict[str, Any], merge: bool = False) -> None:
        self._db.apply_set(self.path, data, merge)

    async def delete(self) -> None:
        self._db.docs.pop(self.path, None)


class FakeQuery:
    def __init__(
        self,
        db: "FakeAsyncFirestore",
        path: tuple[str, ...],
        filters: tuple[tuple[str, str, Any], ...] = (),
    ) -> None:
        self._db = db
        self._path = path
        self._filters = filters

    def where(self, field: str, op: str, value: Any) -> "FakeQuery":
        if op != "==":
            raise NotImplementedError(f"Fake supports only '==' filters, got {op}")
        return FakeQuery(self._db, self._path, (*self._filters, (field, op, value)))

    async def stream(self):
        self._db.queries.append((self._path, self._filters))
        for path, data in list(self._db.docs.items()):
            if path[:-1] != self._path:
                continue
            if all(data.get(f) == v for f, _, v in self._filters):
                yield FakeDocSnapshot(FakeDocRef(self._db, path), copy.deepcopy(data))


class FakeCollection(FakeQuery):
    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self._db, (*self._path, doc_id))


class FakeBatch:
    def __init__(self, db: "FakeAsyncFirestore") -> None:
        self._db = db
        self._ops: list[tuple[str, tuple[str, ...], dict[str, Any] | None, bool]] = []

    def set(self, ref: FakeDocRef, data: dict[str, Any], merge: bool = False) -> None:
        self._ops.append(("set", ref.path, copy.deepcopy(data), merge))

    def delete(self, ref: FakeDocRef) -> None:
        self._ops.append(("delete", ref.path, None, False))

    async def commit(self) -> None:
        if len(self._ops) > FIRESTORE_MAX_BATCH_WRITES:
            raise ValueError("Fake Firestore: batch exceeds 500 writes")
        self._db.commits += 1
        for op, path, data, merge in self._ops:
            if op == "set":
                self._db.apply_set(path, data or {}, merge)
            else:
                self._db.docs.pop(path, None)


class FakeAsyncFirestore:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, ...], dict[str, Any]] = {}
        self.queries: list[tuple[tuple[str, ...], tuple[tuple[str, str, Any], ...]]] = []
        self.commits = 0

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, (name,))

    def batch(self) -> FakeBatch:
        return FakeBatch(self)

    def apply_set(self, path: tuple[str, ...], data: dict[str, Any], merge: bool) -> None:
        new_data = {**self.docs.get(path, {}), **data} if merge else dict(data)
        size = _estimate_doc_bytes(new_data)
        if size > FIRESTORE_MAX_DOC_BYTES:
            raise ValueError(f"Fake Firestore: document {path} is {size} bytes (> 1 MiB)")
        self.docs[path] = copy.deepcopy(new_data)


@pytest.fixture
def fake_firestore() -> FakeAsyncFirestore:
    return FakeAsyncFirestore()


# ---------------------------------------------------------------- Cloud Storage


class FakeBlob:
    def __init__(self, bucket: "FakeBucket", name: str) -> None:
        self._bucket = bucket
        self.name = name

    def upload_from_string(self, data: bytes, content_type: str | None = None) -> None:
        self._bucket.thread_ids.append(threading.get_ident())
        self._bucket.objects[self.name] = bytes(data)
        self._bucket.content_types[self.name] = content_type

    def download_as_bytes(self) -> bytes:
        self._bucket.thread_ids.append(threading.get_ident())
        if self.name not in self._bucket.objects:
            raise NotFound(f"No such object: {self._bucket.name}/{self.name}")
        return self._bucket.objects[self.name]


class FakeBucket:
    def __init__(self, name: str) -> None:
        self.name = name
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str | None] = {}
        self.thread_ids: list[int] = []

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)


class FakeStorageClient:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeBucket] = {}

    def bucket(self, name: str) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket(name))


@pytest.fixture
def fake_storage_client() -> FakeStorageClient:
    return FakeStorageClient()


# ---------------------------------------------------------------- BigQuery


class FakeQueryJob:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def result(self) -> list[dict[str, Any]]:
        return self._rows


class FakeBigQueryClient:
    def __init__(self, existing_batches: int = 0) -> None:
        self.existing_batches = existing_batches
        self.inserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.insert_errors: dict[str, list[dict[str, Any]]] = {}

    def query(self, sql: str, job_config: Any = None) -> FakeQueryJob:
        return FakeQueryJob([{"cnt": self.existing_batches}])

    def insert_rows_json(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            raise ValueError("Fake BigQuery: insert_rows_json called with no rows")
        self.inserts.append((table, rows))
        table_name = table.rsplit(".", 1)[-1]
        return self.insert_errors.get(table_name, [])


@pytest.fixture
def fake_bigquery_client() -> FakeBigQueryClient:
    return FakeBigQueryClient()
