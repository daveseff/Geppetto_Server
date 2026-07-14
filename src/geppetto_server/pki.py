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
    elif not _ca_cert_is_usable(settings.ca_cert):
        LOGGER.warning("existing CA certificate is missing required CA extensions; regenerating server PKI")
        reset_server_pki(settings)
        return
    if not settings.server_cert.exists() or not settings.server_key.exists():
        LOGGER.info("initializing server certificate cert=%s key=%s", settings.server_cert, settings.server_key)
        _generate_server_cert(settings)
    elif not _server_cert_matches_settings(settings):
        LOGGER.warning("existing server certificate does not match configured DNS names; regenerating server certificate")
        _remove_server_cert(settings)
        _generate_server_cert(settings)


def reset_server_pki(settings: Settings) -> None:
    for path in (
        settings.ca_cert,
        settings.ca_key,
        settings.server_cert,
        settings.server_key,
        settings.ca_cert.with_suffix(".srl"),
        settings.server_cert.with_suffix(".csr"),
        settings.server_cert.with_suffix(".ext"),
    ):
        path.unlink(missing_ok=True)
    if settings.signed_cert_dir.exists():
        for cert_path in settings.signed_cert_dir.glob("*.crt"):
            cert_path.unlink()
    ensure_server_pki(settings)


def _remove_server_cert(settings: Settings) -> None:
    for path in (
        settings.server_cert,
        settings.server_key,
        settings.server_cert.with_suffix(".csr"),
        settings.server_cert.with_suffix(".ext"),
    ):
        path.unlink(missing_ok=True)


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
    csr_path.unlink()
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
    ca_ext = ca_cert.with_suffix(".ext")
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
    ca_ext.write_text(
        "\n".join(
            [
                "basicConstraints=critical,CA:TRUE,pathlen:1",
                "keyUsage=critical,keyCertSign,cRLSign",
                "subjectKeyIdentifier=hash",
                "",
            ]
        )
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
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:1",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
            "-out",
            str(ca_cert),
        ],
        "generate CA certificate",
    )
    ca_ext.unlink(missing_ok=True)
    _chmod_key(ca_key)
    _chmod_cert(ca_cert)


def _generate_server_cert(settings: Settings) -> None:
    dns_names = _server_dns_names(settings)
    server_name = dns_names[0]
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
                "subjectAltName=" + ",".join(f"DNS:{name}" for name in dns_names),
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


def _server_dns_names(settings: Settings) -> list[str]:
    primary = (settings.server_name or socket.getfqdn() or socket.gethostname()).strip()
    candidates = [primary, *settings.server_alt_names]
    if "." in primary:
        candidates.append(primary.split(".", 1)[0])
    fqdn = socket.getfqdn().strip()
    hostname = socket.gethostname().strip()
    candidates.extend([fqdn, hostname])
    names: list[str] = []
    for name in candidates:
        if name and name not in names:
            names.append(name)
    return names


def _server_cert_matches_settings(settings: Settings) -> bool:
    result = subprocess.run(
        ["openssl", "x509", "-in", str(settings.server_cert), "-noout", "-text"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    text = result.stdout
    return all(f"DNS:{name}" in text for name in _server_dns_names(settings))


def _run_openssl(cmd: list[str], action: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"failed to {action}: {detail}")


def _ca_cert_is_usable(ca_cert: Path) -> bool:
    result = subprocess.run(
        ["openssl", "x509", "-in", str(ca_cert), "-noout", "-text"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    text = result.stdout
    return "CA:TRUE" in text and "Certificate Sign" in text and "CRL Sign" in text


def _cert_names(directory: Path, suffix: str) -> list[str]:
    try:
        directory.stat()
    except FileNotFoundError:
        return []
    except PermissionError as exc:
        raise PermissionError(
            f"cannot access certificate directory {directory}; run this command as root or geppetto-server"
        ) from exc
    if not directory.is_dir():
        raise NotADirectoryError(f"certificate path is not a directory: {directory}")
    try:
        return sorted(path.stem for path in directory.iterdir() if path.is_file() and path.name.endswith(suffix))
    except PermissionError as exc:
        raise PermissionError(
            f"cannot read certificate directory {directory}; run this command as root or geppetto-server"
        ) from exc


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
