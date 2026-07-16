# M53 China AI Obligation Context

## Objective

M53 connects China tax-obligation readiness to controlled AI guidance. The previous milestone made obligation readiness visible in the workbench; this milestone freezes that readiness into every generated AI guidance snapshot so users do not treat scan results as complete when the underlying tax obligations are still candidates.

The feature does not let AI determine whether VAT, CIT, IIT, surcharge, stamp duty, social insurance, records retention or any other obligation applies. It only exposes the governed profile state that already exists in Odoo.

## Delivered

- Adds `obligation_readiness` to `_cn_ai_guidance_input()` with:
  - readiness state,
  - next action,
  - candidate obligation count,
  - applicable obligation count,
  - pending-review obligation count,
  - applicable filing obligation count.
- Marks AI guidance as `limited` when the profile has no seeded obligations or still has obligations requiring review.
- Adds an obligation-readiness section to generated guidance text.
- Adds an explicit action step requiring obligation applicability and official sources to be confirmed before using scan results for filing or report conclusions.
- Country-pack capability flag:
  - `china_ai_obligation_context`
- Upgrade migration for `19.0.1.50.0` refreshes country-pack metadata.
- Runtime tests cover:
  - pending obligations making AI guidance limited,
  - obligation readiness being frozen into the AI input snapshot,
  - reviewed obligations restoring `ready`,
  - feature metadata.
- Validator coverage now requires the new capability, AI payload key, model contract and runtime tests.

## Boundary

AI remains a controlled explanation and operational guidance layer. It cannot create legal conclusions, cannot approve rules, cannot decide taxpayer obligation applicability, cannot override missing official sources, and cannot replace professional review.

## Validation

Commands executed:

```powershell
python -m py_compile addons\sudo_country_pack_cn\models\ai_guidance.py addons\sudo_country_pack_cn\hooks.py addons\sudo_country_pack_cn\migrations\19.0.1.50.0\post-migration.py tools\validate_addon.py
python tools\validate_addon.py
```

Result:

```text
validated sudo_country_pack_cn 19.0.1.50.0
```

## Package

- Package: `dist/codex-cn-m53-country-v1.tgz`
- SHA256: `64AB7A133D7254007845E8DF058B1F726A1F7614D9F020D79D95120A7EB589C5`
