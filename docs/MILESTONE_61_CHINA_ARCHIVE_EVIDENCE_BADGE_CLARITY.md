# M61 - China Archive and Evidence Badge Clarity

## Purpose

M61 improves the final audit-evidence part of the China compliance loop. Users need to see whether evidence, filing archives, payment archives and integrity checks are reliable without opening every record.

## Delivered Scope

- Added capability flag `china_archive_evidence_badge_clarity`.
- Added native Odoo badge decorations to the evidence center kanban state badge.
- Added native Odoo badge decorations to filing center list and kanban badges:
  - filing state;
  - payment state;
  - submission integrity state;
  - payment integrity state;
  - formal evidence state.
- Preserved the existing Odoo-native menu, action and model structure.
- Added upgrade migration `19.0.1.58.0` to refresh country-pack metadata.
- Updated validator checks so future edits cannot silently remove archive/evidence badge semantics.

## Acceptance Checks

- `tools/validate_addon.py` validates version `19.0.1.58.0`.
- Evidence center XML contains native `decoration-*` expressions for evidence state.
- Filing center XML contains native `decoration-*` expressions for filing, payment, integrity and evidence states.
- Filing center runtime tests assert the capability flag is published.

## Package

- Package: `dist/codex-cn-m61-country-v1.tgz`
- SHA256: `0710DE677EA9E94A9A09235701627FEA62E6F57F11FAAA84EA2EBE35ABFD39D1`
