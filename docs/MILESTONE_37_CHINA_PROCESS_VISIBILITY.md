# M37 China Process Visibility

## Summary

M37 makes the China compliance workbench easier to read by adding an end-to-end process strip for the core operating flow:

`rule scan -> risk review -> remediation -> report readiness -> evidence chain`

The change is intentionally a visibility layer. It does not relax rule governance, evidence verification, remediation closure, or report approval controls.

## Delivered

- Added five computed process states on `sudo.compliance.profile`:
  - scan,
  - risk,
  - remediation,
  - report,
  - evidence.
- Added evidence and verified-evidence counts to the workbench summary.
- Added clickable process tiles to the China compliance workbench kanban view.
- Added a process overview group to the workbench form view.
- Added country pack capability flag `china_process_visibility`.
- Bumped `sudo_country_pack_cn` to `19.0.1.34.0`.

## Design Boundary

The process strip is a status guide, not a separate workflow engine. Each tile routes to the governed source records:

- assessments for rule scans,
- findings for risks,
- tasks for remediation,
- assessments/reports for report readiness,
- governed evidence records for the evidence chain.

## Validation

Local validation should include:

- XML parse check for `views/workbench_views.xml`.
- Python compile check.
- `python tools\validate_addon.py`.
- `git diff --check`.

Server runtime validation remains blocked until PostgreSQL on `43.165.173.80` is restored or an alternate Odoo database is provided.
