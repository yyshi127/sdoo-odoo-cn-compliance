# M62 - China Formal Report Badge Clarity

## Purpose

M62 improves the final formal compliance report center. A reviewer should be able to see report lifecycle, conclusion, traceability and artifact integrity status directly from the report list, kanban card and form.

## Delivered Scope

- Added capability flag `china_formal_report_badge_clarity`.
- Added native Odoo badge decorations to formal report kanban cards:
  - report center stage;
  - report conclusion;
  - report integrity state;
  - traceability state.
- Added native Odoo badge decorations to formal report list rows:
  - report center stage;
  - report integrity state.
- Added native Odoo badge decorations to formal report form:
  - conclusion state;
  - traceability state;
  - snapshot integrity state;
  - approval integrity state;
  - PDF integrity state.
- Fixed formal report runtime coverage by moving report-specific assertions out of the country-pack capability test and into the report workflow test that actually creates and submits a report.
- Added upgrade migration `19.0.1.59.0` to refresh country-pack metadata.

## Acceptance Checks

- `tools/validate_addon.py` validates version `19.0.1.59.0`.
- Formal report XML contains native `decoration-*` expressions for lifecycle, conclusion, traceability and integrity states.
- Formal report runtime tests assert the capability flag is published.

## Package

- Package: `dist/codex-cn-m62-country-v1.tgz`
- SHA256: `1B555BDF0777FB9A2835B6F7FCAA9A0D3ACC5C3B26AD8A0402EE9CE6671A1B31`
