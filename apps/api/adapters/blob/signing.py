"""HMAC-signed, expiring URLs for the API-mediated media byte routes.

PUT /media/upload/{id} and GET /media/download/{id} carry no auth header (the
browser loads downloads in <img src>; seed and web clients PUT to the URL the API
returned). Access is granted by the URL itself:

    ?expires=<unix seconds>&sig=<hex HMAC-SHA256(key, "<METHOD>:<media_id>:<expires>")>

The method binds a signature to one route, the media id to one asset, and the
expiry to a time window.
"""

import hashlib
import hmac
import time
from collections.abc import Callable
from urllib.parse import urlencode
from uuid import UUID

from apps.api.core.config import ConfigurationError

UPLOAD_METHOD = "PUT"
DOWNLOAD_METHOD = "GET"
UPLOAD_URL_TTL_SECONDS = 15 * 60
MIN_CLOUD_KEY_LENGTH = 32

# LOCAL/test profile only: a fixed, publicly known development key so local runs and
# tests work without configuration. It protects nothing; PROFILE=CLOUD never uses it
# (resolve_signing_key raises instead).
LOCAL_DEV_SIGNING_KEY = b"storeops-local-dev-media-url-signing-key"


def resolve_signing_key(profile: str, configured_key: str | None) -> bytes:
    """MEDIA_URL_SIGNING_KEY; required (>= 32 chars) for CLOUD, dev fallback otherwise."""
    if configured_key:
        if profile.upper() == "CLOUD" and len(configured_key) < MIN_CLOUD_KEY_LENGTH:
            raise ConfigurationError(
                f"MEDIA_URL_SIGNING_KEY must be at least {MIN_CLOUD_KEY_LENGTH} characters "
                "for PROFILE=CLOUD"
            )
        return configured_key.encode()
    if profile.upper() == "CLOUD":
        raise ConfigurationError("PROFILE=CLOUD requires MEDIA_URL_SIGNING_KEY to sign media URLs")
    return LOCAL_DEV_SIGNING_KEY


class MediaUrlSigner:
    def __init__(self, key: bytes, clock: Callable[[], float] = time.time) -> None:
        if not key:
            raise ValueError("Media URL signing key must not be empty")
        self._key = key
        self._clock = clock

    def _signature(self, method: str, media_id: UUID, expires: int) -> str:
        message = f"{method}:{media_id}:{expires}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def query(self, method: str, media_id: UUID, ttl_seconds: int) -> str:
        """Query string granting `method` on `media_id` for ttl_seconds from now."""
        expires = int(self._clock()) + ttl_seconds
        return urlencode({"expires": expires, "sig": self._signature(method, media_id, expires)})

    def signed_url(self, base_url: str, method: str, media_id: UUID, ttl_seconds: int) -> str:
        route = "upload" if method == UPLOAD_METHOD else "download"
        return f"{base_url}/{route}/{media_id}?{self.query(method, media_id, ttl_seconds)}"

    def verify(
        self, method: str, media_id: UUID, expires: str | None, signature: str | None
    ) -> bool:
        if not expires or not signature or not expires.isdigit():
            return False
        expires_at = int(expires)
        if expires_at < self._clock():
            return False
        expected = self._signature(method, media_id, expires_at)
        return hmac.compare_digest(expected, signature)
