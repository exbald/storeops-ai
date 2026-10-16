"""Before-photo observation for investigations.

Runs the same image-observation path as the Execution Verifier
(``extract_image_observations``) for each before photo, then serves the
precomputed results through the synchronous ``inspect_image`` read-only tool.
A failed observation yields an ERROR envelope; no observation is fabricated.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from storeops_contracts.models import (
    Error1,
    InspectImageToolInput,
    Media,
    Status8,
    ToolEnvelope,
)

from apps.api.ai.extract import extract_image_observations
from apps.api.ai.gateway import ModelGatewayError
from apps.api.ai.schemas import ImageObservation
from apps.api.ports.blob import BlobRepository
from apps.api.ports.model import ModelGateway

logger = logging.getLogger(__name__)

# Same fallbacks the verifier uses for media without zone metadata.
UNASSIGNED_ZONE_ID = "unassigned-zone"
DEFAULT_ZONE_KIND = "SHELF"


@dataclass(frozen=True)
class ShelfObservation:
    """Outcome of observing one before photo: an observation or an error."""

    media_id: UUID
    zone_id: str
    zone_kind: str
    observation: ImageObservation | None
    error: Error1 | None


def media_zone(media: Media | None) -> tuple[str, str]:
    """Return the media's real (zone_id, zone_kind) with verifier fallbacks."""
    if media is None:
        return UNASSIGNED_ZONE_ID, DEFAULT_ZONE_KIND
    zone_id = media.zone_id or UNASSIGNED_ZONE_ID
    zone_kind = media.zone_kind.value if media.zone_kind else DEFAULT_ZONE_KIND
    return zone_id, zone_kind


def _failed(media_id: UUID, zone: tuple[str, str], code: str, message: str) -> ShelfObservation:
    return ShelfObservation(
        media_id=media_id,
        zone_id=zone[0],
        zone_kind=zone[1],
        observation=None,
        error=Error1(code=code, message=message[:500], retryable=True),
    )


async def observe_before_photo(
    gateway: ModelGateway,
    blob_repo: BlobRepository | None,
    media_id: UUID,
    media: Media | None,
    catalog_product_ids: list[UUID],
) -> ShelfObservation:
    """Load the photo bytes and run the verifier's image observation."""
    zone = media_zone(media)
    if media is None:
        return _failed(media_id, zone, "MEDIA_NOT_FOUND", f"Media {media_id} not found")
    if blob_repo is None:
        return _failed(
            media_id, zone, "MEDIA_BYTES_UNAVAILABLE", "No blob repository configured"
        )
    try:
        raw_bytes = await blob_repo.read_bytes(media_id)
    except (OSError, RuntimeError) as err:
        logger.warning(f"Could not read blob bytes for media {media_id}: {err}")
        return _failed(
            media_id, zone, "MEDIA_BYTES_UNAVAILABLE", f"Photo bytes unreadable: {err}"
        )
    if not raw_bytes:
        return _failed(media_id, zone, "MEDIA_BYTES_UNAVAILABLE", "Photo is empty")

    try:
        obs = await extract_image_observations(
            gateway=gateway,
            image_bytes=raw_bytes,
            media_id=media_id,
            zone_id=zone[0],
            zone_kind=zone[1],
            catalog_product_ids=catalog_product_ids,
        )
    except (ModelGatewayError, ValidationError, ValueError, KeyError) as err:
        logger.warning(f"Could not extract image observations for media {media_id}: {err}")
        return _failed(
            media_id, zone, "IMAGE_OBSERVATION_FAILED", f"Image observation failed: {err}"
        )

    if obs.media_id != media_id:
        return _failed(
            media_id,
            zone,
            "IMAGE_OBSERVATION_FAILED",
            f"Observation returned for media {obs.media_id}, expected {media_id}",
        )
    return ShelfObservation(
        media_id=media_id,
        zone_id=zone[0],
        zone_kind=zone[1],
        observation=obs,
        error=None,
    )


def observation_summary(media_id: UUID, result: ShelfObservation) -> str:
    """Evidence summary for a before photo, stating what was (not) observed."""
    head = f"Before shelf photograph {media_id} (zone {result.zone_id}, {result.zone_kind})"
    obs = result.observation
    if obs is None:
        reason = result.error.message if result.error else "unknown error"
        return f"{head}; observation unavailable: {reason}"[:1000]
    limitations = "; ".join(obs.limitations) if obs.limitations else "none"
    return (
        f"{head}; quality {obs.quality}, coverage {obs.coverage}, "
        f"occluded {str(obs.occluded).lower()}, display {obs.display}, "
        f"{len(obs.detections)} detections; limitations: {limitations}"
    )[:1000]


def _error_envelope(as_of: datetime, error: Error1) -> ToolEnvelope:
    return ToolEnvelope(
        status=Status8.ERROR, data=None, evidence_ids=[], as_of=as_of, error=error
    )


def build_inspect_image_handler(
    results: dict[UUID, ShelfObservation],
    evidence_by_media: dict[UUID, UUID],
    as_of: datetime,
) -> Callable[[dict[str, Any]], ToolEnvelope]:
    """Serve precomputed observations; the server binds media and zone scope."""

    def handler(input_data: dict[str, Any]) -> ToolEnvelope:
        try:
            inp = InspectImageToolInput.model_validate(input_data)
        except ValidationError as err:
            return _error_envelope(
                as_of,
                Error1(code="INVALID_INPUT", message=str(err)[:500], retryable=False),
            )
        result = results.get(inp.media_id)
        evidence_id = evidence_by_media.get(inp.media_id)
        if result is None or evidence_id is None or result.zone_id != inp.zone_id:
            return _error_envelope(
                as_of,
                Error1(
                    code="MEDIA_NOT_IN_SCOPE",
                    message=f"Media {inp.media_id} in zone {inp.zone_id} is not part of this investigation",
                    retryable=False,
                ),
            )
        if result.observation is None:
            return _error_envelope(
                as_of,
                result.error
                or Error1(
                    code="IMAGE_OBSERVATION_FAILED",
                    message="No observation available",
                    retryable=True,
                ),
            )
        return ToolEnvelope(
            status=Status8.OK,
            data=result.observation.model_dump(mode="json"),
            evidence_ids=[evidence_id],
            as_of=as_of,
            error=None,
        )

    return handler
