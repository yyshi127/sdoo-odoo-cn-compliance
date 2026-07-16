# Milestone 67: China Runtime View Guard

## Scope

Version: `19.0.1.64.0`

This milestone closes another class of upgrade/runtime failures found during the
China compliance package hardening pass.

## Changes

- Added a validator that scans China addon models for non-stored computed fields.
- The validator now rejects search view filters, search group-by contexts, and
  view-level `default_group_by` attributes that reference those fields unless
  the field is stored or has an explicit search implementation.
- Removed the China filing center's unsafe grouping by the computed
  `cn_filing_center_kind` field.
- Kept the filing kind visible as a badge in the filing center cards and list,
  so user-facing clarity is preserved without using an invalid database group.

## Why It Matters

Odoo cannot group or search on a computed field unless it is stored or provides a
search method. This guard catches those issues locally before packaging or
database upgrade, instead of letting users discover them as white screens,
internal server errors, or failed module upgrades.

## Validation

- `python tools\validate_addon.py`
- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`
- `git diff --check`

## Artifact

- Package: `dist\codex-cn-m67-country-v1.tgz`
- SHA-256: `FCBD4E5122A649AD492916F25C488F490FB04DC566A8AB5F00B31DBD47C9A52B`
- Remote dev DB upgrade: `codex_cn_m31_demo_01` upgraded to
  `19.0.1.64.0|installed`.
