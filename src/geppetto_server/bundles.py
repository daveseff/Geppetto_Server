from __future__ import annotations

import io
import ast
import re
import zipfile
from pathlib import Path


INCLUDE_RE = re.compile(r"^include\s+['\"]([^'\"]+)['\"]\s*$")
GROUPS_RE = re.compile(r"\bgroups\s*(?:=>|=)\s*(\[[^\]]*\])", re.DOTALL)
GROUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class HostConfigNotFoundError(FileNotFoundError):
    pass


class ConfigBundleBuilder:
    def __init__(self, config_root: Path):
        self.config_root = Path(config_root).resolve()

    def build_host_bundle(self, host_name: str) -> bytes:
        host_dir = self.config_root / "hosts" / host_name
        host_plan = host_dir / "plan.fops"
        if not host_plan.exists():
            raise HostConfigNotFoundError(f"host plan not found for {host_name}")

        defaults_dir = self.config_root / "defaults"
        group_dirs = self._groups_for_host(host_name, host_plan)
        files = self._files_under(defaults_dir)
        for group_dir in group_dirs:
            files.extend(self._files_under(group_dir))
        files.extend(self._files_under(host_dir))
        files.extend(self._files_under(self.config_root / "templates"))

        plan_files = [*self._plan_files(defaults_dir)]
        for group_dir in group_dirs:
            plan_files.extend(self._plan_files(group_dir))
        plan_files.append(host_plan)
        for plan_file in plan_files:
            files.extend(self._collect_plan_closure(plan_file))
        composite_plan = "\n".join(
            f"include '{path.relative_to(self.config_root).as_posix()}'" for path in plan_files
        ) + "\n"

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(set(files)):
                archive.write(path, arcname=str(path.relative_to(self.config_root.parent)))
            archive.writestr("config/plan.fops", composite_plan)
        return payload.getvalue()

    def _groups_for_host(self, host_name: str, host_plan: Path) -> list[Path]:
        group_names = self._host_groups(host_name, host_plan)
        groups_root = self.config_root / "groups"
        group_dirs: list[Path] = []
        for group_name in group_names:
            group_dir = groups_root / group_name
            if not group_dir.is_dir():
                raise FileNotFoundError(f"group config not found for {group_name} (host {host_name})")
            group_dirs.append(group_dir)
        return group_dirs

    @staticmethod
    def _host_groups(host_name: str, host_plan: Path) -> list[str]:
        text = host_plan.read_text()
        node_match = re.search(rf"\bnode\s+(['\"]){re.escape(host_name)}\1\s*\{{", text)
        if node_match is None:
            return []
        body_start = node_match.end()
        depth = 1
        quote: str | None = None
        escaped = False
        body_end = len(text)
        for index in range(body_start, len(text)):
            char = text[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    body_end = index
                    break
        body = text[body_start:body_end]
        match = GROUPS_RE.search(body)
        if match is None:
            if re.search(r"\bgroups\b", body):
                raise ValueError(f"{host_plan}: groups must be a list of strings")
            return []
        try:
            groups = ast.literal_eval(match.group(1))
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"{host_plan}: groups must be a list of strings") from exc
        if not isinstance(groups, list) or not all(isinstance(item, str) and item for item in groups):
            raise ValueError(f"{host_plan}: groups must be a list of strings")
        invalid = [item for item in groups if GROUP_NAME_RE.fullmatch(item) is None]
        if invalid:
            raise ValueError(f"{host_plan}: invalid group name: {invalid[0]}")
        if len(groups) != len(set(groups)):
            raise ValueError(f"{host_plan}: groups must not contain duplicates")
        return groups

    @staticmethod
    def _files_under(directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return [path for path in sorted(directory.rglob("*")) if path.is_file()]

    @staticmethod
    def _plan_files(directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return [path for path in sorted(directory.rglob("*.fops")) if path.is_file()]

    def _collect_plan_closure(self, start: Path) -> list[Path]:
        pending = [start.resolve()]
        seen: set[Path] = set()
        collected: list[Path] = []
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            self._require_under_root(current)
            if not current.exists():
                raise FileNotFoundError(f"included plan not found: {current}")
            collected.append(current)
            for line in current.read_text().splitlines():
                match = INCLUDE_RE.match(line.strip())
                if not match:
                    continue
                pending.append((current.parent / match.group(1)).resolve())
        return collected

    def _require_under_root(self, path: Path) -> None:
        try:
            path.relative_to(self.config_root)
        except ValueError as exc:
            raise ValueError(f"path escapes config root: {path}") from exc
