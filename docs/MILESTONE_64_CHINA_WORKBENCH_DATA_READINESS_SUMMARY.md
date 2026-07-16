# M64 - China Workbench Data Readiness Summary

## Scope

This milestone makes the China compliance workbench show whether controlled source data is ready before users run rule scans. It closes a UX gap where the first workflow step only linked to the data readiness center but did not summarize readiness.

## Delivered

- Added `china_workbench_data_readiness_summary` to China country-pack capabilities.
- Bumped `sudo_country_pack_cn` to `19.0.1.61.0`.
- Added the `19.0.1.61.0` migration hook to refresh country-pack metadata on upgrade.
- Added workbench computed fields:
  - `cn_workbench_data_state`
  - `cn_workbench_data_next_action`
  - `cn_workbench_dataset_count`
  - `cn_workbench_ready_dataset_count`
- Summarized controlled `sudo.cn.external.dataset` records on the main workbench:
  - no current datasets -> `not_started`
  - blocked dataset integrity/authenticity -> `blocked`
  - all current datasets ready -> `ready`
  - partial/pending preparation -> `attention`
- Updated the workflow step `0 数据准备` to show a real status badge and ready/total dataset counts.
- Extended runtime tests and validator checks for the new workbench summary.

## Validation

- `python tools\validate_addon.py`
- `python -m compileall -q addons\sudo_country_pack_cn tools\validate_addon.py`
- `git diff --check`
- XML parse check for:
  - `addons\sudo_country_pack_cn\views\workbench_views.xml`
  - `addons\sudo_country_pack_cn\data\country_pack_data.xml`

## Package

- Artifact: `dist\codex-cn-m64-country-v1.tgz`
- SHA256: `5CDE82921B23C50631AC7C15FE27E7D20A7B785974EE3A558856D8E08CC29E3A`
