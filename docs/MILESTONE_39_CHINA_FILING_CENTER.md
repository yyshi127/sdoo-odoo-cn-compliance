# M39 China Filing Center

## Summary

M39 adds a China-specific filing and payment archive center. It centralizes controlled VAT, CIT, and IIT filing archives so users can inspect submission state, payment/refund state, evidence readiness, integrity status, and next action from one Odoo-native entry point.

## Delivered

- Added display fields on `sudo.compliance.filing`:
  - China filing kind,
  - period label,
  - next action,
  - evidence state,
  - evidence count,
  - verified evidence count.
- Added a workbench drill-down action on `sudo.compliance.profile`.
- Added China filing center search/list/kanban views.
- Added `中国申报缴款档案` menu and action.
- Added country pack capability flag `china_filing_center`.
- Bumped `sudo_country_pack_cn` to `19.0.1.36.0`.

## Design Boundary

The filing center is a viewing and navigation layer. It does not submit tax filings, connect to tax authorities, infer legal deadlines, infer tax payable, or bypass the existing evidence and archive sealing controls.

Each card points back to the existing governed filing record and surfaces:

- controlled source type,
- filing period,
- submission and payment/refund states,
- submission/payment archive integrity,
- verified formal evidence coverage,
- conservative next action.

## Validation

Local validation should include:

- XML parse check for `views/filing_center_views.xml`.
- Python compile check.
- `python tools\validate_addon.py`.
- `git diff --check`.

Server runtime validation remains blocked until PostgreSQL on `43.165.173.80` is restored or an alternate Odoo database is provided.
