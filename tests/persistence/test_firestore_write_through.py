"""Write-through Firestore persistence for the in-memory catalog/policy/visit/verification repos.

Each test writes through one repository instance, then simulates an API restart by
constructing a fresh instance on the same Firestore and calling load().
"""

from uuid import uuid4

import entity_factories as f
import pytest
from google.api_core.exceptions import ServiceUnavailable
from storeops_contracts.models import State, Status1

from apps.api.adapters.state.firestore_write_through import (
    FirestoreBackedCatalogRepository,
    FirestoreBackedPolicyRepository,
    FirestoreBackedVerificationRepository,
    FirestoreBackedVisitRepository,
)

# ---------------------------------------------------------------- catalog


async def test_catalog_round_trip(fake_firestore):
    ws = uuid4()
    repo = FirestoreBackedCatalogRepository(client=fake_firestore)
    backroom = f.location(ws, code="BR-1")
    store = f.store(ws, code="S-1", backroom_id=backroom.id)
    await repo.create_store_with_backroom(store, backroom.model_copy(update={"store_id": store.id}))
    renamed = store.model_copy(update={"name": "Renamed", "version": 2})
    await repo.update_store(renamed)
    distributor = f.location(ws, code="DC-1")
    await repo.create_location(distributor)
    await repo.update_location(distributor.model_copy(update={"active": False, "version": 2}))
    prod = f.product(ws, sku="SKU-9")
    await repo.create_product(prod)
    await repo.update_product(prod.model_copy(update={"case_units": 24, "version": 2}))
    med = f.media(ws)
    await repo.create_media(med)
    ready = med.model_copy(update={"status": Status1.READY, "version": 2})
    await repo.update_media(ready)
    await repo.add_active_policy_product_reference(ws, prod.id)

    fresh = FirestoreBackedCatalogRepository(client=fake_firestore)
    await fresh.load()

    assert await fresh.get_store(ws, store.id) == renamed
    assert await fresh.get_store_by_code(ws, "S-1") == renamed
    assert await fresh.get_location_by_code(ws, "BR-1") == await repo.get_location(ws, backroom.id)
    assert (await fresh.get_location(ws, distributor.id)).active is False
    assert (await fresh.get_product_by_sku(ws, "SKU-9")).case_units == 24
    assert await fresh.get_media(ws, med.id) == ready
    assert await fresh.has_active_policy_product_reference(ws, prod.id)
    assert await fresh.list_stores(ws) == await repo.list_stores(ws)
    assert await fresh.list_locations(ws) == await repo.list_locations(ws)
    assert await fresh.list_products(ws) == await repo.list_products(ws)


async def test_catalog_policy_reference_removal_is_persisted(fake_firestore):
    ws, product_id = uuid4(), uuid4()
    repo = FirestoreBackedCatalogRepository(client=fake_firestore)
    await repo.add_active_policy_product_reference(ws, product_id)
    await repo.remove_active_policy_product_reference(ws, product_id)

    fresh = FirestoreBackedCatalogRepository(client=fake_firestore)
    await fresh.load()
    assert not await fresh.has_active_policy_product_reference(ws, product_id)


async def test_catalog_documents_carry_workspace_id(fake_firestore):
    ws = uuid4()
    repo = FirestoreBackedCatalogRepository(client=fake_firestore)
    prod = f.product(ws)
    await repo.create_product(prod)
    doc = fake_firestore.docs[("products", str(prod.id))]
    assert doc["workspace_id"] == str(ws)


async def test_get_media_by_id_finds_media_across_workspaces(fake_firestore):
    repo = FirestoreBackedCatalogRepository(client=fake_firestore)
    med = f.media(uuid4())
    await repo.create_media(med)
    assert await repo.get_media_by_id(med.id) == med
    assert await repo.get_media_by_id(uuid4()) is None


# ---------------------------------------------------------------- policies


async def test_policy_round_trip(fake_firestore):
    ws = uuid4()
    repo = FirestoreBackedPolicyRepository(client=fake_firestore)
    promo = f.promotion(ws)
    await repo.create_promotion(ws, promo)
    archived = promo.model_copy(update={"archived": True, "version": 2})
    await repo.update_promotion(ws, archived)
    v1 = f.policy_version(promo.id, version=1)
    v2 = f.policy_version(promo.id, version=2)
    await repo.create_policy_version(ws, v1)
    await repo.create_policy_version(ws, v2)

    fresh = FirestoreBackedPolicyRepository(client=fake_firestore)
    await fresh.load()

    assert await fresh.get_promotion(ws, promo.id) == archived
    assert await fresh.get_policy_version(ws, promo.id, 2) == v2
    assert await fresh.get_policy_version_by_id(ws, v1.id) == v1
    assert await fresh.list_policy_versions(ws, promo.id) == await repo.list_policy_versions(ws, promo.id)
    assert await fresh.list_promotions(ws) == await repo.list_promotions(ws)
    assert await fresh.get_promotion(uuid4(), promo.id) is None


# ---------------------------------------------------------------- visits


