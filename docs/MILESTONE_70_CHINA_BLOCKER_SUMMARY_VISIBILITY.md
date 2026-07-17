# Milestone 70 - China Blocker Summary Visibility

## Purpose

This milestone records the final visibility pass for reviewer-facing blockers
across the China fiscal compliance closed loop. The objective is to make the
reason for a blocked, limited or not-yet-ready state visible in the list and
kanban pages that business reviewers use during UAT.

## Delivered Visibility

The following centers now expose a readable blocker or limitation summary:

- Data readiness center: shows why an external dataset is not audit-ready.
- Evidence center: shows the evidence source and why evidence is not closed.
- Filing/payment archive center: shows why filing, payment or evidence archive
  reliance is blocked.
- Report center: shows formal report blockers such as open remediation,
  missing evidence, approval state and traceability gaps.
- Report readiness center: shows why an assessment cannot be used for a formal
  report, or why it can only be reported with limitations.
- Remediation tracker: shows remaining blockers before a task can support
  report sign-off.

## User Acceptance Focus

Business UAT should verify that the following fields are readable without
opening every record:

- risk level and closure state;
- affected period;
- owner, due date and remediation status;
- impact amount or tax-impact status;
- data, evidence, filing and report blockers;
- next action for the reviewer or operator.

The expected reviewer behavior is simple: if a card or list row is not ready,
the visible blocker summary should explain why and point to the next page or
action needed to close it.

## Implementation Evidence

Recent commits that form this milestone:

- `bba1ad5` - data readiness blockers.
- `c745e8f` - evidence center source and blockers.
- `2c5f007` - filing/payment archive blockers.
- `a6db8d8` - report readiness blockers.

Representative files:

- `addons/sudo_country_pack_cn/models/data_readiness_center.py`
- `addons/sudo_country_pack_cn/models/evidence_center.py`
- `addons/sudo_country_pack_cn/models/filing_center.py`
- `addons/sudo_country_pack_cn/models/report_readiness.py`
- `addons/sudo_country_pack_cn/models/risk_center.py`
- `addons/sudo_country_pack_cn/views/*_views.xml`
- `addons/sudo_country_pack_cn/tests/`

## Boundary

These blocker summaries are operational and audit-readiness indicators. They do
not certify a taxpayer position, replace China tax professional sign-off, or
remove the need for customer-specific data completeness review.
