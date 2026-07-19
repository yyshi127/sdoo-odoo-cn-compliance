# China Fiscal Compliance Pack Production Sign-off Template

Use this template after automated delivery acceptance and business UAT are
complete. It records the decision to deploy, defer or reject a release candidate.
It is not a tax opinion.

## How To Use This Template

Complete this template after generating the delivery status and sign-off action
packet for the release candidate. Use the latest numbered `mNNN` evidence set
for the exact candidate under review:

- `dist/cn_delivery_status_mNNN.json`
- `dist/cn_delivery_status_mNNN.md`
- `dist/cn_signoff_packet_mNNN.json`
- `dist/cn_signoff_packet_mNNN.md`
- `dist/cn_delivery_acceptance_mNNN_remote.json`
- `dist/cn_delivery_acceptance_mNNN_upgrade_remote.json`
- `docs/CHINA_PRODUCTION_RELEASE_CONTROL.md`
- `dist/sdoo-cn-compliance-delivery-mNNN.bundle.json`
- `dist/cn_delivery_manifest_mNNN_full.json`

Confirm that all selected `mNNN` files point to the same delivery version,
source commit, manifest aggregate hash and remote runtime acceptance result.

Use the Markdown files for reviewer walkthroughs and the JSON files for audit
traceability. Do not copy placeholder text into the final sign-off evidence.
Every reviewer, date, decision and evidence reference must point to a real
record such as a completed checklist, meeting minutes, signed review packet,
screenshot set, recording, ticket, audit workpaper or release approval.

Choose `defer` or `reject` instead of `deploy` when any of the following is
true:

- Automated delivery status is not `business_uat_ready=true`.
- Odoo runtime acceptance did not pass on a clean runtime database.
- The preview database module version does not match the release package.
- Business UAT has not explicitly accepted the release.
- China tax professional rule/source sign-off is missing for rules used in
  formal conclusions.
- Official-source freshness or local jurisdiction scope was not reviewed for the
  target period.
- Customer-specific accounting, external tax data, evidence, open risk or
  remediation gaps remain unresolved and are not formally accepted as
  limitations.
- Risk center, remediation tracker, controlled AI guidance, filing/payment
  archive or report pages are not readable enough for the intended users.
- Rollback owner, rollback trigger or go-live monitoring owner is missing.

If the decision is `deploy with limitations`, list every limitation with a
specific owner, due date, monitoring action and customer-facing boundary
statement. The machine-readable sign-off evidence must use a matching limitation
decision and include substantive limitation notes.

## Release Candidate

- Delivery version:
- Git commit:
- Bundle SHA-256:
- Manifest aggregate SHA-256:
- Acceptance summary path:
- Delivery status path:
- Target Odoo version:
- Target database or staging database:
- Review date:
- Sign-off action packet path:
- Sign-off evidence JSON path:
- Release owner:
- Rollback owner:

## Automated Evidence

- Delivery manifest verified: yes / no
- Bundle metadata verified: yes / no
- Artifact verifier passed: yes / no
- Odoo runtime acceptance result: passed / failed / not run
- Odoo upgrade runtime acceptance result: passed / failed / not run
- Runtime failed tests:
- Runtime errors:
- Production release-control checklist included in manifest: yes / no
- Backup, restore, rollback trigger and monitoring controls reviewed: yes / no
- Objective coverage matrix included in manifest: yes / no
- Business UAT checklist included in manifest: yes / no
- Business UAT walkthrough script included in manifest: yes / no
- Official source governance summary ready: true / false
- Official source governance issue count reviewed: yes / no
- Delivery status `business_uat_ready`: true / false
- Delivery status `production_signoff_ready` before human evidence: false / unexpected true
- Sign-off packet generated from the same source commit: yes / no
- All automated evidence paths archived: yes / no

## Business UAT Result

- UAT database:
- Company:
- Review period:
- Business reviewer:
- Technical reviewer:
- China tax professional reviewer:
- Decision: accepted / accepted with limitations / rejected
- Representative datasets reviewed:
- Controlled AI guidance evidence reviewed: yes / no / not applicable
- Controlled AI guidance evidence reference:
- Controlled AI guidance checksum evidence complete: yes / no / not applicable
- AI limitation and professional warning disclosure reviewed: yes / no / not applicable
- Screens checked:
- Completed UAT walkthrough script reference:
- Blocker-summary walkthrough evidence:
- Blocker-summary walkthrough decision: passed / passed with limitations / failed
- Workbench next-action and limitation summary readable: yes / no
- Risk center risk level, reason, impact amount and next action readable: yes / no
- Remediation tracker owner, due date, status and rescan state readable: yes / no
- Report center/report readiness blockers readable: yes / no
- Filing/payment archive integrity and evidence status readable: yes / no
- Open usability issues:

## Rule And Source Governance

- Released rules reviewed for official source governance: yes / no / not applicable
- Rule versions requiring China tax professional sign-off:
- Rule versions signed off:
- Candidate/draft rules still excluded from formal conclusions: yes / no
- Official-source freshness reviewed: yes / no / not applicable
- Local jurisdiction scope reviewed: yes / no / not applicable
- Official-source freshness evidence reference:
- Official source governance summary evidence reference:
- Latest official-source monitor run reviewed:
- Latest monitor run state and completion time:
- Latest monitor result integrity state:
- Latest monitor result checksum (64-character SHA-256):
- Overdue official-source reviews:
- Changed source monitor runs:
- Failed source monitor runs:
- Changed or failed monitor run disposition:
- Rule governance issues:
- Local jurisdiction review evidence reference:
- Rules not approved for production conclusions:

## Data And Scope Limitations

- Accounting periods covered:
- Posted accounting entries complete for reviewed periods: yes / no
- Draft accounting entries requiring review:
- External datasets complete: yes / no
- Partial datasets or missing sources:
- Evidence gaps:
- Controlled AI limitations or excluded findings:
- Known conclusion limitations:
- External tax/invoice/payment data acquisition basis reviewed: yes / no / not applicable
- Data sufficiency reviewer:
- Customer-facing limitation statement:

## Risk And Remediation Status

- Open critical risks:
- Open high risks:
- Open remediation tasks:
- Overdue remediation tasks:
- Pending verification rescans:
- Failed verification rescans:
- Report readiness state:
- Filing/payment archive issues:
- Data readiness blockers reviewed: yes / no / not applicable
- Evidence blockers reviewed: yes / no / not applicable
- Remediation blockers reviewed: yes / no / not applicable
- Report blockers reviewed: yes / no / not applicable
- Report readiness blockers reviewed: yes / no / not applicable
- Accepted unresolved risks or limitations:
- Risks requiring pre-go-live remediation:

## Deployment Decision

- Decision: deploy / deploy with limitations / defer / reject
- Required pre-go-live actions:
- Required post-go-live monitoring:
- Rollback owner:
- Rollback trigger:
- Approval names and dates:
- Deployment window:
- Post-go-live evidence retention location:
- Customer communication owner:

## Boundary Statement

This sign-off confirms that the software release candidate, delivery evidence,
business UAT and known limitations have been reviewed for deployment readiness.
It does not certify that a real taxpayer's filings are legally correct. Formal
China tax conclusions still require current official sources, customer-specific
facts, reviewed evidence and qualified professional judgment.
