# M38 China Risk Action Guidance

## Summary

M38 improves the China risk center and remediation tracker so users can read the next operating step directly from each card or list row.

The goal is to make risk review less like browsing raw records and more like following a controlled compliance workflow.

## Delivered

- Added risk-center display fields on `sudo.compliance.finding`:
  - applicable period,
  - next action,
  - evidence state,
  - evidence count,
  - verified evidence count.
- Added remediation display fields on `sudo.compliance.task`:
  - applicable period,
  - next action,
  - evidence state,
  - evidence count,
  - verified evidence count.
- Updated China risk center list and kanban views to show period, next action, and evidence readiness.
- Updated China remediation tracker list and kanban views to show period, next action, and evidence readiness.
- Added country pack capability flag `china_risk_action_guidance`.
- Bumped `sudo_country_pack_cn` to `19.0.1.35.0`.

## Design Boundary

This is a viewing and guidance layer. It does not create a new workflow engine and does not change rule results, review states, task state transitions, evidence verification, or report approval controls.

The computed next action is intentionally conservative. It points the user to review, remediate, quantify tax impact, verify evidence, or wait for validation rescans, but it does not claim a legal conclusion.

## Validation

Local validation should include:

- XML parse check for `views/risk_center_views.xml`.
- Python compile check.
- `python tools\validate_addon.py`.
- `git diff --check`.

Server runtime validation remains blocked until PostgreSQL on `43.165.173.80` is restored or an alternate Odoo database is provided.
