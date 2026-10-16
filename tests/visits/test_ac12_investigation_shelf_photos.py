"""AC12 / AC15 / AC39: live investigations must inspect before-photos.

The investigation pipeline runs the same image observation path as the
Execution Verifier for each before photo, persists the photo evidence, and
exposes the precomputed observation through the ``inspect_image`` tool so the
proposal can cite it. A failed observation produces an error envelope and no
fabricated observation.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from storeops_contracts.models import Kind, Media, Status1, Status8, ZoneKind

from apps.api.ai.gateway import ModelGatewayError
from apps.api.ai.investigator import ReadOnlyToolRegistry
from apps.api.ai.schemas import (
    AnalysisProposal,
    Detection,
    ImageObservation,
    ProposedAction,
    ProposedClaim,
)

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"shelf-photo-bytes" * 8


@pytest.fixture
def make_before_media(catalog_repo, sample_store, workspace_setup, temp_media_dir):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)

    async def _create(
        visit_id: UUID,
        zone_id: str,
        zone_kind: ZoneKind = ZoneKind.SHELF,
        with_bytes: bool = True,
    ) -> Media:
        media = Media(
            id=uuid4(),
            workspace_id=ws_id,
            version=1,
            created_at=now,
            updated_at=now,
            kind=Kind.VISIT_BEFORE,
            filename=f"{zone_id}.jpg",
            mime_type="image/jpeg",
            status=Status1.READY,
            store_id=sample_store.id,
            visit_id=visit_id,
            product_id=None,
            zone_id=zone_id,
            zone_kind=zone_kind,
            captured_at=now,
            original_sha256="a" * 64,
            normalized_sha256="a" * 64,
            byte_size=len(JPEG_BYTES),
            width=1920,
            height=1080,
            rejection=None,
            download_url=None,
            download_url_expires_at=None,
        )
        saved = await catalog_repo.create_media(media)
        if with_bytes:
            (Path(temp_media_dir) / f"{saved.id}.bin").write_bytes(JPEG_BYTES)
        return saved

    return _create


@pytest.fixture
def tool_calls(monkeypatch) -> list[dict[str, Any]]:
    """Record every read-only tool execution and its envelope."""
    calls: list[dict[str, Any]] = []
    original = ReadOnlyToolRegistry.execute

    def recording_execute(self, tool_name, caller_workspace_id, input_data):
        env = original(self, tool_name, caller_workspace_id, input_data)
        calls.append(
            {
                "tool": tool_name,
                "registered": sorted(self._tools.keys()),
                "input": dict(input_data),
                "envelope": env,
            }
        )
        return env

    monkeypatch.setattr(ReadOnlyToolRegistry, "execute", recording_execute)
    return calls


def _observation_for(prompt: str) -> ImageObservation:
    m = re.search(
        r"Analyze media ([0-9a-f-]{36}) for zone '([^']+)' \((SHELF|DISPLAY)\)",
        prompt,
    )
    assert m, prompt
    return ImageObservation(
        media_id=UUID(m.group(1)),
        zone_id=m.group(2),
        zone_kind=m.group(3),
        quality="CLEAR",
        coverage="FULL",
        occluded=False,
        detections=[],
        display="ABSENT",
        limitations=[],
    )


def _prompt_observations(prompt: str) -> list[dict[str, Any]]:
    match = re.search(r"<observations>\s*(.*?)\s*</observations>", prompt, re.DOTALL)
    assert match, "investigation prompt has no <observations> block"
    return json.loads(match.group(1))


def _citing_proposal(prompt: str) -> AnalysisProposal:
    """Cite the evidence id the prompt attaches to the shelf observation."""
    observed = [o for o in _prompt_observations(prompt) if o.get("status") == "OK"]
    assert observed, "no successful shelf observation reached the investigator"
    eid = UUID(observed[0]["evidence_ids"][0])
    return AnalysisProposal(
        hypothesis="EXECUTION",
        summary="Promotional display is absent from the audited shelf.",
        claims=[
            ProposedClaim(
                claim_key="c1",
                kind="OBSERVATION",
                text="The shelf photo shows no promotional display.",
                evidence_ids=[eid],
            )
        ],
        alternatives=[],
        actions=[
            ProposedAction(
                kind="INSTALL_DISPLAY",
                rule_ids=[],
                claim_keys=["c1"],
                evidence_ids=[eid],
                instruction="Install the promotional display on shelf-7.",
                required_zone_ids=["shelf-7"],
            )
        ],
        unresolved_questions=[],
    )


async def _run(client, headers, store_id, promo_id, visit_id, media_ids):
    res_inv = await client.post(
        "/investigations",
        json={
            "store_id": str(store_id),
            "visit_id": str(visit_id),
            "promotion_id": str(promo_id),
            "media_ids": [str(m) for m in media_ids],
        },
        headers={**headers, "Idempotency-Key": f"inv-{uuid4()}"},
    )
    assert res_inv.status_code == 202, res_inv.text
    return res_inv.json()["resource_id"]


async def _create_visit(client, headers, store_id) -> UUID:
    res_v = await client.post(
        "/visits",
        json={"store_id": str(store_id), "notes": "Promo audit"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    assert res_v.status_code == 201, res_v.text
    return UUID(res_v.json()["id"])


def _image_calls(model_gateway) -> list[dict[str, Any]]:
    return [
        c
        for c in model_gateway.call_history
        if c["response_schema"] is ImageObservation
    ]


def _proposal_prompt(model_gateway) -> str:
    prompts = [
        c["prompt"]
        for c in model_gateway.call_history
        if c["response_schema"] is AnalysisProposal
    ]
    assert len(prompts) == 1
    return prompts[0]


@pytest.mark.asyncio
async def test_investigation_inspects_before_photo_and_cites_observation(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    make_before_media,
    model_gateway,
    visit_repo,
    tool_calls,
):
    headers = workspace_setup["rep_headers"]
    ws_id = workspace_setup["workspace_id"]
    promo, policy_ver, _rule = sample_promotion_with_policy
    model_gateway.register_response(ImageObservation, _observation_for)
    model_gateway.register_response(AnalysisProposal, _citing_proposal)

    visit_id = await _create_visit(client, headers, sample_store.id)
    media = await make_before_media(visit_id, zone_id="shelf-7")
    inv_id = await _run(
        client, headers, sample_store.id, promo.id, visit_id, [media.id]
    )

    # The verifier's image-observation path ran once, with the photo bytes,
    # the media's real zone and the policy's catalog products.
    image_calls = _image_calls(model_gateway)
    assert len(image_calls) == 1
    assert image_calls[0]["images_count"] == 1
    assert (
        f"Analyze media {media.id} for zone 'shelf-7' (SHELF)"
        in image_calls[0]["prompt"]
    )
    for pid in policy_ver.catalog_product_ids:
        assert str(pid) in image_calls[0]["prompt"]

    # inspect_image is registered and called once, with the real zone id.
    inspect_calls = [c for c in tool_calls if c["tool"] == "inspect_image"]
    assert len(inspect_calls) == 1
    assert "inspect_image" in inspect_calls[0]["registered"]
    assert inspect_calls[0]["input"]["media_id"] == str(media.id)
    assert inspect_calls[0]["input"]["zone_id"] == "shelf-7"
    env = inspect_calls[0]["envelope"]
    assert env.status == Status8.OK
    assert env.data["media_id"] == str(media.id)
    assert env.data["zone_id"] == "shelf-7"
    assert env.data["display"] == "ABSENT"
    assert len(env.evidence_ids) == 1
    obs_ev_id = env.evidence_ids[0]

    # The observation evidence is persisted and points at the photo.
    stored = await visit_repo.get_evidence(ws_id, obs_ev_id)
    assert stored is not None
    assert str(stored.investigation_id) == inv_id
    assert stored.kind.value == "PHOTO"
    assert stored.source_id == media.id
    assert stored.locator.media_id == media.id
    assert "display ABSENT" in stored.summary
    assert "quality CLEAR" in stored.summary

    # The model sees the observation keyed to that evidence id.
    observations = _prompt_observations(_proposal_prompt(model_gateway))
    assert observations == [
        {
            "media_id": str(media.id),
            "zone_id": "shelf-7",
            "status": "OK",
            "evidence_ids": [str(obs_ev_id)],
            "observation": env.data,
        }
    ]

    # And the persisted proposal cites the observation evidence.
    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    assert res_get.status_code == 200, res_get.text
    inv = res_get.json()
    assert inv["state"] == "PROPOSED"
    assert inv["diagnosis"]["hypothesis"] == "EXECUTION"
    assert inv["diagnosis"]["claims"][0]["evidence_ids"] == [str(obs_ev_id)]


@pytest.mark.asyncio
async def test_investigation_inspects_every_photo_with_its_own_zone(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    make_before_media,
    model_gateway,
    tool_calls,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy
    model_gateway.register_response(ImageObservation, _observation_for)
    model_gateway.register_response(AnalysisProposal, _citing_proposal)

    visit_id = await _create_visit(client, headers, sample_store.id)
    shelf_a = await make_before_media(visit_id, zone_id="shelf-1")
    shelf_b = await make_before_media(visit_id, zone_id="shelf-1")
    display = await make_before_media(
        visit_id, zone_id="endcap-2", zone_kind=ZoneKind.DISPLAY
    )
    await _run(
        client,
        headers,
        sample_store.id,
        promo.id,
        visit_id,
        [shelf_a.id, shelf_b.id, display.id],
    )

    assert len(_image_calls(model_gateway)) == 3
    inspected = {
        (c["input"]["media_id"], c["input"]["zone_id"])
        for c in tool_calls
        if c["tool"] == "inspect_image"
    }
    assert inspected == {
        (str(shelf_a.id), "shelf-1"),
        (str(shelf_b.id), "shelf-1"),
        (str(display.id), "endcap-2"),
    }
    display_obs = [
        o
        for o in _prompt_observations(_proposal_prompt(model_gateway))
        if o["media_id"] == str(display.id)
    ]
    assert display_obs[0]["observation"]["zone_kind"] == "DISPLAY"


@pytest.mark.asyncio
async def test_failed_observation_returns_error_envelope_without_fabrication(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    make_before_media,
    model_gateway,
    visit_repo,
    tool_calls,
):
    headers = workspace_setup["rep_headers"]
    ws_id = workspace_setup["workspace_id"]
    promo, _policy_ver, _rule = sample_promotion_with_policy
    model_gateway.register_response(
        ImageObservation, ModelGatewayError("vision model unavailable")
    )

    visit_id = await _create_visit(client, headers, sample_store.id)
    media = await make_before_media(visit_id, zone_id="shelf-7")
    inv_id = await _run(
        client, headers, sample_store.id, promo.id, visit_id, [media.id]
    )

    inspect_calls = [c for c in tool_calls if c["tool"] == "inspect_image"]
    assert len(inspect_calls) == 1
    assert inspect_calls[0]["input"]["zone_id"] == "shelf-7"
    env = inspect_calls[0]["envelope"]
    assert env.status == Status8.ERROR
    assert env.data is None
    assert env.evidence_ids == []
    assert env.error is not None
    assert env.error.code == "IMAGE_OBSERVATION_FAILED"

    # The model is told visual evidence is missing; no observation is invented.
    observations = _prompt_observations(_proposal_prompt(model_gateway))
    assert len(observations) == 1
    assert observations[0]["status"] == "ERROR"
    assert observations[0]["media_id"] == str(media.id)
    assert observations[0]["zone_id"] == "shelf-7"
    assert observations[0]["evidence_ids"] == []
    assert "observation" not in observations[0]
    assert observations[0]["error"]["code"] == "IMAGE_OBSERVATION_FAILED"

    # The stored photo evidence states that no observation was derived.
    res_ev = await client.get(
        f"/investigations/{inv_id}/evidence", headers=headers
    )
    assert res_ev.status_code == 200, res_ev.text
    photo_ev = [
        e for e in res_ev.json()["items"] if e["locator"]["media_id"] == str(media.id)
    ]
    assert len(photo_ev) == 1
    assert "observation unavailable" in photo_ev[0]["summary"]
    assert "quality" not in photo_ev[0]["summary"]
    stored = await visit_repo.get_evidence(ws_id, UUID(photo_ev[0]["id"]))
    assert stored is not None


@pytest.mark.asyncio
async def test_missing_photo_bytes_returns_error_envelope(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    make_before_media,
    model_gateway,
    tool_calls,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy
    model_gateway.register_response(ImageObservation, _observation_for)

    visit_id = await _create_visit(client, headers, sample_store.id)
    media = await make_before_media(visit_id, zone_id="shelf-7", with_bytes=False)
    await _run(client, headers, sample_store.id, promo.id, visit_id, [media.id])

    assert _image_calls(model_gateway) == []
    env = next(c["envelope"] for c in tool_calls if c["tool"] == "inspect_image")
    assert env.status == Status8.ERROR
    assert env.data is None
    assert env.error.code == "MEDIA_BYTES_UNAVAILABLE"


@pytest.mark.asyncio
async def test_detections_survive_into_the_tool_envelope(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_product,
    make_before_media,
    model_gateway,
    tool_calls,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy

    def _with_detection(prompt: str) -> ImageObservation:
        base = _observation_for(prompt)
        return base.model_copy(
            update={
                "display": "PRESENT",
                "detections": [
                    Detection(
                        product_id=sample_product.id,
                        view="FRONT",
                        box=[100, 100, 300, 300],
                        identity="CLEAR",
                        label="Artisan Dark Chocolate 100g",
                    )
                ],
            }
        )

    model_gateway.register_response(ImageObservation, _with_detection)
    model_gateway.register_response(AnalysisProposal, _citing_proposal)

    visit_id = await _create_visit(client, headers, sample_store.id)
    media = await make_before_media(visit_id, zone_id="shelf-7")
    await _run(client, headers, sample_store.id, promo.id, visit_id, [media.id])

    env = next(c["envelope"] for c in tool_calls if c["tool"] == "inspect_image")
    assert env.status == Status8.OK
    assert env.data["detections"][0]["product_id"] == str(sample_product.id)
    assert env.data["detections"][0]["identity"] == "CLEAR"


def test_inspect_handler_without_evidence_mapping_returns_scope_error_not_crash():
    """A desync between observations and evidence ids must not raise KeyError (500)."""
    from apps.api.modules.visits.shelf_observations import (
        ShelfObservation,
        build_inspect_image_handler,
    )

    media_id = uuid4()
    observed = ShelfObservation(
        media_id=media_id, zone_id="shelf-7", zone_kind="SHELF", observation=None, error=None
    )
    handler = build_inspect_image_handler({media_id: observed}, {}, datetime.now(UTC))
    env = handler({"media_id": str(media_id), "zone_id": "shelf-7", "reference_media_ids": [str(media_id)]})
    assert env.status == Status8.ERROR
    assert env.error.code == "MEDIA_NOT_IN_SCOPE"
