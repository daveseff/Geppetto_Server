from __future__ import annotations

import ssl
from pathlib import Path

from geppetto_server.server import build_ssl_context, extract_common_name
from geppetto_server.settings import Settings


def test_extract_common_name_from_peer_cert() -> None:
    cert = {"subject": ((("commonName", "host1"),),)}
    assert extract_common_name(cert) == "host1"


def test_extract_common_name_returns_none_when_absent() -> None:
    assert extract_common_name({}) is None


def test_build_ssl_context_requires_client_auth(tmp_path: Path) -> None:
    settings = Settings(
        config_root=tmp_path / "config",
        server_cert=tmp_path / "server.crt",
        server_key=tmp_path / "server.key",
        ca_cert=tmp_path / "ca.crt",
        bind_host="127.0.0.1",
        bind_port=8443,
    )
    loaded: dict[str, str] = {}

    class FakeContext:
        def __init__(self) -> None:
            self.verify_mode = None

        def load_cert_chain(self, certfile: str, keyfile: str) -> None:
            loaded["certfile"] = certfile
            loaded["keyfile"] = keyfile

        def load_verify_locations(self, cafile: str) -> None:
            loaded["cafile"] = cafile

    fake_context = FakeContext()
    original = ssl.create_default_context
    ssl.create_default_context = lambda purpose: fake_context  # type: ignore[assignment]
    try:
        context = build_ssl_context(settings)
    finally:
        ssl.create_default_context = original  # type: ignore[assignment]

    assert context is fake_context
    assert fake_context.verify_mode == ssl.CERT_REQUIRED
    assert loaded == {
        "certfile": str(settings.server_cert),
        "keyfile": str(settings.server_key),
        "cafile": str(settings.ca_cert),
    }