async def test_visit_round_trip(fake_firestore):
    ws = uuid4()
    repo = FirestoreBackedVisitRepository(client=fake_firestore)
    vis = f.visit(ws)
    await repo.create_visit(ws, vis)
    inv = f.investigation(ws, visit_id=vis.id)
    await repo.create_investigation(ws, inv)
    proposed = inv.model_copy(update={"state": State.PROPOSED, "version": 2})
    await repo.update_investigation(ws, proposed)
    linked = vis.model_copy(update={"active_investigation_id": inv.id, "version": 2})
    await repo.update_visit(ws, linked)
    ev = f.evidence(inv.id)
    await repo.save_evidence(ws, ev)
    rep = f.report(ws, inv.id)
    await repo.save_report(ws, rep)

    fresh = FirestoreBackedVisitRepository(client=fake_firestore)
    await fresh.load()

    assert await fresh.get_visit(ws, vis.id) == linked
    assert await fresh.get_investigation(ws, inv.id) == proposed
    assert await fresh.get_evidence(ws, ev.id) == ev
    assert await fresh.get_report(ws, rep.id) == rep
    assert await fresh.list_visits(ws) == await repo.list_visits(ws)
    assert await fresh.list_investigations(ws) == await repo.list_investigations(ws)
    assert await fresh.list_evidence(ws, inv.id) == await repo.list_evidence(ws, inv.id)


async def test_evidence_without_workspace_field_is_scoped_on_reload(fake_firestore):
    ws = uuid4()
    repo = FirestoreBackedVisitRepository(client=fake_firestore)
    ev = f.evidence(uuid4())
    await repo.save_evidence(ws, ev)

    fresh = FirestoreBackedVisitRepository(client=fake_firestore)
    await fresh.load()
    assert await fresh.get_evidence(ws, ev.id) == ev
    assert await fresh.get_evidence(uuid4(), ev.id) is None


# ---------------------------------------------------------------- verification


async def test_verification_round_trip(fake_firestore):
    ws, inv_id = uuid4(), uuid4()
    repo = FirestoreBackedVerificationRepository(client=fake_firestore)
    first = f.verification(ws, inv_id, minutes=0)
    second = f.verification(ws, inv_id, minutes=5)
    await repo.save_verification(ws, first)
    await repo.save_verification(ws, second)
    updated = first.model_copy(update={"version": 2, "report_id": uuid4()})
    await repo.update_verification(ws, updated)

    fresh = FirestoreBackedVerificationRepository(client=fake_firestore)
    await fresh.load()

    assert await fresh.get_verification(ws, first.id) == updated
    assert await fresh.list_verifications(ws, inv_id) == await repo.list_verifications(ws, inv_id)


# ---------------------------------------------------------------- failures


@pytest.mark.parametrize(
    ("repo_cls", "mutate", "read"),
    [
        (
            FirestoreBackedCatalogRepository,
            lambda r, ws, e: r.create_product(e),
            lambda r, ws, e: r.get_product(ws, e.id),
        ),
        (
            FirestoreBackedPolicyRepository,
            lambda r, ws, e: r.create_promotion(ws, e),
            lambda r, ws, e: r.get_promotion(ws, e.id),
        ),
        (
            FirestoreBackedVisitRepository,
            lambda r, ws, e: r.create_visit(ws, e),
            lambda r, ws, e: r.get_visit(ws, e.id),
        ),
        (
            FirestoreBackedVerificationRepository,
            lambda r, ws, e: r.save_verification(ws, e),
            lambda r, ws, e: r.get_verification(ws, e.id),
        ),
    ],
)
async def test_write_failure_raises_and_leaves_memory_unchanged(fake_firestore, repo_cls, mutate, read):
    ws = uuid4()
    entity = {
        FirestoreBackedCatalogRepository: lambda: f.product(ws),
        FirestoreBackedPolicyRepository: lambda: f.promotion(ws),
        FirestoreBackedVisitRepository: lambda: f.visit(ws),
        FirestoreBackedVerificationRepository: lambda: f.verification(ws, uuid4()),
    }[repo_cls]()
    repo = repo_cls(client=fake_firestore)
    fake_firestore.fail_writes = True

    with pytest.raises(ServiceUnavailable):
        await mutate(repo, ws, entity)
    assert await read(repo, ws, entity) is None


async def test_policy_reference_delete_failure_raises(fake_firestore):
    ws, product_id = uuid4(), uuid4()
    repo = FirestoreBackedCatalogRepository(client=fake_firestore)
    await repo.add_active_policy_product_reference(ws, product_id)
    fake_firestore.fail_writes = True
    with pytest.raises(ServiceUnavailable):
        await repo.remove_active_policy_product_reference(ws, product_id)
    assert await repo.has_active_policy_product_reference(ws, product_id)


async def test_load_failure_raises(fake_firestore):
    fake_firestore.fail_reads = True
    with pytest.raises(ServiceUnavailable):
        await FirestoreBackedVisitRepository(client=fake_firestore).load()


async def test_load_is_idempotent(fake_firestore):
    ws = uuid4()
    repo = FirestoreBackedVisitRepository(client=fake_firestore)
    await repo.create_visit(ws, f.visit(ws))
    fresh = FirestoreBackedVisitRepository(client=fake_firestore)
    await fresh.load()
    await fresh.load()
    items, _ = await fresh.list_visits(ws)
    assert len(items) == 1
