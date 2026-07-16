# M57 - China Workbench Filing Archive Summary

## Purpose

M57 extends the China compliance workbench so the end-to-end compliance loop does not stop at risk, remediation, evidence and formal reports. The workbench now summarizes controlled filing and payment archives created from VAT, CIT and IIT reconciliation runs.

This is meant to answer one practical delivery question for a reviewer:

> After rules are scanned, risks are handled and a report is issued, are the filing/payment archives sealed and supported by verified evidence?

## Delivered Scope

- Added workbench computed fields on `sudo.compliance.profile`:
  - `cn_workbench_filing_archive_state`
  - `cn_workbench_filing_archive_next_action`
  - `cn_workbench_filing_archive_count`
  - `cn_workbench_sealed_filing_archive_count`
  - `cn_workbench_filing_archive_issue_count`
- Added a controlled filing archive domain covering China VAT, CIT and IIT filing archives.
- Added filing archive closure logic:
  - `not_started` when no controlled filing archives exist.
  - `attention` when filing/payment integrity is changed, invalid or unsealed, or formal evidence is not fully verified.
  - `ready` when all controlled filing archives are sealed and supported by verified evidence.
- Added the archive summary to the China workbench kanban and form.
- Added the filing archive summary as step 6 in the workbench end-to-end flow.
- Added capability flag `china_workbench_filing_archive_summary`.
- Added migration `19.0.1.54.0` to refresh country-pack metadata.

## Acceptance Checks

- The country pack declares `china_workbench_filing_archive_summary`.
- The workbench model contains all filing archive summary fields.
- The workbench kanban/form expose the archive summary.
- Workbench tests cover the default archive state and navigation into the filing center.
- `tools/validate_addon.py` enforces the feature contract.

## Package

- Package: `dist/codex-cn-m57-country-v1.tgz`
- SHA256: `F9C8A12B98EE20EA037844932BE16F3E5F1BDC631A6CFFFD87D28F2A78993763`
