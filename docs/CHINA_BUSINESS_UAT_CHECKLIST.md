# China Fiscal Compliance Pack Business UAT Checklist

This checklist is for business user acceptance on a representative Odoo database.
It complements automated delivery acceptance and does not replace legal or tax
professional review.

## Preconditions

- The target database is an isolated copy or dedicated test database.
- `sudo_country_pack_cn` is installed or upgraded to the delivery version.
- Accounting is installed and representative posted accounting entries exist for
  the review period.
- Representative external datasets are available where applicable: electronic
  invoices, VAT/CIT/IIT filings, tax payments, payroll or withholding exports,
  and supporting attachments.
- China tax obligations and taxpayer classification have been reviewed by the
  intended business reviewer or clearly marked as pending.

## Walkthrough

1. Open the China compliance workbench.
   - Confirm the correct company and period are visible.
   - Confirm the conclusion boundary clearly says whether the current result is
     blocked, limited, attention-needed or ready.
   - Click **Next Best Action** and confirm it opens the expected next page.

2. Review profile, identity and obligations.
   - Confirm the China profile is active for the company under review.
   - Confirm taxpayer classification, jurisdiction and local authority fields are
     complete or visibly limited.
   - Confirm each candidate tax obligation is applicable, not applicable or
     pending with a source and justification.

3. Review data readiness.
   - Confirm each external dataset shows period, source, coverage, integrity,
     authenticity and next action.
   - Confirm partial or missing source data is visible as a limitation and does
     not look like a clean compliance pass.
   - Confirm posted/draft accounting entry counts are consistent with the test
     period expectations.

4. Run or review rule scans.
   - Confirm completed assessments show period, rule versions, data basis and
     jurisdiction coverage.
   - Confirm draft/candidate rule status is visible and not presented as a final
     professional conclusion.

5. Review risks.
   - Confirm risk cards or lists show risk level, reason, affected period,
     rule/source basis, fact basis, data basis, tax impact, evidence requirement
     and next action.
   - Confirm high or critical risks are visually distinct from low-risk items.
   - Confirm limited facts, missing parameters or professional warnings are
     visible.

6. Review remediation.
   - Confirm remediation tasks show owner, due date, status, next action,
     evidence state and verification rescan state.
   - Confirm overdue or failed verification rescans are visually clear.
   - Confirm completed remediation has supporting evidence and a verification
     assessment link where required.

7. Review controlled AI guidance.
   - Confirm AI guidance is generated only from controlled snapshots.
   - Confirm missing fact, missing parameter, source and professional warnings are
     visible.
   - Confirm the guidance is framed as assistance, not as an official tax
     conclusion.

8. Review report readiness and formal reports.
   - Confirm report readiness gates block reports when data, obligations,
     remediation, rescans, filing archives, evidence or AI guidance disclosures
     are incomplete.
   - Generate or open a formal report and confirm it includes scope, period,
     rules, findings, remediation, evidence, limitations and conclusion state.

9. Review evidence, filing and payment archives.
   - Confirm evidence records are linked to findings, tasks, reports or filing
     archives.
   - Confirm filing/payment archives show submission, payment and evidence
     integrity status.
   - Confirm sealed archives cannot silently hide changed or invalid evidence.

10. Screen and usability checks.
    - Repeat the workbench, risk center, remediation tracker and report readiness
      walkthrough on a normal desktop and a smaller laptop screen.
    - Confirm important labels, badges, buttons and next actions do not overlap or
      disappear.
    - Confirm list, kanban and form navigation feels native to Odoo.

11. Review blocker-summary visibility.
    - Confirm data readiness, evidence center, filing/payment archive,
      remediation tracker, report center and report readiness pages show a
      visible blocker or limitation summary for non-ready records.
    - Confirm each blocker summary explains why the record is blocked, limited
      or pending, and what next page or action should be used to close it.
    - Capture screenshots, a short recording or a signed UAT note as evidence
      for the production `blocker_summary_walkthrough` sign-off action.

## Sign-off Notes

Record the following before marking a release candidate business-accepted:

- database name and date/time of walkthrough;
- delivery version and Git commit;
- review period and company;
- source datasets reviewed;
- unresolved limitations or data gaps;
- open high/critical risks;
- blocker-summary walkthrough evidence reference;
- reviewer name and role;
- decision: accepted, accepted with limitations, or rejected.

## Acceptance Boundary

Business UAT confirms that users can understand and operate the compliance
workflow on representative data. It does not certify that all China tax rules are
complete or that a real filing position is correct. Production use still depends
on current official sources, professional rule sign-off and customer-specific
data completeness.
