# M49 China Cross-Border Transaction Register

## Objective

M49 adds a controlled cross-border transaction register to the China country pack. The goal is to capture reviewable facts for cross-border contracts, payments, royalties, service fees, related-party indicators, withholding consideration and evidence before those facts are used by scans or report limitations.

This milestone deliberately does not produce a tax, treaty, transfer-pricing, customs, VAT or foreign-exchange conclusion. It records governed facts, review state, evidence and a frozen checksum so later rules can consume a traceable basis.

## Delivered

- New Odoo model: `sudo.cn.cross.border.transaction`.
- Controlled lifecycle: draft -> submitted -> reviewed or cancelled.
- Manager-only submit/review/cancel actions.
- China-only profile constraint and non-China counterparty constraint.
- Period/date and positive amount validation.
- Evidence attachment register.
- Reviewed records are immutable and store `snapshot_checksum`.
- Workbench integration:
  - transaction count,
  - pending review count,
  - cross-border domain state becomes `attention` when pending facts exist,
  - direct workbench action to the register.
- Kanban/list/form/search views and a menu entry.
- ACL and multi-company record rule.
- Migration hook for `19.0.1.46.0`.
- Runtime tests covering feature advertisement, workbench visibility, action domain, review checksum and immutability.
- Validator coverage for metadata, manifest loading, model import, model/view/security/test contracts.

## Validation

Commands executed:

```powershell
python -m compileall addons\sudo_country_pack_cn tools\validate_addon.py
python tools\validate_addon.py
git diff --check
```

Result:

```text
validated sudo_country_pack_cn 19.0.1.46.0
```

## Package

- Package: `dist/codex-cn-m49-country-v1.tgz`
- SHA256: `7CD851482542AC2EAE0257BF3720FA510D4F10067E80FBEC53284AD6783DF404`
