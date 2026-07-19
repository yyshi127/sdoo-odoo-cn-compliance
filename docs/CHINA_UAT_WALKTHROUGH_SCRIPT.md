# China Fiscal Compliance Pack UAT Walkthrough Script

This script turns the business UAT checklist into a reviewer-facing screen
walkthrough. Use it on the representative preview database and attach the
completed script, screenshots or recording reference to the production sign-off
evidence.

It is not a tax opinion. It proves that reviewers could understand the workflow,
visible risks, limitations and next actions on representative data.

## Session Header

- Delivery version:
- Git commit:
- Preview URL:
- Database:
- Company:
- Review period:
- Reviewer:
- Reviewer role:
- Screen sizes used:
- Date:
- Recording or screenshot folder:

## Pass Criteria

Mark the walkthrough as failed or accepted with limitations if any of the
following happens:

- The reviewer cannot identify the current company, period or profile state.
- A blocked, limited or uncertain result looks like a clean pass.
- Risk level, reason, impact amount, period, owner, due date, status or next
  action is missing from the relevant page.
- The risk center must make risk level, reason, impact amount, applicable period, owner, due date, status and next action clear without opening technical fields.
- Controlled AI guidance lacks provider, prompt version, checksum or warning
  disclosure.
- Controlled AI guidance evidence must show provider, prompt version, model, input checksum, output checksum and record checksum.
- Evidence, filing/payment archive, report or remediation state cannot be traced
  back to the related risk or assessment.
- Important labels, buttons, badges or next actions overlap or disappear on the
  target desktop or laptop screen.
- Navigation no longer feels native to Odoo menus, actions, forms, lists or
  kanban views.

## 1. Compliance Workbench

Open the China compliance workbench from the Odoo menu.

Record:

- Workbench profile:
- Company and period visible: yes / no
- Next best action visible: yes / no
- Rule basis summary visible: yes / no
- Data readiness summary visible: yes / no
- Limitation summary visible: yes / no
- Uncertainty summary visible: yes / no
- Screenshot reference:

Reviewer checks:

- Does the page explain whether the current profile is ready, blocked, limited
  or attention-needed?
- Can the reviewer understand the next action without opening developer tools or
  reading raw JSON?
- Does clicking the next action open the expected Odoo page?

Decision: passed / passed with limitations / failed

Notes:

## 2. Profile, Taxpayer Identity And Obligations

Open the profile identity, taxpayer classification, jurisdiction and obligation
records from the workbench or related menus.

Record:

- Taxpayer identity reviewed: yes / no
- Jurisdiction reviewed: yes / no
- Applicable obligations reviewed: yes / no
- Pending obligations are visibly limited: yes / no
- Source and justification visible: yes / no
- Screenshot reference:

Reviewer checks:

- Are country, jurisdiction and taxpayer identity fields visible enough for
  review?
- Are pending obligations clearly different from accepted obligations?
- Are missing UEN/taxpayer identifiers or classification gaps presented as
  blockers or limitations?

Decision: passed / passed with limitations / failed

Notes:

## 3. Data Readiness And External Datasets

Open data readiness and representative external dataset records.

Record:

- Accounting period reviewed:
- Posted entries visible: yes / no
- Draft entries or excluded entries visible: yes / no / not applicable
- External dataset period/source/coverage visible: yes / no
- Integrity/authenticity state visible: yes / no
- Missing or partial data limitation visible: yes / no / not applicable
- Screenshot reference:

Reviewer checks:

- Can the reviewer distinguish real posted accounting evidence from draft or
  excluded entries?
- Are invoice, filing, payment, payroll and withholding datasets traceable to a
  source, period and integrity state?
- Does missing data prevent a clean conclusion?

Decision: passed / passed with limitations / failed

Notes:

## 4. Rule Scan And Assessment

Open the latest assessment or run a representative scan.

Record:

- Assessment:
- Period:
- Rule version visible: yes / no
- Data basis visible: yes / no
- Jurisdiction coverage visible: yes / no
- Candidate/draft rule boundary visible: yes / no / not applicable
- Screenshot reference:

Reviewer checks:

- Is the scan result tied to period, company, data basis and rule version?
- Are draft or candidate rules prevented from looking like signed-off
  professional conclusions?

Decision: passed / passed with limitations / failed

Notes:

## 5. Risk Center

Open representative high, critical, low and informational risks if available.

Record:

- Risk record:
- Risk level visible: yes / no
- Reason visible: yes / no
- Affected period visible: yes / no
- Impact amount visible or explicitly unavailable: yes / no
- Rule/source basis visible: yes / no
- Evidence requirement visible: yes / no
- Next action visible: yes / no
- Screenshot reference:

Reviewer checks:

- Are high/critical risks visually distinct from lower-risk items?
- Can the reviewer understand why the risk exists and what to do next?
- Are source, professional, fact or parameter limitations shown where relevant?

Decision: passed / passed with limitations / failed

