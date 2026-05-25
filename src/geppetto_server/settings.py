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
    bind_host: str = "0.0.0.0"
    bind_port: int = 8443


def load_settings() -> Settings:
    config_root = Path(os.environ.get("GEPPETTO_CONFIG_ROOT", "/etc/geppetto/config"))
    server_cert = Path(os.environ.get("GEPPETTO_SERVER_CERT", "/etc/geppetto/pki/server.crt"))
    server_key = Path(os.environ.get("GEPPETTO_SERVER_KEY", "/etc/geppetto/pki/server.key"))
    ca_cert = Path(os.environ.get("GEPPETTO_CA_CERT", "/etc/geppetto/pki/ca.crt"))
    bind_host = os.environ.get("GEPPETTO_SERVER_HOST", "0.0.0.0")
    bind_port = int(os.environ.get("GEPPETTO_SERVER_PORT", "8443"))
    return Settings(
        config_root=config_root,
        server_cert=server_cert,
        server_key=server_key,
        ca_cert=ca_cert,
        bind_host=bind_host,
        bind_port=bind_port,
    )
