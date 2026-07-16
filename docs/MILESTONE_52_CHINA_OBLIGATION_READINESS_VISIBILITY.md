# M52 China Obligation Readiness Visibility

## Objective

M52 makes the China compliance workbench and compliance profile show whether China tax obligations have been reviewed before users rely on scans, filing archives or formal reports.

The feature remains a governance and readiness surface. It does not decide VAT, CIT, IIT, surcharge, stamp duty, social insurance, records retention or any other statutory obligation automatically. Candidate obligations still require official sources, company-level applicability review and professional signoff before they can support controlled filing workflows.

## Delivered

- New computed workbench fields on `sudo.compliance.profile`:
  - `cn_workbench_obligation_state`
  - `cn_workbench_obligation_next_action`
  - `cn_workbench_obligation_count`
  - `cn_workbench_applicable_obligation_count`
  - `cn_workbench_pending_obligation_count`
  - `cn_workbench_filing_obligation_count`
- The China workbench kanban now includes a tax-obligation readiness card before domain scans.
- The China workbench form now includes an obligation-readiness group.
- The compliance profile form now includes a China tax-obligation overview page with a clear warning when candidate obligations still need review.
- New navigation action:
  - `action_cn_open_workbench_obligations`
- Country-pack capability flag:
  - `china_obligation_readiness_visibility`
- Upgrade migration for `19.0.1.49.0` refreshes country-pack metadata and reseeds missing China candidate obligations.
- Runtime tests cover:
  - feature metadata,
  - initial pending-obligation counts,
  - obligation-list navigation,
  - readiness transition after applicability review.
- Validator coverage now requires the model fields, UI entry points, capability flag and runtime test markers.

## Readiness Logic

- No obligations: `not_started`.
- Unknown obligations, or applicable obligations without an authority source: `attention`.
- All obligations reviewed and sourced: `ready`.

If the profile is active but obligations still need review, the workbench status becomes `warning` and tells the user to confirm China tax-obligation applicability before treating scan results as complete.

## Validation

Commands executed:

```powershell
python -m py_compile addons\sudo_country_pack_cn\models\workbench.py addons\sudo_country_pack_cn\hooks.py addons\sudo_country_pack_cn\migrations\19.0.1.49.0\post-migration.py tools\validate_addon.py
python tools\validate_addon.py
```

Result:

```text
validated sudo_country_pack_cn 19.0.1.49.0
```

## Package

- Package: `dist/codex-cn-m52-country-v1.tgz`
- SHA256: `11221908944B8458BC99BF75B4C447215B79FAF8F5B24B248B427069F0ED7C42`
