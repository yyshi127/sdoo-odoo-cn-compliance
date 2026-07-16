# M65 - China Data Readiness Search View Hotfix

## Scope

This milestone fixes a runtime Odoo view loading error found while upgrading the isolated demo database. The data readiness search view used the non-stored computed field `integrity_state` in search filter and group-by domains, which Odoo 19 rejects during view validation.

## Delivered

- Bumped `sudo_country_pack_cn` to `19.0.1.62.0`.
- Added the `19.0.1.62.0` migration hook to refresh country-pack metadata on upgrade.
- Removed the data readiness search filter on `integrity_state`.
- Removed the data readiness group-by option on `integrity_state`.
- Kept integrity visibility in list and kanban badges, where non-stored computed fields are safe for display.
- Added validator guards so future search views cannot reintroduce a domain or group-by on non-searchable `integrity_state`.

## Validation

- `python tools\validate_addon.py`
- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`
- `git diff --check`
- XML parse check for:
  - `addons\sudo_country_pack_cn\views\data_readiness_center_views.xml`
  - `addons\sudo_country_pack_cn\data\country_pack_data.xml`

## Package

- Artifact: `dist\codex-cn-m65-country-v1.tgz`
- SHA256: `EB97AE007A6813355D8579CED92F0D6E586FA27308A24147D926C356D7D995EC`
