# Changelog

## 0.3.0

### Added
- One-or-many host groups defined by the `groups` attribute in each host's
  `node` block.
- Generated bundle entrypoints that load defaults, matching groups, and the
  requesting host's plan in that order.

### Changed
- Host bundles always publish `defaults/`, publish only groups assigned to the
  requesting host, and retain shared and host-specific templates.
- Bumped Python, RPM, and Arch package versions to `0.3.0`.
