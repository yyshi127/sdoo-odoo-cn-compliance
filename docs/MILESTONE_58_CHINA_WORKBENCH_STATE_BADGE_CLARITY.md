# M58 - China Workbench State Badge Clarity

## Purpose

M58 improves the China compliance workbench reading experience by making state badges visually distinct. Compliance users should be able to tell at a glance whether a domain or workflow step is ready, needs attention, is blocked, or has not started.

This responds to the UX requirement that compliance pages should be clear, review-oriented and immediately understandable, not just native Odoo record lists.

## Delivered Scope

- Added capability flag `china_workbench_state_badge_clarity`.
- Added native Odoo badge decorations to China workbench state fields:
  - `ready` -> success.
  - `attention` -> warning.
  - `blocked` -> danger.
  - `not_started` -> muted.
- Covered key workbench areas:
  - overall profile status on the form;
  - tax obligation readiness;
  - VAT, CIT and IIT domain cards;
  - cross-border/withholding card;
  - end-to-end flow steps;
  - filing/payment archive summary.
- Added upgrade migration `19.0.1.55.0` to refresh country-pack metadata.
- Updated validator checks so future edits cannot silently remove the badge-state contract.

## Acceptance Checks

- `tools/validate_addon.py` validates version `19.0.1.55.0`.
- Workbench XML contains native Odoo `decoration-*` expressions for critical state badges.
- Workbench runtime tests assert the capability flag is published.

## Package

- Package: `dist/codex-cn-m58-country-v1.tgz`
- SHA256: `1B28D2938D3BDA0C9EE2F3AA1293324704FE353359F1E4F75F3D3AD00FD94B37`
