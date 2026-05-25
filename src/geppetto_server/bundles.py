from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path


INCLUDE_RE = re.compile(r"^include\s+['\"]([^'\"]+)['\"]\s*$")


class HostConfigNotFoundError(FileNotFoundError):
    pass


class ConfigBundleBuilder:
    def __init__(self, config_root: Path):
        self.config_root = Path(config_root).resolve()

    def build_host_bundle(self, host_name: str) -> bytes:
        host_plan = self.config_root / "hosts" / host_name / "plan.fops"
        if not host_plan.exists():
            raise HostConfigNotFoundError(f"host plan not found for {host_name}")

        files = self._collect_plan_closure(host_plan)
        templates_dir = self.config_root / "templates"
        if templates_dir.exists():
            files.extend(path for path in sorted(templates_dir.rglob("*")) if path.is_file())

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(set(files)):
                archive.write(path, arcname=str(path.relative_to(self.config_root.parent)))
        return payload.getvalue()

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
