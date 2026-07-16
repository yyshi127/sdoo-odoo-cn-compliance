# M35 China Controlled AI Guidance

## Summary

M35 adds a controlled AI guidance entry point for China compliance findings. It does not let AI create legal, tax, audit, or regulatory conclusions. Instead, it creates immutable `sudo.compliance.ai.analysis` snapshots using the existing global finance AI audit model.

## Delivered

- Added `action_generate_cn_ai_guidance` on `sudo.compliance.finding`.
- Added deterministic fallback guidance using frozen finding fields:
  - risk level,
  - result,
  - period,
  - rule code/version,
  - professional conclusion,
  - legal basis,
  - remediation recommendation,
  - evidence requirements,
  - source/professional warning flags,
  - missing fact/parameter notes,
  - current remediation task status.
- Created AI analysis snapshots with:
  - provider key `sdoo_cn_controlled_guidance`,
  - jurisdiction `CN`,
  - state `fallback`,
  - prompt version `cn-compliance-guidance-v1`,
  - model name `sdoo-cn-guidance-fallback-v1`,
  - input checksum,
  - output checksum,
  - record checksum.
- Added buttons on China finding forms and China risk center cards.
- Added AI guidance count to finding lists/cards.
- Added country pack capability flag `china_controlled_ai_guidance`.
- Bumped `sudo_country_pack_cn` to `19.0.1.32.0`.

## Design Boundary

This milestone deliberately uses the existing immutable AI analysis model. The generated text is marked as auxiliary material and is excluded from becoming a formal conclusion or evidence. Formal reports freeze AI metadata only, consistent with the existing compliance report design.

Future external LLM integration can replace the fallback text provider only if it preserves:

- controlled prompt versioning,
- input snapshot hashing,
- output hashing,
- immutable record checksums,
- source/professional warning disclosure,
- no direct mutation of findings, tasks, evidence, reports, or rules.

## Validation

Local validation should include:

- Python compile check.
- XML parse check for `views/ai_guidance_views.xml`.
- `python tools\validate_addon.py`.
- `git diff --check`.

Server runtime validation remains blocked until PostgreSQL on `43.165.173.80` is restored.
