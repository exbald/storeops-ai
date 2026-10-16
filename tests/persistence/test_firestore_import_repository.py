"""Firestore-backed import repository: same behavior as the in-memory ImportRepository."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from storeops_contracts.models import Import, Kind2, Status4

from apps.api.adapters.state.firestore_imports import FirestoreImportRepository
from apps.api.modules.imports.repository import ImportRepository

BASE_TIME = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _import(
    workspace_id: UUID,
    *,
    kind: Kind2 = Kind2.SALES,
    status: Status4 = Status4.VALIDATED,
    sha: str = "a" * 64,
    offset_minutes: int = 0,
) -> Import:
    created = BASE_TIME + timedelta(minutes=offset_minutes)
    return Import(
        id=uuid4(),
        workspace_id=workspace_id,
        kind=kind,
        media_id=uuid4(),
        source_sha256=sha,
        status=status,
        version=1,
        row_count=1,
        error_count=0,
        errors=[],
        batch_id=None,
        created_at=created,
        updated_at=created,
        committed_at=None,
    )


@pytest.fixture
def repo(fake_firestore) -> FirestoreImportRepository:
    return FirestoreImportRepository(client=fake_firestore)


async def test_save_and_get_roundtrip_scoped_by_workspace(repo, fake_firestore):
    ws = uuid4()
    rec = _import(ws)
    await repo.save_import(rec)

    stored = fake_firestore.docs[("imports", str(rec.id))]
    assert stored["workspace_id"] == str(ws)
    assert await repo.get_import(ws, rec.id) == rec
    assert await repo.get_import(uuid4(), rec.id) is None
    assert await repo.get_import(ws, uuid4()) is None


async def test_staged_rows_none_until_staged(repo):
    rec = _import(uuid4())
    await repo.save_import(rec)
    assert await repo.get_staged_rows(rec.workspace_id, rec.id) is None
    assert await repo.get_staged_rows(rec.workspace_id, uuid4()) is None


async def test_staged_rows_roundtrip_preserves_types(repo):
    rec = _import(uuid4())
    store_id = uuid4()
    rows = [
        {
            "store_id": store_id,
            "store_code": "S1",
            "sku": "SKU-é-🍵",
            "business_date": "2026-09-10",
            "units": 3,
            "revenue": "7.50",
            "currency": "USD",
        },
        {"location_id": uuid4(), "sku": "X", "quantity": 2, "amount": Decimal("1.10"), "note": None},
    ]
    await repo.save_import(rec, staged_rows=rows)
    assert await repo.get_staged_rows(rec.workspace_id, rec.id) == rows


async def test_empty_staged_rows_are_distinct_from_none(repo):
    rec = _import(uuid4())
    await repo.save_import(rec, staged_rows=[])
    assert await repo.get_staged_rows(rec.workspace_id, rec.id) == []


async def test_save_without_rows_keeps_existing_staged_rows(repo):
    rec = _import(uuid4())
    rows = [{"store_id": uuid4(), "sku": "A", "units": 1}]
    await repo.save_import(rec, staged_rows=rows)

    updated = rec.model_copy(update={"status": Status4.COMMITTED, "version": 2})
    await repo.save_import(updated)

    assert (await repo.get_import(rec.workspace_id, rec.id)).status == Status4.COMMITTED
    assert await repo.get_staged_rows(rec.workspace_id, rec.id) == rows


async def test_large_staged_rows_are_chunked_under_doc_limit(repo, fake_firestore):
    rec = _import(uuid4())
    rows = [
        {"store_id": uuid4(), "store_code": f"STORE-{i:06d}", "sku": f"SKU-{i:08d}",
         "business_date": "2026-09-10", "units": i, "revenue": "12345.67", "currency": "USD"}
        for i in range(30_000)
    ]
    await repo.save_import(rec, staged_rows=rows)

    chunk_paths = [p for p in fake_firestore.docs if p[:3] == ("imports", str(rec.id), "staged_chunks")]
    assert len(chunk_paths) > 1
    assert await repo.get_staged_rows(rec.workspace_id, rec.id) == rows


async def test_restaging_replaces_previous_chunks(repo, fake_firestore):
    rec = _import(uuid4())
    big = [{"sku": f"SKU-{i:08d}", "store_id": uuid4(), "pad": "x" * 200} for i in range(10_000)]
    await repo.save_import(rec, staged_rows=big)
    small = [{"sku": "ONLY", "store_id": uuid4()}]
    await repo.save_import(rec, staged_rows=small)

    chunk_paths = [p for p in fake_firestore.docs if p[:3] == ("imports", str(rec.id), "staged_chunks")]
    assert len(chunk_paths) == 1
    assert await repo.get_staged_rows(rec.workspace_id, rec.id) == small


async def test_missing_chunk_is_an_error_not_partial_data(repo, fake_firestore):
    rec = _import(uuid4())
    await repo.save_import(rec, staged_rows=[{"sku": "A"}])
    for path in [p for p in fake_firestore.docs if "staged_chunks" in p]:
        del fake_firestore.docs[path]
    with pytest.raises(RuntimeError, match="staged"):
        await repo.get_staged_rows(rec.workspace_id, rec.id)


async def test_find_committed_import_matches_workspace_kind_sha_and_status(repo):
    ws = uuid4()
    validated = _import(ws, sha="b" * 64)
    committed = _import(ws, sha="b" * 64, status=Status4.COMMITTED)
    other_kind = _import(ws, sha="b" * 64, status=Status4.COMMITTED, kind=Kind2.INVENTORY)
    other_ws = _import(uuid4(), sha="b" * 64, status=Status4.COMMITTED)
    for rec in (validated, committed, other_kind, other_ws):
        await repo.save_import(rec)

    found = await repo.find_committed_import(ws, Kind2.SALES, "b" * 64)
    assert found == committed
    assert await repo.find_committed_import(ws, Kind2.SALES, "c" * 64) is None


async def test_list_imports_matches_in_memory_ordering_and_pagination(repo):
    memory = ImportRepository()
    ws = uuid4()
    records = [_import(ws, offset_minutes=i % 3) for i in range(7)]
    for rec in [*records, _import(uuid4())]:
        await repo.save_import(rec)
        await memory.save_import(rec)

    cursor = None
    pages_fs, pages_mem = [], []
    while True:
        fs_items, fs_cursor = await repo.list_imports(ws, cursor=cursor, limit=3)
        mem_items, mem_cursor = await memory.list_imports(ws, cursor=cursor, limit=3)
        pages_fs.append(fs_items)
        pages_mem.append(mem_items)
        assert fs_cursor == mem_cursor
        if fs_cursor is None:
            break
        cursor = fs_cursor

    assert pages_fs == pages_mem
    assert sum(len(p) for p in pages_fs) == 7


async def test_survives_new_repository_instance(fake_firestore):
    """Records persist in Firestore, not in the adapter instance (restart safety)."""
    ws = uuid4()
    rec = _import(ws)
    rows = [{"store_id": uuid4(), "sku": "A"}]
    await FirestoreImportRepository(client=fake_firestore).save_import(rec, staged_rows=rows)

    fresh = FirestoreImportRepository(client=fake_firestore)
    assert await fresh.get_import(ws, rec.id) == rec
    assert await fresh.get_staged_rows(rec.workspace_id, rec.id) == rows


@pytest.mark.parametrize("backend", ["firestore", "memory"])
async def test_staged_rows_are_scoped_by_workspace(fake_firestore, backend):
    repository = (
        FirestoreImportRepository(client=fake_firestore)
        if backend == "firestore"
        else ImportRepository()
    )
    owner = uuid4()
    rec = _import(owner)
    rows = [{"sku": "A", "units": 3}]
    await repository.save_import(rec, staged_rows=rows)

    assert await repository.get_staged_rows(owner, rec.id) == rows
    assert await repository.get_staged_rows(uuid4(), rec.id) is None
