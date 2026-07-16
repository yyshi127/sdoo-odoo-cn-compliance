# M55 China Assessment Obligation Basis

## Purpose

China compliance assessments and report readiness views should expose whether the scan perimeter rests on reviewed tax obligations. Before this milestone, the workbench and formal report could show obligation readiness, but the assessment/report-readiness page did not directly reveal whether the scan itself was produced while obligations were still unconfirmed.

## Delivered

- Added the `china_assessment_obligation_basis` country-pack capability.
- Added assessment-level obligation basis fields:
  - `cn_obligation_basis_state`
  - `cn_obligation_basis_candidate_count`
  - `cn_obligation_basis_applicable_count`
  - `cn_obligation_basis_pending_count`
  - `cn_obligation_basis_filing_count`
  - `cn_obligation_basis_next_action`
- Added an assessment action to open the profile-scoped obligation list.
- Added obligation-basis visibility to China report readiness list, kanban and inherited assessment form views.
- Added runtime coverage for default unreviewed obligations, navigation and reviewed-obligation readiness.
- Added upgrade migration metadata refresh for `19.0.1.52.0`.

## Boundary

This milestone does not make a legal applicability decision. It projects the existing controlled compliance-profile obligation state into the assessment layer, so users can see whether scan and report conclusions still carry a tax-obligation perimeter limitation.

## Validation

- `python tools\validate_addon.py`
- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`

## Package

- `dist/codex-cn-m55-country-v1.tgz`
- SHA256: `7D5410D53CDEAE7A7A785A94B3E1E2F0F1D98176FAB394719A2FDB948A241170`
