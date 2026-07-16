# Milestone 44 - China Formal Report Center Visibility

## Purpose

This milestone improves the China compliance package's formal report experience. The formal report model already freezes assessment evidence, supports independent approval, detects source changes, and protects issued PDF integrity. The missing piece was a report-center style entry point that lets a reviewer understand the report status without opening each form.

## Delivered

- Adds report-center display fields on `sudo.cn.compliance.report`:
  - `cn_report_center_stage`
  - `cn_report_center_integrity_state`
  - `cn_report_center_next_action`
  - `cn_report_center_period_label`
- Adds direct navigation from a formal report to:
  - report-related findings
  - report-related remediation tasks
  - source assessment
- Adds a kanban-first formal report center with:
  - report stage
  - integrity status
  - conclusion badge
  - next action
  - risk, remediation, and evidence counters
- Keeps the existing list and form views for detailed review, approval, issuing, withdrawal, and audit fingerprint checks.
- Advertises the capability as `china_report_center_visibility`.

## User Experience Boundary

The report center does not change report governance. It does not bypass draft submission, independent approval, PDF sealing, source-change checks, or tamper detection. It only makes those states visible and actionable from the report entry point.

## Validation

- XML parse check for `views/compliance_report_views.xml`.
- Python compile check for the China addon and validator.
- `tools/validate_addon.py` verifies:
  - package version metadata
  - capability flag
  - report center fields and actions
  - kanban-first action view mode
  - runtime test coverage names

## Acceptance Criteria

- Opening the formal report menu shows a report-center kanban first.
- Each report card shows whether it is draft, pending approval, issued, source-changed, integrity-blocked, or historical.
- Each report card explains the next action.
- Users can jump directly to report findings and remediation tasks from the card.
- Issued report download and formal approval remain controlled by the existing form workflow.