Notes:

## 6. Remediation Tracker

Open representative remediation tasks.

Record:

- Task:
- Owner visible: yes / no
- Due date visible: yes / no
- Task state visible: yes / no
- Evidence state visible: yes / no
- Verification rescan state visible: yes / no
- Overdue or failed rescan visually clear: yes / no / not applicable
- Screenshot reference:

Reviewer checks:

- Can the reviewer see who owns the task and whether it is late?
- Can the reviewer trace the task back to the risk and forward to the evidence
  and verification assessment?
- Are blocked tasks and failed rescans clear enough to prevent premature report
  sign-off?

Decision: passed / passed with limitations / failed

Notes:

## 7. Controlled AI Guidance

Open representative controlled AI guidance from a finding or workbench action.

Record:

- AI guidance:
- Provider visible: yes / no
- Prompt version visible: yes / no
- Model visible: yes / no
- Input checksum visible: yes / no
- Output checksum visible: yes / no
- Record checksum visible: yes / no
- Source/professional/fact warnings visible: yes / no / not applicable
- Screenshot reference:

Reviewer checks:

- Does the guidance clearly read as assistance rather than a tax opinion?
- Are missing facts, missing parameters and professional warnings disclosed?
- Can the reviewer trace the guidance to controlled input and output checksums?

Decision: passed / passed with limitations / failed

Notes:

## 8. Report Readiness And Compliance Report

Open report readiness and representative formal reports.

Record:

- Report readiness record:
- Report:
- Scope visible: yes / no
- Period visible: yes / no
- Rules visible: yes / no
- Findings visible: yes / no
- Remediation visible: yes / no
- Evidence visible: yes / no
- Limitations visible: yes / no
- Conclusion state visible: yes / no
- Screenshot reference:

Reviewer checks:

- Do report readiness blockers explain what must be done before sign-off?
- Does the report disclose scope, evidence basis, limitations and uncertainty?
- Are unsealed snapshots, missing approvals or PDF integrity gaps visible?

Decision: passed / passed with limitations / failed

Notes:

## 9. Evidence, Filing And Payment Archives

Open representative evidence and filing/payment archive records.

Record:

- Evidence record:
- Filing/payment archive:
- Linked risk/task/report visible: yes / no
- Submission integrity visible: yes / no / not applicable
- Payment integrity visible: yes / no / not applicable
- Evidence integrity visible: yes / no
- Checksums visible: yes / no
- Changed or invalid evidence blocked: yes / no / not applicable
- Screenshot reference:

Reviewer checks:

- Can the reviewer trace evidence to a finding, task, report or filing archive?
- Does the archive separate submission, payment and evidence integrity?
- Can changed or invalid evidence be detected rather than hidden?

Decision: passed / passed with limitations / failed

Notes:

## 10. Tax Domain Samples

Verify that the representative database includes ready evidence for each target
domain in the delivery status.

The walkthrough must cover VAT, CIT, IIT and cross-border domains when the
representative dataset contains those obligations.

| Domain | Reviewed record | Ready in status | Reviewer decision | Evidence reference |
| --- | --- | --- | --- | --- |
| VAT invoice / filing / payment |  | yes / no | passed / limited / failed |  |
| CIT accounting / filing |  | yes / no | passed / limited / failed |  |
| IIT payroll / withholding / payment |  | yes / no | passed / limited / failed |  |
| Cross-border and withholding review |  | yes / no | passed / limited / failed |  |

Notes:

## 11. Screen-Size And Native Odoo UX Check

Repeat the workbench, risk center, remediation tracker and report readiness
screens on the target screen sizes.

Record:

- Browser and version:
- Desktop viewport or resolution:
- Smaller laptop viewport or resolution:
- Text overlap found: yes / no
- Buttons or badges ambiguous: yes / no
- Important action hidden: yes / no
- Navigation follows Odoo menu/list/form/action expectations: yes / no

Required screen evidence:

| Page | Desktop evidence reference | Smaller laptop evidence reference | Reviewer decision |
| --- | --- | --- | --- |
| Compliance workbench |  |  | passed / limited / failed |
| Risk center |  |  | passed / limited / failed |
| Remediation tracker |  |  | passed / limited / failed |
| Report readiness |  |  | passed / limited / failed |

For each page, confirm that risk level, reason, impact amount, applicable
period, owner, due date, status, blockers and next action remain readable
without opening developer tools or relying on raw technical fields.

Decision: passed / passed with limitations / failed

Notes:

## Final UAT Decision

- Decision: accepted / accepted with limitations / rejected
- Limitations accepted:
- Issues requiring fixes before production:
- Reviewer:
- Reviewer role:
- Date:
- Evidence package location:

Boundary statement:

Business UAT confirms that reviewers can operate and understand the China
compliance workflow on representative data. It does not certify that a real
taxpayer filing position is legally correct. Production still requires current
official sources, China tax professional rule/source sign-off and
customer-specific data completeness review.
