from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from geppetto_server.bundles import ConfigBundleBuilder, HostConfigNotFoundError


def _zip_names(payload: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return sorted(archive.namelist())


def test_build_host_bundle_collects_includes_and_templates(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "defaults").mkdir(parents=True)
    (root / "groups/staging").mkdir(parents=True)
    (root / "hosts/host1").mkdir(parents=True)
    (root / "hosts/host1/templates").mkdir(parents=True)
    (root / "templates").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text(
        "\n".join(
            [
                "include '../../defaults/base.fops'",
                "include '../../groups/staging/apps.fops'",
                "include 'keys.fops'",
            ]
        )
    )
    (root / "hosts/host1/keys.fops").write_text("task 'keys' on ['host1'] {}")
    (root / "defaults/base.fops").write_text("task 'base' on ['host1'] {}")
    (root / "groups/staging/apps.fops").write_text("task 'apps' on ['host1'] {}")
    (root / "hosts/host1/templates/sssd.conf.tmpl").write_text("services = nss, pam")
    (root / "templates/motd.tmpl").write_text("hello")

    payload = ConfigBundleBuilder(root).build_host_bundle("host1")

    assert _zip_names(payload) == [
        "config/defaults/base.fops",
        "config/groups/staging/apps.fops",
        "config/hosts/host1/keys.fops",
        "config/hosts/host1/plan.fops",
        "config/hosts/host1/templates/sssd.conf.tmpl",
        "config/templates/motd.tmpl",
    ]


def test_missing_host_plan_raises(tmp_path: Path) -> None:
    root = tmp_path / "config"
    root.mkdir()
    with pytest.raises(HostConfigNotFoundError):
        ConfigBundleBuilder(root).build_host_bundle("missing")


def test_include_cannot_escape_config_root(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "hosts/host1").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text("include '../../../../etc/passwd'")

    with pytest.raises(ValueError, match="escapes config root"):
        ConfigBundleBuilder(root).build_host_bundle("host1")
