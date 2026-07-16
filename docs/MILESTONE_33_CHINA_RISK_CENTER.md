# M33 China Risk Center and Remediation Tracker

## Summary

M33 adds a China-specific risk center and remediation tracker on top of the governed rule assessment results already produced by the compliance engine. This milestone improves the review experience without changing the rule engine, source governance, or audit trail semantics.

## Delivered

- Added `中国风险中心` for China compliance findings.
- Added `中国整改跟踪` for remediation tasks generated from China compliance findings.
- Added kanban/list/search views optimized for review work:
  - risk level,
  - result,
  - human review state,
  - remediation assignee,
  - due date,
  - remediation state,
  - verification/rescan state,
  - linked tax impact case count.
- Bound the new views explicitly to their actions so Odoo opens the China-specific experience instead of the generic global finance views.
- Updated the China workbench buttons so risk and remediation drill-down open the new China-specific actions.
- Added country pack capability flags:
  - `china_risk_center`
  - `china_remediation_tracker`
- Bumped `sudo_country_pack_cn` to `19.0.1.30.0`.

## Design Boundary

The risk center does not create a separate risk model. It remains grounded in:

- `sudo.compliance.finding`
- `sudo.compliance.task`

This keeps the audit trail anchored to the original assessment, rule version, fact snapshot, evidence requirements, review state, and remediation lifecycle.

## Validation

Local static validation should include:

- Python compile check.
- XML parse check for `views/risk_center_views.xml`.
- `python tools\validate_addon.py`.
- `git diff --check`.

Server runtime validation is still blocked until PostgreSQL on `43.165.173.80` is restored. The observed blocker remains the failed PostgreSQL 16 cluster and missing `/var/lib/postgresql/16/main` data directory.

## Next Step

After database recovery, upgrade an isolated test database to `19.0.1.30.0` and visually verify:

- `中国合规工作台` opens normally.
- Risk cards drill into `中国风险中心`.
- Remediation cards drill into `中国整改跟踪`.
- Grouping by risk level, review state, assignee, task state, and due month works.
- Form drill-down still uses the governed base finding/task forms.
