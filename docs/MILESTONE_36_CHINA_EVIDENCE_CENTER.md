# M36 China Evidence Center

## Summary

M36 adds a China-specific evidence center that centralizes formal evidence records across assessments, findings, remediation tasks, and filing/payment archives. It reuses the existing governed `sudo.compliance.evidence` model rather than creating a parallel evidence table.

## Delivered

- Added `中国证据中心` menu and action.
- Added China-specific evidence search/list/kanban views.
- Added workbench drill-down to the evidence center.
- Added an informational notice on evidence forms explaining checksum immutability.
- Added country pack capability flag `china_evidence_center`.
- Bumped `sudo_country_pack_cn` to `19.0.1.33.0`.

## Design Boundary

The evidence center is a viewing and navigation layer. The underlying evidence lifecycle remains controlled by global finance:

- draft,
- submitted,
- verified,
- rejected,
- SHA-256 fingerprinting,
- attachment mutation protection,
- audit event logging.

This keeps the China pack aligned with the existing audit chain while making evidence readiness easier to inspect.

## Validation

Local validation should include:

- XML parse check for `views/evidence_center_views.xml`.
- Python compile check.
- `python tools\validate_addon.py`.
- `git diff --check`.

Server runtime validation remains blocked until PostgreSQL on `43.165.173.80` is restored.
