# M60 - China Report Readiness Badge Clarity

## Purpose

M60 improves the report-preparation entry point for the China compliance package. The report readiness page is where users decide whether scan results can become a formal compliance report, so the key states must be immediately visible.

## Delivered Scope

- Added capability flag `china_report_readiness_badge_clarity`.
- Added native Odoo badge decorations to report readiness kanban and inherited assessment form:
  - report readiness state;
  - controlled data-basis state;
  - obligation-basis state.
- Preserved the existing Odoo-native menu, action and model structure.
- Added upgrade migration `19.0.1.57.0` to refresh country-pack metadata.
- Updated validator checks so future edits cannot silently remove report-readiness badge semantics.

## Acceptance Checks

- `tools/validate_addon.py` validates version `19.0.1.57.0`.
- Report readiness XML contains native `decoration-*` expressions for report, data and obligation status badges.
- Report readiness runtime tests assert the capability flag is published.

## Package

- Package: `dist/codex-cn-m60-country-v1.tgz`
- SHA256: `3D94BB2230795E096268729F79D66DC59DD2FCEE766E463F27CC81BCD0E6143B`
