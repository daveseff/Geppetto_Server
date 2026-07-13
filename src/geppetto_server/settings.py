from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    config_root: Path
    server_cert: Path
    server_key: Path
    ca_cert: Path
    ca_key: Path
    pending_csr_dir: Path
    signed_cert_dir: Path
    log_file: Path
    server_name: str
    server_alt_names: tuple[str, ...] = ()
    autosign: bool = False
    bind_host: str = "0.0.0.0"
    bind_port: int = 8443


def load_settings() -> Settings:
    env_file = Path(os.environ.get("GEPPETTO_SERVER_ENV", "/etc/geppetto_server/geppetto-server.env"))
    file_values = _load_env_file(env_file)
    base_dir = Path(_setting("GEPPETTO_SERVER_BASE", "/etc/geppetto_server", file_values))
    config_root = Path(_setting("GEPPETTO_CONFIG_ROOT", str(base_dir / "config"), file_values))
    server_cert = Path(_setting("GEPPETTO_SERVER_CERT", str(base_dir / "pki/server.crt"), file_values))
    server_key = Path(_setting("GEPPETTO_SERVER_KEY", str(base_dir / "pki/server.key"), file_values))
    ca_cert = Path(_setting("GEPPETTO_CA_CERT", str(base_dir / "pki/ca.crt"), file_values))
    ca_key = Path(_setting("GEPPETTO_CA_KEY", str(base_dir / "pki/ca.key"), file_values))
    pending_csr_dir = Path(_setting("GEPPETTO_PENDING_CSR_DIR", str(base_dir / "csr_pending"), file_values))
    signed_cert_dir = Path(_setting("GEPPETTO_SIGNED_CERT_DIR", str(base_dir / "certs"), file_values))
    log_file = Path(_setting("GEPPETTO_SERVER_LOG_FILE", "/var/log/geppetto/geppetto-server.log", file_values))
    server_name = _setting("GEPPETTO_SERVER_NAME", "", file_values)
    server_alt_names = tuple(
        name.strip()
        for name in _setting("GEPPETTO_SERVER_ALT_NAMES", "", file_values).split(",")
        if name.strip()
    )
    autosign = _setting("GEPPETTO_AUTOSIGN", "", file_values).lower() in {"1", "true", "yes"}
    bind_host = _setting("GEPPETTO_SERVER_HOST", "0.0.0.0", file_values)
    bind_port = int(_setting("GEPPETTO_SERVER_PORT", "8443", file_values))
    return Settings(
        config_root=config_root,
        server_cert=server_cert,
        server_key=server_key,
        ca_cert=ca_cert,
        ca_key=ca_key,
        pending_csr_dir=pending_csr_dir,
        signed_cert_dir=signed_cert_dir,
        log_file=log_file,
        server_name=server_name,
        server_alt_names=server_alt_names,
        autosign=autosign,
        bind_host=bind_host,
        bind_port=bind_port,
    )


def _setting(name: str, default: str, file_values: dict[str, str]) -> str:
    return os.environ.get(name, file_values.get(name, default))


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return values
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values
