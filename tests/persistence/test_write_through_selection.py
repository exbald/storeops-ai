"""Repository selection by STATE_BACKEND and load-on-startup for write-through repos."""

from typing import Any
from uuid import uuid4

import entity_factories as f
import pytest
from fastapi.testclient import TestClient

from apps.api.adapters.state.firestore_write_through import (
    FirestoreBackedCatalogRepository,
    FirestoreBackedPolicyRepository,
    FirestoreBackedVerificationRepository,
    FirestoreBackedVisitRepository,
)
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core import auth
from apps.api.core.config import Settings, settings
from apps.api.main import app
from apps.api.modules.catalog import dependencies as catalog_deps
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.policies import dependencies as policy_deps
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.verification import dependencies as verification_deps
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.visits import dependencies as visit_deps
from apps.api.modules.visits.repository import InMemoryVisitRepository

BUILDERS = [
    (catalog_deps.build_catalog_repository, InMemoryCatalogRepository, FirestoreBackedCatalogRepository),
    (policy_deps.build_policy_repository, InMemoryPolicyRepository, FirestoreBackedPolicyRepository),
    (visit_deps.build_visit_repository, InMemoryVisitRepository, FirestoreBackedVisitRepository),
    (
        verification_deps.build_verification_repository,
        InMemoryVerificationRepository,
        FirestoreBackedVerificationRepository,
    ),
]


def _settings(state_backend: str) -> Settings:
    return Settings(app_env="development", profile="LOCAL", ai_mode="STUB", state_backend=state_backend)


@pytest.mark.parametrize(("build", "memory_cls", "_backed_cls"), BUILDERS)
def test_in_memory_backend_uses_plain_in_memory_repo(build, memory_cls, _backed_cls):
    assert type(build(_settings("in_memory"))) is memory_cls


@pytest.mark.parametrize(("build", "_memory_cls", "backed_cls"), BUILDERS)
def test_firestore_backend_uses_write_through_repo(build, _memory_cls, backed_cls, fake_firestore):
    projects: list[Any] = []

    def factory(project):
        projects.append(project)
        return fake_firestore

    cfg = _settings("firestore")
    repo = build(cfg, firestore_client_factory=factory)
    assert isinstance(repo, backed_cls)
    assert projects == [cfg.firebase_project_id]


def test_startup_loads_persisted_entities_when_firestore(monkeypatch, fake_firestore):
    ws = uuid4()
    seeded_store = f.store(ws)
    seeded_visit = f.visit(ws)
    seeded_promo = f.promotion(ws)
    seeded_verification = f.verification(ws, uuid4())

    # Previous process wrote these
    import asyncio

    async def seed():
        await FirestoreBackedCatalogRepository(client=fake_firestore).update_store(seeded_store)
        await FirestoreBackedVisitRepository(client=fake_firestore).create_visit(ws, seeded_visit)
        await FirestoreBackedPolicyRepository(client=fake_firestore).create_promotion(ws, seeded_promo)
        await FirestoreBackedVerificationRepository(client=fake_firestore).save_verification(
            ws, seeded_verification
        )

    asyncio.run(seed())

    catalog = FirestoreBackedCatalogRepository(client=fake_firestore)
    visits = FirestoreBackedVisitRepository(client=fake_firestore)
    policies = FirestoreBackedPolicyRepository(client=fake_firestore)
    verifications = FirestoreBackedVerificationRepository(client=fake_firestore)
    monkeypatch.setattr(auth, "_state_repository", InMemoryStateRepository())
    monkeypatch.setattr(settings, "state_backend", "firestore")
    monkeypatch.setattr(settings, "profile", "LOCAL")
    monkeypatch.setattr(catalog_deps, "_catalog_repository", catalog)
    monkeypatch.setattr(visit_deps, "_visit_repository", visits)
    monkeypatch.setattr(policy_deps, "_policy_repository", policies)
    monkeypatch.setattr(verification_deps, "_verification_repository", verifications)

    with TestClient(app):
        pass

    async def read():
        return (
            await catalog.get_store(ws, seeded_store.id),
            await visits.get_visit(ws, seeded_visit.id),
            await policies.get_promotion(ws, seeded_promo.id),
            await verifications.get_verification(ws, seeded_verification.id),
        )

    assert asyncio.run(read()) == (seeded_store, seeded_visit, seeded_promo, seeded_verification)
