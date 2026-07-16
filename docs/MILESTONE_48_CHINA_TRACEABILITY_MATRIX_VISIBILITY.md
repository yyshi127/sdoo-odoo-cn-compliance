# M48 China Traceability Matrix Visibility

## Summary

This milestone adds a visible traceability layer across the China compliance flow:

- risk finding -> rule basis -> review -> remediation -> evidence -> tax impact;
- remediation task -> closure -> verification rescan -> evidence;
- formal report -> frozen snapshot -> integrity checks -> evidence and unresolved gaps.

The goal is to make the review experience clearer: a user can see whether an item is
report-ready, blocked, or still action-required without opening multiple records.

## Changes

- Added traceability state, gap count, and next-action fields to China risk findings.
- Added traceability state, gap count, and next-action fields to remediation tasks.
- Added report traceability state, gap count, and next-action fields to formal reports.
- Added navigation from a risk finding to its related evidence.
- Added navigation from a formal report to the evidence included in its report scope.
- Surfaced traceability status in risk center, remediation tracker, and formal report center views.
- Declared `china_traceability_matrix_visibility` in the China country pack capabilities.
- Added a migration to refresh country pack metadata during upgrade to `19.0.1.45.0`.

## Validation

- `python -m compileall addons\sudo_country_pack_cn`
- `python tools\validate_addon.py`
- Package: `dist/codex-cn-m48-country-v1.tgz`
- SHA-256: `D846DE29F9E74C7540F6462F6827E45B110F72DC74AC4A877AD9DD1C37727DB1`

## Notes

This milestone does not change rule evaluation semantics. It is a visibility and
workflow-guidance layer over the existing controlled evidence, remediation, and report
models.
