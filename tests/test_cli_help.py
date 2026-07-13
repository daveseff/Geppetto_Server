from __future__ import annotations

import pytest

from geppetto_server.__main__ import _parse_args, main


def test_top_level_help_lists_certificate_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--help"])

    output = capsys.readouterr().out
    assert "serve" in output
    assert "init" in output
    assert "cert" in output


def test_cert_sign_help_describes_host_argument(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        _parse_args(["cert", "sign", "--help"])

    output = capsys.readouterr().out
    assert "usage: geppetto-config-server cert sign" in output
    assert "Agent hostname whose pending CSR should be signed" in output


def test_help_command_prints_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["help"]) == 0

    output = capsys.readouterr().out
    assert "Geppetto config server" in output
    assert "serve" in output
    assert "cert" in output


def test_help_command_prints_nested_cert_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["help", "cert", "sign"]) == 0

    output = capsys.readouterr().out
    assert "usage: geppetto-config-server cert sign" in output
    assert "Agent hostname whose pending CSR should be signed" in output


def test_cert_help_command_prints_cert_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cert", "help"]) == 0

    output = capsys.readouterr().out
    assert "usage: geppetto-config-server cert" in output
    assert "sign" in output


def test_cert_help_command_prints_nested_cert_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cert", "help", "sign"]) == 0

    output = capsys.readouterr().out
    assert "usage: geppetto-config-server cert sign" in output
    assert "Agent hostname whose pending CSR should be signed" in output


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["serve", "help"], "usage: geppetto-config-server serve"),
        (["init", "help"], "usage: geppetto-config-server init"),
        (["cert", "list", "help"], "usage: geppetto-config-server cert list"),
        (["cert", "sign", "help"], "usage: geppetto-config-server cert sign"),
        (["cert", "clean", "help"], "usage: geppetto-config-server cert clean"),
        (["cert", "status", "help"], "usage: geppetto-config-server cert status"),
        (["help", "serve"], "usage: geppetto-config-server serve"),
        (["help", "init"], "usage: geppetto-config-server init"),
        (["help", "cert", "list"], "usage: geppetto-config-server cert list"),
        (["help", "cert", "sign"], "usage: geppetto-config-server cert sign"),
        (["help", "cert", "clean"], "usage: geppetto-config-server cert clean"),
        (["help", "cert", "status"], "usage: geppetto-config-server cert status"),
    ],
)
def test_all_server_commands_support_help_forms(
    argv: list[str],
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(argv) == 0

    output = capsys.readouterr().out
    assert expected in output
