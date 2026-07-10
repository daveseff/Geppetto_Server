from __future__ import annotations

from pathlib import Path

from geppetto_server.pki import clean_agent_cert, ensure_server_pki, list_certs, sign_agent_cert
from geppetto_server.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        config_root=tmp_path / "config",
        server_cert=tmp_path / "pki/server.crt",
        server_key=tmp_path / "pki/server.key",
        ca_cert=tmp_path / "pki/ca.crt",
        ca_key=tmp_path / "pki/ca.key",
        pending_csr_dir=tmp_path / "csr_pending",
        signed_cert_dir=tmp_path / "certs",
        log_file=tmp_path / "geppetto-server.log",
        server_name="config.example.invalid",
    )


def test_ensure_server_pki_generates_missing_material(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    ensure_server_pki(settings)

    assert settings.ca_cert.exists()
    assert settings.ca_key.exists()
    assert settings.server_cert.exists()
    assert settings.server_key.exists()


def test_list_certs_reports_pending_and_signed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.pending_csr_dir.mkdir(parents=True)
    settings.signed_cert_dir.mkdir(parents=True)
    (settings.pending_csr_dir / "host1.csr").write_text("csr")
    (settings.signed_cert_dir / "host2.crt").write_text("cert")

    inventory = list_certs(settings)

    assert inventory.pending == ["host1"]
    assert inventory.signed == ["host2"]


def test_sign_agent_cert_requires_pending_csr(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    try:
        sign_agent_cert(settings, "host1")
    except FileNotFoundError as exc:
        assert "pending CSR not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_clean_agent_cert_removes_pending_and_signed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.pending_csr_dir.mkdir(parents=True)
    settings.signed_cert_dir.mkdir(parents=True)
    pending = settings.pending_csr_dir / "host1.csr"
    signed = settings.signed_cert_dir / "host1.crt"
    pending.write_text("csr")
    signed.write_text("cert")

    removed = clean_agent_cert(settings, "host1")

    assert removed == [pending, signed]
    assert not pending.exists()
    assert not signed.exists()
