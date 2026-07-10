from __future__ import annotations

import logging
import os
import pwd
import grp
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .settings import Settings


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CertInventory:
    pending: list[str]
    signed: list[str]


def ensure_server_pki(settings: Settings) -> None:
    settings.server_cert.parent.mkdir(parents=True, exist_ok=True)
    if not settings.ca_cert.exists() or not settings.ca_key.exists():
        LOGGER.info("initializing CA cert=%s key=%s", settings.ca_cert, settings.ca_key)
        _generate_ca(settings.ca_cert, settings.ca_key)
    if not settings.server_cert.exists() or not settings.server_key.exists():
        LOGGER.info("initializing server certificate cert=%s key=%s", settings.server_cert, settings.server_key)
        _generate_server_cert(settings)


def list_certs(settings: Settings) -> CertInventory:
    pending = _cert_names(settings.pending_csr_dir, ".csr")
    signed = _cert_names(settings.signed_cert_dir, ".crt")
    return CertInventory(pending=pending, signed=signed)


def sign_agent_cert(settings: Settings, host_name: str) -> Path:
    _validate_host_name(host_name)
    csr_path = settings.pending_csr_dir / f"{host_name}.csr"
    cert_path = settings.signed_cert_dir / f"{host_name}.crt"
    if not csr_path.exists():
        raise FileNotFoundError(f"pending CSR not found: {csr_path}")
    if not settings.ca_cert.exists() or not settings.ca_key.exists():
        raise FileNotFoundError("CA is not initialized; run `geppetto-config-server init` first")
    settings.signed_cert_dir.mkdir(parents=True, exist_ok=True)
    sign_csr(csr_path, cert_path, settings.ca_cert, settings.ca_key)
    _chmod_cert(cert_path)
    return cert_path


def clean_agent_cert(settings: Settings, host_name: str) -> list[Path]:
    _validate_host_name(host_name)
    removed: list[Path] = []
    for path in (
        settings.pending_csr_dir / f"{host_name}.csr",
        settings.signed_cert_dir / f"{host_name}.crt",
    ):
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def sign_csr(csr_path: Path, cert_path: Path, ca_cert: Path, ca_key: Path) -> None:
    result = subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr_path),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(cert_path),
            "-days",
            "825",
            "-sha256",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"failed to sign CSR: {detail}")


def csr_common_name(csr: bytes) -> str:
    with tempfile.NamedTemporaryFile() as csr_file:
        csr_file.write(csr)
        csr_file.flush()
        result = subprocess.run(
            ["openssl", "req", "-in", csr_file.name, "-noout", "-subject"],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise ValueError("invalid CSR")
    import re

    match = re.search(r"(?:^|[ /,=])CN\s*=\s*([^/,]+)", result.stdout.strip())
    if not match:
        raise ValueError("CSR does not contain a common name")
    return match.group(1).strip()


def _generate_ca(ca_cert: Path, ca_key: Path) -> None:
    ca_cert.parent.mkdir(parents=True, exist_ok=True)
    _run_openssl(
        [
            "openssl",
            "genrsa",
            "-out",
            str(ca_key),
            "4096",
        ],
        "generate CA key",
    )
    _run_openssl(
        [
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(ca_key),
            "-sha256",
            "-days",
            "3650",
            "-subj",
            "/CN=Geppetto Config CA",
            "-out",
            str(ca_cert),
        ],
        "generate CA certificate",
    )
    _chmod_key(ca_key)
    _chmod_cert(ca_cert)


def _generate_server_cert(settings: Settings) -> None:
    server_name = settings.server_name or socket.getfqdn()
    csr_path = settings.server_cert.with_suffix(".csr")
    ext_path = settings.server_cert.with_suffix(".ext")
    _run_openssl(["openssl", "genrsa", "-out", str(settings.server_key), "4096"], "generate server key")
    _run_openssl(
        ["openssl", "req", "-new", "-key", str(settings.server_key), "-subj", f"/CN={server_name}", "-out", str(csr_path)],
        "generate server CSR",
    )
    ext_path.write_text(
        "\n".join(
            [
                "basicConstraints=CA:FALSE",
                "keyUsage=digitalSignature,keyEncipherment",
                "extendedKeyUsage=serverAuth",
                f"subjectAltName=DNS:{server_name}",
                "",
            ]
        )
    )
    _run_openssl(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr_path),
            "-CA",
            str(settings.ca_cert),
            "-CAkey",
            str(settings.ca_key),
            "-CAcreateserial",
            "-out",
            str(settings.server_cert),
            "-days",
            "825",
            "-sha256",
            "-extfile",
            str(ext_path),
        ],
        "sign server certificate",
    )
    csr_path.unlink(missing_ok=True)
    ext_path.unlink(missing_ok=True)
    _chmod_key(settings.server_key)
    _chmod_cert(settings.server_cert)


def _run_openssl(cmd: list[str], action: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"failed to {action}: {detail}")


def _cert_names(directory: Path, suffix: str) -> list[str]:
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob(f"*{suffix}") if path.is_file())


def _validate_host_name(host_name: str) -> None:
    import re

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", host_name):
        raise ValueError(f"invalid host name: {host_name}")


def _chmod_key(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
        _chown_server_user(path)
    except OSError:
        LOGGER.warning("unable to chmod private key %s", path)


def _chmod_cert(path: Path) -> None:
    try:
        os.chmod(path, 0o644)
        _chown_server_user(path)
    except OSError:
        LOGGER.warning("unable to chmod certificate %s", path)


def _chown_server_user(path: Path) -> None:
    try:
        uid = pwd.getpwnam("geppetto-server").pw_uid
        gid = grp.getgrnam("geppetto-server").gr_gid
    except KeyError:
        return
    try:
        os.chown(path, uid, gid)
    except OSError:
        LOGGER.warning("unable to chown %s to geppetto-server", path)
