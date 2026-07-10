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
    autosign: bool = False
    bind_host: str = "0.0.0.0"
    bind_port: int = 8443


def load_settings() -> Settings:
    base_dir = Path(os.environ.get("GEPPETTO_SERVER_BASE", "/etc/geppetto_server"))
    config_root = Path(os.environ.get("GEPPETTO_CONFIG_ROOT", str(base_dir / "config")))
    server_cert = Path(os.environ.get("GEPPETTO_SERVER_CERT", str(base_dir / "pki/server.crt")))
    server_key = Path(os.environ.get("GEPPETTO_SERVER_KEY", str(base_dir / "pki/server.key")))
    ca_cert = Path(os.environ.get("GEPPETTO_CA_CERT", str(base_dir / "pki/ca.crt")))
    ca_key = Path(os.environ.get("GEPPETTO_CA_KEY", str(base_dir / "pki/ca.key")))
    pending_csr_dir = Path(os.environ.get("GEPPETTO_PENDING_CSR_DIR", str(base_dir / "csr_pending")))
    signed_cert_dir = Path(os.environ.get("GEPPETTO_SIGNED_CERT_DIR", str(base_dir / "certs")))
    log_file = Path(os.environ.get("GEPPETTO_SERVER_LOG_FILE", "/var/log/geppetto/geppetto-server.log"))
    server_name = os.environ.get("GEPPETTO_SERVER_NAME", "")
    autosign = os.environ.get("GEPPETTO_AUTOSIGN", "").lower() in {"1", "true", "yes"}
    bind_host = os.environ.get("GEPPETTO_SERVER_HOST", "0.0.0.0")
    bind_port = int(os.environ.get("GEPPETTO_SERVER_PORT", "8443"))
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
        autosign=autosign,
        bind_host=bind_host,
        bind_port=bind_port,
    )
