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
                "node 'host1' { groups = ['staging'] }",
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
        "config/plan.fops",
        "config/templates/motd.tmpl",
    ]

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        plan = archive.read("config/plan.fops").decode()
    assert "include 'defaults/base.fops'" in plan
    assert "include 'groups/staging/apps.fops'" in plan
    assert "include 'hosts/host1/plan.fops'" in plan


def test_bundle_only_contains_groups_assigned_in_host_node(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "hosts/host1").mkdir(parents=True)
    (root / "groups/staging").mkdir(parents=True)
    (root / "groups/production").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text("node 'host1' { groups => ['staging'] }")
    (root / "groups/staging/packages.fops").write_text("task 'staging' on ['host1'] {}")
    (root / "groups/production/packages.fops").write_text("task 'production' on ['host3'] {}")

    names = _zip_names(ConfigBundleBuilder(root).build_host_bundle("host1"))

    assert "config/groups/staging/packages.fops" in names
    assert "config/groups/production/packages.fops" not in names


@pytest.mark.parametrize(
    "node",
    ["node 'host1' {}", "node 'host1' { groups = [] }"],
)
def test_omitted_or_empty_groups_means_no_membership(tmp_path: Path, node: str) -> None:
    root = tmp_path / "config"
    (root / "hosts/host1").mkdir(parents=True)
    (root / "groups/staging").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text(node)
    (root / "groups/staging/packages.fops").write_text("task 'staging' on ['host1'] {}")

    names = _zip_names(ConfigBundleBuilder(root).build_host_bundle("host1"))

    assert not any(name.startswith("config/groups/") for name in names)


def test_host_can_belong_to_multiple_groups(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "hosts/host1").mkdir(parents=True)
    (root / "groups/staging").mkdir(parents=True)
    (root / "groups/database").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text(
        "node 'host1' { groups = ['staging', 'database'] }"
    )
    (root / "groups/staging/base.fops").write_text("task 'staging' on ['host1'] {}")
    (root / "groups/database/base.fops").write_text("task 'database' on ['host1'] {}")

    payload = ConfigBundleBuilder(root).build_host_bundle("host1")

    names = _zip_names(payload)
    assert "config/groups/staging/base.fops" in names
    assert "config/groups/database/base.fops" in names
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        plan = archive.read("config/plan.fops").decode()
    assert plan.index("groups/staging/base.fops") < plan.index("groups/database/base.fops")


def test_invalid_node_groups_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "hosts/host1").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text("node 'host1' { groups = 'staging' }")

    with pytest.raises(ValueError, match="groups must be a list of strings"):
        ConfigBundleBuilder(root).build_host_bundle("host1")


def test_missing_group_directory_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "hosts/host1").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text("node 'host1' { groups = ['missing'] }")

    with pytest.raises(FileNotFoundError, match="group config not found for missing"):
        ConfigBundleBuilder(root).build_host_bundle("host1")


def test_group_name_cannot_escape_groups_directory(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "hosts/host1").mkdir(parents=True)
    (root / "hosts/host1/plan.fops").write_text("node 'host1' { groups = ['../hosts'] }")

    with pytest.raises(ValueError, match="invalid group name"):
        ConfigBundleBuilder(root).build_host_bundle("host1")


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
