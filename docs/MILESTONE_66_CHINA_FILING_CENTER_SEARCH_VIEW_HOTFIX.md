# M66 - China Filing Center Search View Hotfix

## Scope

This milestone fixes a second runtime Odoo view validation issue found during isolated demo database upgrade. The China filing center search view filtered on non-stored computed integrity/evidence fields, which Odoo 19 rejects in search domains.

## Delivered

- Bumped `sudo_country_pack_cn` to `19.0.1.63.0`.
- Added the `19.0.1.63.0` migration hook to refresh country-pack metadata on upgrade.
- Removed search filters on:
  - `cn_submission_integrity_state`
  - `cn_payment_integrity_state`
  - `cn_filing_center_evidence_state`
- Kept these fields visible as list and kanban badges, where they are safe display fields.
- Added validator guards so non-searchable computed filing status fields cannot be reintroduced into search domains.
- Normalized post-migration scripts from `migrate(env, version)` to the Odoo runtime signature `migrate(cr, version)` and added validator coverage for this upgrade-chain requirement.

## Validation

- `python tools\validate_addon.py`
- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`
- `git diff --check`
- XML parse check for:
  - `addons\sudo_country_pack_cn\views\filing_center_views.xml`
  - `addons\sudo_country_pack_cn\data\country_pack_data.xml`

## Package

- Artifact: `dist\codex-cn-m66-country-v1.tgz`
- SHA256: `C7131603304C51E547D40A5632B980F662C5A9EF8CF92FA69390941E71AB5621`
