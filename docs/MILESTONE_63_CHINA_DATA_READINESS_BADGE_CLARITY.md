# M63 - China Data Readiness Badge Clarity

## Scope

This milestone improves the China data readiness center so users can distinguish usable, pending, blocked, and superseded data sources at a glance before running compliance scans.

## Delivered

- Added `china_data_readiness_badge_clarity` to the China country-pack capability metadata.
- Bumped `sudo_country_pack_cn` to `19.0.1.60.0`.
- Added the `19.0.1.60.0` migration hook to refresh country-pack metadata on upgrade.
- Clarified badge decorations in the data readiness list and kanban views:
  - readiness stage
  - dataset seal state
  - file integrity state
  - authenticity verification state
  - review control state
- Exposed `review_control_state` in the data readiness center so users can see whether source data has independent review, is still pending review, or is under a single-review exception.
- Extended runtime test coverage and local validator checks to prevent badge clarity regressions.

## Validation

- `python tools\validate_addon.py`
- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`
- `git diff --check`
- XML parse check for:
  - `addons\sudo_country_pack_cn\views\data_readiness_center_views.xml`
  - `addons\sudo_country_pack_cn\data\country_pack_data.xml`

## Package

- Artifact: `dist\codex-cn-m63-country-v1.tgz`
- SHA256: `26B5CE63EE50294902A18B0A22F91F77AF8C678E52DC053EA11E30215F6D44E3`
