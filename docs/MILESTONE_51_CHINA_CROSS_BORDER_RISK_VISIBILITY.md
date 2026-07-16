# M51 China Cross-Border Risk Visibility

## Objective

M51 improves the risk-center reading experience for cross-border rule findings. M50 made cross-border transaction records available to rule scans; this milestone makes the resulting findings explain the cross-border fact status directly in the risk center.

The display remains a data-readiness and review-status view. It does not state withholding tax, treaty relief, transfer pricing, customs, VAT, foreign exchange, penalty or underpayment conclusions.

## Delivered

- New computed finding fields:
  - `cn_cross_border_fact_state`
  - `cn_cross_border_pending_count`
  - `cn_cross_border_reviewed_count`
  - `cn_cross_border_transaction_count`
  - `cn_cross_border_next_action`
- Risk center list and kanban now show cross-border fact status when a finding is driven by `CN.CROSS_BORDER` facts.
- The summary reads the actual rule fact snapshots:
  - `cn.cross_border.pending_review_count`
  - `cn.cross_border.reviewed_transaction_count`
  - `cn.cross_border.detail`
- Runtime test proves that:
  - pending cross-border records produce a failed finding and `pending_review` display state,
  - reviewed records produce a passing finding and `reviewed` display state.
- Country-pack capability flag:
  - `china_cross_border_risk_visibility`
- Upgrade migration for `19.0.1.48.0` refreshes country-pack metadata.
- Validator coverage now requires the model fields, risk-center UI fields, capability flag and runtime test.

## Validation

Commands executed:

```powershell
python -m compileall addons\sudo_country_pack_cn tools\validate_addon.py
python tools\validate_addon.py
git diff --check
```

Result:

```text
validated sudo_country_pack_cn 19.0.1.48.0
```

## Package

- Package: `dist/codex-cn-m51-country-v1.tgz`
- SHA256: `26A44081F7E386D41E8EA05EA3FEA899FF49158F010329437462FD0850579B58`
