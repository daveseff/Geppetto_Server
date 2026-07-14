from __future__ import annotations

from pathlib import Path

import subprocess

from geppetto_server.pki import clean_agent_cert, ensure_server_pki, list_certs, reset_server_pki, sign_agent_cert
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
        server_alt_names=("config",),
    )


def test_ensure_server_pki_generates_missing_material(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    ensure_server_pki(settings)

    assert settings.ca_cert.exists()
    assert settings.ca_key.exists()
    assert settings.server_cert.exists()
    assert settings.server_key.exists()


def test_generated_ca_has_key_cert_sign_usage(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    ensure_server_pki(settings)

    result = subprocess.run(
        ["openssl", "x509", "-in", str(settings.ca_cert), "-noout", "-text"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "CA:TRUE" in result.stdout
    assert "Certificate Sign" in result.stdout
    assert "CRL Sign" in result.stdout


def test_generated_server_cert_includes_configured_alt_names(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    ensure_server_pki(settings)

    result = subprocess.run(
        ["openssl", "x509", "-in", str(settings.server_cert), "-noout", "-text"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "DNS:config.example.invalid" in result.stdout
    assert "DNS:config" in result.stdout


def test_ensure_server_pki_repairs_server_cert_with_missing_alt_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("geppetto_server.pki.socket.getfqdn", lambda: "local.invalid")
    monkeypatch.setattr("geppetto_server.pki.socket.gethostname", lambda: "local")
    old_settings = Settings(
        config_root=tmp_path / "config",
        server_cert=tmp_path / "pki/server.crt",
        server_key=tmp_path / "pki/server.key",
        ca_cert=tmp_path / "pki/ca.crt",
        ca_key=tmp_path / "pki/ca.key",
        pending_csr_dir=tmp_path / "csr_pending",
        signed_cert_dir=tmp_path / "certs",
        log_file=tmp_path / "geppetto-server.log",
        server_name="saturn",
    )
    ensure_server_pki(old_settings)
    old_ca = old_settings.ca_cert.read_text()
    old_server_cert = old_settings.server_cert.read_text()
    new_settings = Settings(
        config_root=old_settings.config_root,
        server_cert=old_settings.server_cert,
        server_key=old_settings.server_key,
        ca_cert=old_settings.ca_cert,
        ca_key=old_settings.ca_key,
        pending_csr_dir=old_settings.pending_csr_dir,
        signed_cert_dir=old_settings.signed_cert_dir,
        log_file=old_settings.log_file,
        server_name="saturn",
        server_alt_names=("saturn.solar1.net",),
    )

    ensure_server_pki(new_settings)

    result = subprocess.run(
        ["openssl", "x509", "-in", str(new_settings.server_cert), "-noout", "-text"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert new_settings.ca_cert.read_text() == old_ca
    assert new_settings.server_cert.read_text() != old_server_cert
    assert "DNS:saturn" in result.stdout
    assert "DNS:saturn.solar1.net" in result.stdout


def test_reset_server_pki_replaces_existing_material(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    ensure_server_pki(settings)
    settings.signed_cert_dir.mkdir(parents=True)
    stale_agent_cert = settings.signed_cert_dir / "host1.crt"
    stale_agent_cert.write_text("old")
    old_ca = settings.ca_cert.read_text()

    reset_server_pki(settings)

    assert settings.ca_cert.exists()
    assert settings.server_cert.exists()
    assert settings.ca_cert.read_text() != old_ca
    assert not stale_agent_cert.exists()


def test_ensure_server_pki_repairs_ca_without_key_usage(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ca_cert.parent.mkdir(parents=True)
    settings.signed_cert_dir.mkdir(parents=True)
    stale_agent_cert = settings.signed_cert_dir / "host1.crt"
    stale_agent_cert.write_text("old")

    subprocess.run(["openssl", "genrsa", "-out", str(settings.ca_key), "2048"], check=True, capture_output=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(settings.ca_key),
            "-sha256",
            "-days",
            "3650",
            "-subj",
            "/CN=Bad Geppetto CA",
            "-out",
            str(settings.ca_cert),
        ],
        check=True,
        capture_output=True,
    )

    ensure_server_pki(settings)

    result = subprocess.run(
        ["openssl", "x509", "-in", str(settings.ca_cert), "-noout", "-text"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Certificate Sign" in result.stdout
    assert "CRL Sign" in result.stdout
    assert settings.server_cert.exists()
    assert not stale_agent_cert.exists()


def test_list_certs_reports_pending_and_signed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.pending_csr_dir.mkdir(parents=True)
    settings.signed_cert_dir.mkdir(parents=True)
    (settings.pending_csr_dir / "host1.csr").write_text("csr")
    (settings.signed_cert_dir / "host2.crt").write_text("cert")

    inventory = list_certs(settings)

    assert inventory.pending == ["host1"]
    assert inventory.signed == ["host2"]


def test_list_certs_reports_unreadable_directory(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    original_stat = Path.stat

    def deny_stat(path, *args, **kwargs):
        if path == settings.pending_csr_dir:
            raise PermissionError("denied")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_stat)

    try:
        list_certs(settings)
    except PermissionError as exc:
        assert "run this command as root or geppetto-server" in str(exc)
    else:
        raise AssertionError("expected PermissionError")


def test_sign_agent_cert_requires_pending_csr(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    try:
        sign_agent_cert(settings, "host1")
    except FileNotFoundError as exc:
        assert "pending CSR not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_sign_agent_cert_removes_pending_csr_after_success(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    ensure_server_pki(settings)
    settings.pending_csr_dir.mkdir(parents=True)
    agent_key = tmp_path / "host1.key"
    pending = settings.pending_csr_dir / "host1.csr"

    subprocess.run(["openssl", "genrsa", "-out", str(agent_key), "2048"], check=True, capture_output=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-key",
            str(agent_key),
            "-subj",
            "/CN=host1",
            "-out",
            str(pending),
        ],
        check=True,
        capture_output=True,
    )

    cert_path = sign_agent_cert(settings, "host1")
    inventory = list_certs(settings)

    assert cert_path == settings.signed_cert_dir / "host1.crt"
    assert cert_path.exists()
    assert not pending.exists()
    assert inventory.pending == []
    assert inventory.signed == ["host1"]


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
