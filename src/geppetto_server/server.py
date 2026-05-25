from __future__ import annotations

import json
import re
import ssl
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .bundles import ConfigBundleBuilder, HostConfigNotFoundError
from .settings import Settings


BUNDLE_RE = re.compile(r"^/v1/configs/([^/]+)/bundle$")


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
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return

        match = BUNDLE_RE.match(self.path)
        if not match:
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return

        host_name = match.group(1)
        cert_name = extract_common_name(self.connection.getpeercert())
        if not cert_name:
            self._write_json(HTTPStatus.UNAUTHORIZED, {"detail": "client certificate required"})
            return
        if cert_name != host_name:
            self._write_json(HTTPStatus.FORBIDDEN, {"detail": f"certificate CN {cert_name} cannot access {host_name}"})
            return

        try:
            payload = self.server.bundle_builder.build_host_bundle(host_name)  # type: ignore[attr-defined]
        except HostConfigNotFoundError as exc:
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

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_json(self, status_code: HTTPStatus, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GeppettoHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, *, bundle_builder: ConfigBundleBuilder):
        super().__init__(server_address, handler_class)
        self.bundle_builder = bundle_builder


def build_ssl_context(settings: Settings) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile=str(settings.server_cert), keyfile=str(settings.server_key))
    context.load_verify_locations(cafile=str(settings.ca_cert))
    return context


def serve(settings: Settings) -> None:
    server = GeppettoHTTPServer(
        (settings.bind_host, settings.bind_port),
        GeppettoRequestHandler,
        bundle_builder=ConfigBundleBuilder(settings.config_root),
    )
    server.socket = build_ssl_context(settings).wrap_socket(server.socket, server_side=True)
    server.serve_forever()
