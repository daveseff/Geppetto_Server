from __future__ import annotations

import re
import ssl
from pathlib import Path

from geppetto_server.server import build_ssl_context, extract_common_name, match_request_path, routed_paths
from geppetto_server.settings import Settings, load_settings


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
        ca_key=tmp_path / "ca.key",
        pending_csr_dir=tmp_path / "csr_pending",
        signed_cert_dir=tmp_path / "certs",
        log_file=tmp_path / "geppetto-server.log",
        server_name="config.example.invalid",
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
    assert fake_context.verify_mode == ssl.CERT_OPTIONAL
    assert loaded == {
        "certfile": str(settings.server_cert),
        "keyfile": str(settings.server_key),
        "cafile": str(settings.ca_cert),
    }


def test_load_settings_defaults_to_server_etc_tree(monkeypatch) -> None:
    for key in (
        "GEPPETTO_SERVER_BASE",
        "GEPPETTO_CONFIG_ROOT",
        "GEPPETTO_SERVER_CERT",
        "GEPPETTO_SERVER_KEY",
        "GEPPETTO_CA_CERT",
        "GEPPETTO_CA_KEY",
        "GEPPETTO_PENDING_CSR_DIR",
        "GEPPETTO_SIGNED_CERT_DIR",
        "GEPPETTO_SERVER_ALT_NAMES",
        "GEPPETTO_SERVER_ENV",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.config_root == Path("/etc/geppetto_server/config")
    assert settings.server_cert == Path("/etc/geppetto_server/pki/server.crt")
    assert settings.server_key == Path("/etc/geppetto_server/pki/server.key")
    assert settings.ca_cert == Path("/etc/geppetto_server/pki/ca.crt")
    assert settings.ca_key == Path("/etc/geppetto_server/pki/ca.key")
    assert settings.pending_csr_dir == Path("/etc/geppetto_server/csr_pending")
    assert settings.signed_cert_dir == Path("/etc/geppetto_server/certs")
    assert settings.log_file == Path("/var/log/geppetto/geppetto-server.log")
    assert settings.path_prefix == ""
    assert settings.server_alt_names == ()


def test_load_settings_reads_server_alt_names(monkeypatch) -> None:
    monkeypatch.setenv("GEPPETTO_SERVER_ALT_NAMES", "saturn.solar1.net, saturn")

    settings = load_settings()

    assert settings.server_alt_names == ("saturn.solar1.net", "saturn")


def test_load_settings_normalizes_path_prefix(monkeypatch) -> None:
    monkeypatch.setenv("GEPPETTO_SERVER_PATH_PREFIX", "geppetto/")

    settings = load_settings()

    assert settings.path_prefix == "/geppetto"


def test_load_settings_reads_env_file(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / "geppetto-server.env"
    env_file.write_text(
        "\n".join(
            [
                "GEPPETTO_SERVER_BASE=/srv/geppetto_server",
                "GEPPETTO_SERVER_NAME=saturn",
                "GEPPETTO_SERVER_PATH_PREFIX=/geppetto/",
                "GEPPETTO_SERVER_ALT_NAMES=saturn.solar1.net,saturn",
                "GEPPETTO_SERVER_PORT=9443",
                "",
            ]
        )
    )
    monkeypatch.setenv("GEPPETTO_SERVER_ENV", str(env_file))
    monkeypatch.delenv("GEPPETTO_SERVER_BASE", raising=False)

    settings = load_settings()

    assert settings.config_root == Path("/srv/geppetto_server/config")
    assert settings.pending_csr_dir == Path("/srv/geppetto_server/csr_pending")
    assert settings.server_name == "saturn"
    assert settings.path_prefix == "/geppetto"
    assert settings.server_alt_names == ("saturn.solar1.net", "saturn")
    assert settings.bind_port == 9443


def test_environment_overrides_env_file(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / "geppetto-server.env"
    env_file.write_text("GEPPETTO_SERVER_BASE=/srv/geppetto_server\n")
    monkeypatch.setenv("GEPPETTO_SERVER_ENV", str(env_file))
    monkeypatch.setenv("GEPPETTO_SERVER_BASE", "/override/geppetto_server")

    settings = load_settings()

    assert settings.config_root == Path("/override/geppetto_server/config")


def test_routed_paths_accepts_root_and_prefixed_routes() -> None:
    assert routed_paths("/v1/ca?download=1", "") == ("/v1/ca",)
    assert routed_paths("/geppetto/v1/ca", "/geppetto") == ("/geppetto/v1/ca", "/v1/ca")
    assert routed_paths("/health", "/geppetto") == ("/health",)


def test_match_request_path_uses_prefixed_route_when_available() -> None:
    match = match_request_path(
        routed_paths("/geppetto/v1/configs/host1/bundle", "/geppetto"),
        re.compile(r"^/v1/configs/([^/]+)/bundle$"),
    )

    assert match is not None
    assert match.group(1) == "host1"
