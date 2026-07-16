# Milestone 68: China Workbench Remediation Rescan Summary

## Scope

Version: `19.0.1.65.0`

This milestone makes the China compliance workbench show the verification
rescan part of the remediation loop directly on the first screen.

## Changes

- Added workbench fields for:
  - remediation verification rescan state,
  - pending verification rescan count,
  - failed verification rescan count,
  - verified remediation count,
  - verification rescan next action.
- Added the verification rescan state into the workbench end-to-end flow.
- Added a compact workbench card showing pending, failed, and verified
  remediation counts.
- Added a country-pack capability flag:
  `china_workbench_remediation_rescan_summary`.
- Added runtime test coverage for pending, failed, and verified remediation
  rescan summaries.
- Strengthened `tools/validate_addon.py` so this capability, UI surface, and
  test coverage remain part of the package contract.

## Why It Matters

The target compliance loop is not complete at "task created" or "task closed".
Users need to know whether the corrective action has been verified by a rescan,
whether a rescan is still pending, and whether a failed rescan requires reopening
the remediation. This makes that status visible without drilling into every
task record.

## Validation

- `python tools\validate_addon.py`
- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`
- `git diff --check`

## Artifact

- Package: `dist\codex-cn-m68-country-v1.tgz`
- SHA-256: `DE473F27420A7117B933D86C9094D2E15BC3F261855500C6ECE498402569251F`
- Remote dev DB upgrade: `codex_cn_m31_demo_01` upgraded to
  `19.0.1.65.0|installed`.
- Runtime test: `TestChinaComplianceWorkbench.test_workbench_summarizes_remediation_rescan_status`
  passed on `codex_cn_m31_demo_01` with `0 failed, 0 error(s)`.
