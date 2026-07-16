# Milestone 45 - China Workbench Tax Domain Overview

## Purpose

This milestone makes the China compliance workbench visibly China-specific. The workbench already summarized risk, remediation, evidence, and report readiness, but the first screen still looked like a generic compliance dashboard. Users need to immediately see that the installed package covers China fiscal compliance domains.

## Delivered

- Adds China package identity fields on `sudo.compliance.profile`:
  - `cn_workbench_package_label`
  - `cn_workbench_scope_label`
- Adds tax-domain state and next-action fields:
  - VAT: `cn_workbench_vat_domain_state`, `cn_workbench_vat_next_action`
  - CIT: `cn_workbench_cit_domain_state`, `cn_workbench_cit_next_action`
  - IIT: `cn_workbench_iit_domain_state`, `cn_workbench_iit_next_action`
- Adds VAT, CIT, and IIT cards to the China workbench kanban.
- Reuses existing reconciliation issue counts and action methods; no rule result semantics changed.
- Advertises the capability as `china_workbench_tax_domain_overview`.

## User Experience Boundary

The domain cards are orientation and navigation surfaces. They do not create new tax conclusions, calculate tax payable, or replace the governed rule engine. They tell users where to look first and expose the current problem count for each major China tax domain.

## Validation

- XML parse check for `views/workbench_views.xml`.
- Python compile check for the China addon and validator.
- `tools/validate_addon.py` verifies:
  - capability metadata
  - model fields
  - kanban fields and buttons
  - runtime test coverage markers

## Acceptance Criteria

- The China workbench card explicitly shows `中国财税合规包`.
- The workbench shows a China scope summary covering VAT, CIT, IIT, e-invoice, filing/payment, evidence, and formal reports.
- VAT, CIT, and IIT each have a visible state badge, next-action text, issue count, and navigation button.
- Existing workbench process flow remains available below the tax-domain overview.
