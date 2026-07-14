from __future__ import annotations

import json
import logging
import re
import ssl
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .bundles import ConfigBundleBuilder, HostConfigNotFoundError
from .pki import csr_common_name, ensure_server_pki, sign_csr
from .settings import Settings


BUNDLE_RE = re.compile(r"^/v1/configs/([^/]+)/bundle$")
CSR_RE = re.compile(r"^/v1/csr/([^/]+)$")
LOGGER = logging.getLogger(__name__)


def configure_logging(settings: Settings) -> None:
    handlers: list[logging.Handler]
    try:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.FileHandler(settings.log_file)]
    except OSError:
        handlers = [logging.StreamHandler()]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s", handlers=handlers)


def extract_common_name(peer_cert: dict | None) -> str | None:
    if not peer_cert:
        return None
    for rdn in peer_cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                return str(value)
    return None


class GeppettoRequestHandler(BaseHTTPRequestHandler):
    server_version = "GeppettoConfigServer/0.1"

    def do_GET(self) -> None:  # noqa: N802
        request_paths = routed_paths(self.path, self.server.settings.path_prefix)  # type: ignore[attr-defined]
        if "/health" in request_paths:
            LOGGER.info("health-check client=%s", self.client_address[0])
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if "/v1/ca" in request_paths:
            LOGGER.info("ca-download client=%s", self.client_address[0])
            self._write_file(self.server.settings.ca_cert, "application/x-pem-file")  # type: ignore[attr-defined]
            return

        match = match_request_path(request_paths, BUNDLE_RE)
        if not match:
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return

        host_name = match.group(1)
        cert_name = extract_common_name(self.connection.getpeercert())
        if not cert_name:
            LOGGER.warning("bundle-denied host=%s client=%s reason=no-client-cert", host_name, self.client_address[0])
            self._write_json(HTTPStatus.UNAUTHORIZED, {"detail": "client certificate required"})
            return
        if cert_name != host_name:
            LOGGER.warning(
                "bundle-denied host=%s cert-cn=%s client=%s reason=cn-mismatch",
                host_name,
                cert_name,
                self.client_address[0],
            )
            self._write_json(HTTPStatus.FORBIDDEN, {"detail": f"certificate CN {cert_name} cannot access {host_name}"})
            return

        try:
            payload = self.server.bundle_builder.build_host_bundle(host_name)  # type: ignore[attr-defined]
        except HostConfigNotFoundError as exc:
            LOGGER.warning("bundle-not-found host=%s client=%s", host_name, self.client_address[0])
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": str(exc)})
            return
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
            return
        except FileNotFoundError as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": str(exc)})
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{host_name}.zip"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        LOGGER.info("bundle-served host=%s bytes=%s client=%s", host_name, len(payload), self.client_address[0])

    def do_POST(self) -> None:  # noqa: N802
        request_paths = routed_paths(self.path, self.server.settings.path_prefix)  # type: ignore[attr-defined]
        match = match_request_path(request_paths, CSR_RE)
        if not match:
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return
        host_name = match.group(1)
        length = int(self.headers.get("Content-Length", "0"))
        csr = self.rfile.read(length)
        try:
            cert = self.server.enrollment.handle_csr(host_name, csr)  # type: ignore[attr-defined]
        except ValueError as exc:
            LOGGER.warning("csr-rejected host=%s client=%s detail=%s", host_name, self.client_address[0], exc)
            self._write_json(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
            return
        if cert:
            self._write_bytes(HTTPStatus.OK, cert, "application/x-pem-file")
            LOGGER.info("csr-signed host=%s client=%s", host_name, self.client_address[0])
            return
        self._write_json(HTTPStatus.ACCEPTED, {"detail": f"CSR for {host_name} is pending approval"})
        LOGGER.info("csr-pending host=%s client=%s", host_name, self.client_address[0])

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_json(self, status_code: HTTPStatus, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._write_bytes(status_code, body, "application/json")

    def _write_file(self, path: Path, content_type: str) -> None:
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": f"file not found: {path}"})
            return
        self._write_bytes(HTTPStatus.OK, payload, content_type)

    def _write_bytes(self, status_code: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GeppettoHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, *, bundle_builder: ConfigBundleBuilder, settings: Settings):
        super().__init__(server_address, handler_class)
        self.bundle_builder = bundle_builder
        self.settings = settings
        self.enrollment = EnrollmentService(settings)


class EnrollmentService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def handle_csr(self, host_name: str, csr: bytes) -> bytes | None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", host_name):
            raise ValueError("invalid host name")
        csr_name = self._csr_common_name(csr)
        if csr_name != host_name:
            raise ValueError(f"CSR common name {csr_name!r} does not match requested host {host_name!r}")
        signed_cert = self.settings.signed_cert_dir / f"{host_name}.crt"
        if signed_cert.exists():
            return signed_cert.read_bytes()

        self.settings.pending_csr_dir.mkdir(parents=True, exist_ok=True)
        csr_path = self.settings.pending_csr_dir / f"{host_name}.csr"
        csr_path.write_bytes(csr)

        if not self.settings.autosign:
            return None

        self.settings.signed_cert_dir.mkdir(parents=True, exist_ok=True)
        sign_csr(csr_path, signed_cert, self.settings.ca_cert, self.settings.ca_key)
        return signed_cert.read_bytes()

    @staticmethod
    def _csr_common_name(csr: bytes) -> str:
        return csr_common_name(csr)


def build_ssl_context(settings: Settings) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_OPTIONAL
    context.load_cert_chain(certfile=str(settings.server_cert), keyfile=str(settings.server_key))
    context.load_verify_locations(cafile=str(settings.ca_cert))
    return context


def routed_paths(request_target: str, path_prefix: str) -> tuple[str, ...]:
    request_path = urlsplit(request_target).path or "/"
    paths = [request_path]
    if path_prefix:
        if request_path == path_prefix:
            paths.append("/")
        elif request_path.startswith(f"{path_prefix}/"):
            paths.append(request_path[len(path_prefix):])
    return tuple(paths)


def match_request_path(paths: tuple[str, ...], pattern: re.Pattern[str]) -> re.Match[str] | None:
    for path in paths:
        match = pattern.match(path)
        if match:
            return match
    return None


def serve(settings: Settings) -> None:
    ensure_server_pki(settings)
    server = GeppettoHTTPServer(
        (settings.bind_host, settings.bind_port),
        GeppettoRequestHandler,
        bundle_builder=ConfigBundleBuilder(settings.config_root),
        settings=settings,
    )
    server.socket = build_ssl_context(settings).wrap_socket(server.socket, server_side=True)
    LOGGER.info(
        "server-started bind=%s:%s config_root=%s path_prefix=%s log_file=%s",
        settings.bind_host,
        settings.bind_port,
        settings.config_root,
        settings.path_prefix or "/",
        settings.log_file,
    )
    server.serve_forever()
