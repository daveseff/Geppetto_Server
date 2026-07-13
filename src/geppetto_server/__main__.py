from __future__ import annotations

import argparse
import sys

from .pki import clean_agent_cert, ensure_server_pki, list_certs, reset_server_pki, sign_agent_cert
from .server import configure_logging, serve
from .settings import load_settings


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    help_path = _normalize_help_path(argv)
    if help_path is not None:
        return _handle_help_command(help_path)
    args = _parse_args(argv)
    settings = load_settings()
    configure_logging(settings)
    try:
        if args.command in {None, "serve"}:
            serve(settings)
            return 0
        if args.command == "init":
            if args.force:
                reset_server_pki(settings)
            else:
                ensure_server_pki(settings)
            print(f"initialized CA/server certificates under {settings.ca_cert.parent}")
            return 0
        if args.command == "cert":
            return _handle_cert_command(args, settings)
    except Exception as exc:  # noqa: BLE001
        print(f"geppetto-config-server: {exc}", file=sys.stderr)
        return 1
    return 1


def _normalize_help_path(argv: list[str]) -> list[str] | None:
    if not argv:
        return None
    if argv[0] == "help":
        return argv[1:]
    if len(argv) >= 2 and argv[0] == "cert" and argv[1] == "help":
        return ["cert", *argv[2:]]
    if argv[-1] == "help":
        return argv[:-1]
    return None


def _handle_help_command(argv: list[str]) -> int:
    try:
        if not argv:
            _parse_args(["--help"])
        else:
            _parse_args([*argv, "--help"])
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="geppetto-config-server", description="Geppetto config server")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Run the HTTPS config server", description="Run the HTTPS config server")
    init = subparsers.add_parser("init", help="Initialize CA and server certificates", description="Initialize CA and server certificates")
    init.add_argument("--force", action="store_true", help="Replace existing CA and server certificates")

    cert = subparsers.add_parser("cert", help="Manage agent certificates", description="Manage agent certificates")
    cert_subparsers = cert.add_subparsers(dest="cert_command", required=True)
    cert_subparsers.add_parser("list", help="List pending CSRs and signed certificates", description="List pending CSRs and signed certificates")
    sign = cert_subparsers.add_parser("sign", help="Sign a pending agent CSR", description="Sign a pending agent CSR")
    sign.add_argument("host", help="Agent hostname whose pending CSR should be signed")
    clean = cert_subparsers.add_parser("clean", help="Remove a pending CSR and signed cert", description="Remove a pending CSR and signed cert")
    clean.add_argument("host", help="Agent hostname to remove from certificate state")
    status = cert_subparsers.add_parser("status", help="Show certificate state for one host", description="Show certificate state for one host")
    status.add_argument("host", help="Agent hostname to inspect")
    return parser.parse_args(argv)


def _handle_cert_command(args: argparse.Namespace, settings) -> int:
    inventory = list_certs(settings)
    if args.cert_command == "list":
        _print_inventory(inventory)
        return 0
    if args.cert_command == "status":
        states: list[str] = []
        if args.host in inventory.pending:
            states.append("pending")
        if args.host in inventory.signed:
            states.append("signed")
        print(f"{args.host}: {', '.join(states) if states else 'unknown'}")
        return 0
    if args.cert_command == "sign":
        cert_path = sign_agent_cert(settings, args.host)
        print(f"signed {args.host}: {cert_path}")
        return 0
    if args.cert_command == "clean":
        removed = clean_agent_cert(settings, args.host)
        if removed:
            for path in removed:
                print(f"removed {path}")
        else:
            print(f"{args.host}: no pending CSR or signed certificate")
        return 0
    return 1


def _print_inventory(inventory) -> None:
    print("Pending CSRs:")
    for host in inventory.pending:
        print(f"  {host}")
    if not inventory.pending:
        print("  none")
    print("Signed certificates:")
    for host in inventory.signed:
        print(f"  {host}")
    if not inventory.signed:
        print("  none")


if __name__ == "__main__":
    raise SystemExit(main())
