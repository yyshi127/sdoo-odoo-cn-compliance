# Milestone 47 - China AI Guidance Visibility

## Purpose

The China package already generated controlled AI guidance for actionable findings, but users had to open the finding and infer whether AI guidance was available or current. This milestone makes AI guidance readiness visible directly in the risk center.

## Delivered

- Adds AI guidance display fields on `sudo.compliance.finding`:
  - `cn_ai_guidance_state`
  - `cn_ai_guidance_next_action`
  - `cn_ai_guidance_input_checksum`
- Shows AI guidance state and next action in the China risk center list and kanban card.
- Shows the current controlled input checksum so reviewers can compare whether an existing AI guide was generated from the same controlled inputs.
- Advertises the capability as `china_ai_guidance_visibility`.

## Boundary

This milestone does not call an external AI model and does not make AI output authoritative. The generated guidance remains fallback controlled guidance derived from frozen rule results, fact snapshots, remediation recommendations, and evidence requirements. The UI explicitly treats AI as auxiliary workflow guidance.

## Validation

- XML parse check for `views/risk_center_views.xml`.
- Python compile check for the China addon and validator.
- `tools/validate_addon.py` verifies:
  - feature metadata
  - model fields
  - risk center visibility
  - runtime tests for ready, limited, and generated guidance states

## Acceptance Criteria

- Risk center list shows AI guidance state and next action.
- Risk center card shows AI guidance state, next action, and input checksum.
- Findings with clean actionable inputs show `ready`.
- Findings with source, professional, fact, or parameter limitations show `limited`.
- Findings with generated guidance show `generated`.
