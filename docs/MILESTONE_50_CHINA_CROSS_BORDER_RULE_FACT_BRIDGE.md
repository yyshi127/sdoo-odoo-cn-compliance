# M50 China Cross-Border Rule Fact Bridge

## Objective

M50 connects the controlled cross-border transaction register to the China rule engine. M49 created the governed register; this milestone makes those records visible to rule scans as auditable facts and adds a draft data-readiness rule.

The scope remains deliberately limited: the rule does not determine withholding tax, treaty relief, transfer pricing, customs, VAT, foreign exchange, tax rate, filing deadline, penalty or underpayment. It only determines whether cross-border facts captured for the assessment period still require controlled review before professional analysis can rely on them.

## Delivered

- New fact providers:
  - `cn.cross_border.pending_review_count`
  - `cn.cross_border.reviewed_transaction_count`
  - `cn.cross_border.detail`
- New fact snapshot schema:
  - `sdoo.cn.cross-border-facts.v1`
- New fact definitions in `compliance_fact_data.xml`.
- New draft rule:
  - `CN-CROSS-BORDER-CTRL-001`
  - `rule_version_cn_cross_border_ready_001_draft`
- New pass/fail packaged rule test cases.
- New professional review packet and three supporting citations.
- Runtime test covering the provider period snapshot and reviewed checksum propagation.
- Validator coverage for the new feature flag, fact keys, provider methods, schema, draft rule, test cases and review packet governance.
- Upgrade migration for `19.0.1.47.0` that refreshes metadata and links candidate official sources without replacing existing rule source links.

## Validation

Commands executed:

```powershell
python tools\validate_addon.py
```

Result:

```text
validated sudo_country_pack_cn 19.0.1.47.0
```

Additional commands executed:

```powershell
python -m compileall addons\sudo_country_pack_cn tools\validate_addon.py
git diff --check
```

## Package

- Package: `dist/codex-cn-m50-country-v1.tgz`
- SHA256: `8A10FBD68D0436FF0B6B531DACE9AB7F50D4F53B2C23ED3B37399583B98F06BB`
