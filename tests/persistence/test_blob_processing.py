"""Storage-independent media normalization shared by local and GCS blob adapters."""

import hashlib
import struct

import pytest

from apps.api.adapters.blob.processing import normalize_asset, resolve_media_base_url

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _truncated_png(width: int, height: int) -> bytes:
    return PNG_SIG + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x00" * 8


def _truncated_jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width)
    return b"\xff\xd8" + app0 + sof0 + b"\x00" * 16


def test_truncated_png_uses_header_dimensions():
    asset = normalize_asset(_truncated_png(300, 200))
    assert asset.dimensions == (300, 200)
    assert asset.sha256 == hashlib.sha256(_truncated_png(300, 200)).hexdigest()


def test_truncated_jpeg_uses_sof_dimensions():
    assert normalize_asset(_truncated_jpeg(640, 480)).dimensions == (640, 480)


def test_truncated_png_over_long_edge_rejected():
    with pytest.raises(ValueError, match="2048"):
        normalize_asset(_truncated_png(4096, 10))


def test_png_without_readable_header_rejected():
    with pytest.raises(ValueError, match="dimensions"):
        normalize_asset(PNG_SIG + b"\x00" * 4)


def test_pdf_over_limit_rejected():
    with pytest.raises(ValueError, match="PDF exceeds"):
        normalize_asset(b"%PDF" + b"\x00" * (10 * 1024 * 1024))


def test_generic_asset_over_limit_rejected():
    with pytest.raises(ValueError, match="Asset exceeds"):
        normalize_asset(b"sku,units\n" + b"x" * (10 * 1024 * 1024))


def test_csv_passes_through_unchanged():
    raw = b"sku,units\nA,1\n"
    asset = normalize_asset(raw)
    assert (asset.data, asset.size, asset.dimensions) == (raw, len(raw), None)


def test_base_url_prefers_media_base_url(monkeypatch):
    monkeypatch.setenv("MEDIA_BASE_URL", "https://a.example/media/")
    monkeypatch.setenv("API_URL", "https://b.example")
    assert resolve_media_base_url("http://default/media") == "https://a.example/media"


def test_base_url_falls_back_to_api_url_then_default(monkeypatch):
    monkeypatch.delenv("MEDIA_BASE_URL", raising=False)
    monkeypatch.setenv("API_URL", "https://b.example/")
    assert resolve_media_base_url("http://default/media") == "https://b.example/media"
    monkeypatch.delenv("API_URL")
    assert resolve_media_base_url("http://default/media/") == "http://default/media"
