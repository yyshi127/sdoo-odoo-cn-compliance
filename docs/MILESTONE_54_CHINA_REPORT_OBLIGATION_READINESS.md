# M54 China Report Obligation Readiness

## Purpose

Formal China compliance reports must not imply that the tax compliance perimeter is complete when candidate tax obligations have not been reviewed. This milestone freezes the China profile obligation readiness state into the report snapshot and surfaces it as a report limitation and traceability gap.

## Delivered

- Added the `china_report_obligation_readiness` country-pack capability.
- Added `obligation_readiness` to the formal report snapshot, including candidate, applicable, pending-review and filing-obligation counts.
- Added per-obligation snapshot rows with code, name, domain, applicability, source and filing metadata.
- Treated unreviewed obligation readiness as a material report limitation.
- Required a limitation statement before submitting a report when obligations are still unconfirmed.
- Added report HTML/PDF visibility for the obligation readiness boundary.
- Added traceability status guidance when report distribution still depends on obligation applicability review.
- Added upgrade migration metadata refresh for `19.0.1.51.0`.

## Validation Boundary

This milestone does not determine whether a tax obligation is legally applicable. It makes the limitation explicit, auditable and visible in the formal reporting flow so users cannot rely on a report without seeing the unresolved perimeter.

## Runtime Checks

- `test_pending_obligations_require_report_limitation`
- Existing formal report snapshot and traceability tests now include obligation readiness.
- `tools/validate_addon.py` requires the new capability, report snapshot contract and runtime coverage.

## Package

- `dist/codex-cn-m54-country-v1.tgz`
- SHA256: `67F8FBB138276B4CA6438D0639324DA21925DEECC4E487E5B0731DED828CEF50`
