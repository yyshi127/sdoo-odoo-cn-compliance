# M59 - China Risk Card State Badge Clarity

## Purpose

M59 improves the China risk center and remediation tracker card experience. The goal is to make risk review and整改跟踪 immediately readable from kanban cards, so users can distinguish high-risk, failed, blocked, pending, verified and ready states without opening each record.

This keeps the Odoo-native menu and record model while improving the review-oriented UX required by the China compliance objective.

## Delivered Scope

- Added capability flag `china_risk_card_state_badge_clarity`.
- Added native Odoo badge decorations to China risk center kanban cards:
  - risk level;
  - rule result;
  - rule-basis readiness;
  - AI guidance state;
  - human review state;
  - evidence state;
  - cross-border fact state;
  - traceability state;
  - remediation task state;
  - verification state.
- Added native Odoo badge decorations to remediation tracker kanban cards:
  - risk level and priority;
  - remediation evidence state;
  - traceability state;
  - task state;
  - verification/rescan stage.
- Added upgrade migration `19.0.1.56.0` to refresh country-pack metadata.
- Updated validator checks so future edits cannot silently remove the card badge-state contract.

## Acceptance Checks

- `tools/validate_addon.py` validates version `19.0.1.56.0`.
- Risk center XML contains native `decoration-*` expressions for critical risk and remediation card states.
- Risk center runtime tests assert the capability flag is published.

## Package

- Package: `dist/codex-cn-m59-country-v1.tgz`
- SHA256: `56CAC628069DEAEB891428CC141C6E9AFE1BA6302325A629AC60FEE72B64ACBA`
