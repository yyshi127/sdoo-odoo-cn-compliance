# M32 China Compliance Workbench

## Summary

M32 adds the first China-specific review-oriented UX layer for the China fiscal compliance pack. The goal is to stop presenting compliance work only as scattered Odoo configuration and list screens. The new workbench gives compliance users a single entry point to see the current profile status, high-risk findings, remediation tasks, tax impact review, reconciliation issues, and formal reports.

## Scope

- Adds `sudo.compliance.profile` workbench fields for China profiles.
- Adds a native Odoo kanban/list/form action named `中国合规工作台`.
- Adds direct navigation from the workbench to:
  - rule assessments,
  - findings,
  - remediation tasks,
  - China tax impact cases,
  - formal China compliance reports,
  - VAT/CIT/IIT reconciliation issues.
- Adds `china_compliance_workbench` to the country pack capability metadata.
- Bumps `sudo_country_pack_cn` to `19.0.1.29.0`.

## Design Notes

The workbench is deliberately an aggregation layer. It does not invent new risk results and does not replace the rule engine. It summarizes existing controlled records:

- `sudo.compliance.assessment`
- `sudo.compliance.finding`
- `sudo.compliance.task`
- `sudo.cn.tax.impact.case`
- `sudo.cn.compliance.report`
- VAT/CIT/IIT period reconciliation issue models

Computed fields are non-stored so the page reflects the current risk/remediation state without another synchronization job. Search filters avoid non-stored computed fields to prevent Odoo domain errors.

## Current Validation

Local validation passed:

- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`
- `python tools\validate_addon.py`
- `git diff --check -- addons\sudo_country_pack_cn tools\validate_addon.py`

Server runtime validation is currently blocked because the PostgreSQL 16 main cluster on `43.165.173.80` is down and its data directory `/var/lib/postgresql/16/main` is missing. Do not recreate or initialize the database cluster without a confirmed backup/restore plan.

## Follow-Up

- Restore or confirm the PostgreSQL data directory before running Odoo upgrade tests.
- Upgrade an isolated copy of the China test database with `sudo_country_pack_cn 19.0.1.29.0`.
- Verify the workbench visually in the browser across normal and small laptop screen sizes.
- Continue M33 with deeper UX for risk drill-down and report-readiness scoring.
