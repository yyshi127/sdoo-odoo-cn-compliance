# M34 China Report Readiness

## Summary

M34 adds a China report-readiness layer between rule assessment and formal compliance reporting. It helps users understand whether an assessment is ready for formal report preparation, and if not, why it is blocked or limited.

## Delivered

- Added report-readiness fields on `sudo.compliance.assessment`:
  - readiness state,
  - next action,
  - issue count,
  - open remediation count,
  - limitation count,
  - pending tax-impact count,
  - latest formal report,
  - report preparation eligibility.
- Added `中国报告准备度` menu and action.
- Added kanban/list/search views for report preparation review.
- Added a report-readiness section to the assessment form.
- Added a report-readiness drill-down button on the China workbench.
- Added country pack capability flag `china_report_readiness`.
- Bumped `sudo_country_pack_cn` to `19.0.1.31.0`.

## Design Boundary

The readiness layer does not replace `sudo.cn.compliance.report`. It summarizes whether the source `sudo.compliance.assessment` is suitable for report preparation using existing controlled artifacts:

- assessment state,
- data sufficiency,
- unknown/error findings,
- source/professional review warnings,
- pending human review,
- open remediation tasks,
- pending or unquantifiable tax-impact cases,
- jurisdiction scope limitations,
- existing draft/submitted/issued formal reports.

This keeps the formal report as the governed, auditable artifact while giving users a clearer pre-report checklist.

## Validation

Local validation should include:

- XML parse check for `views/report_readiness_views.xml`.
- Python compile check.
- `python tools\validate_addon.py`.
- `git diff --check`.

Server runtime validation remains blocked until PostgreSQL on `43.165.173.80` is restored.

## Follow-Up

After database recovery, upgrade an isolated test database to `19.0.1.31.0` and verify:

- `中国报告准备度` appears in the Compliance app.
- Workbench drill-down opens report readiness scoped to the selected profile.
- Ready/limited/remediation/review states display clearly.
- `编制正式报告` opens the existing governed formal report flow.
- Existing report submission and approval controls remain unchanged.
