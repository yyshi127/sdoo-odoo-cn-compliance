# China Fiscal Compliance Pack Objective Coverage

This document maps the delivery objective to auditable evidence in the
`sudo_country_pack_cn` delivery bundle. It is a delivery-control document, not a
legal opinion.

## Coverage Matrix

| Objective area | Current coverage | Evidence in bundle | Production boundary |
| --- | --- | --- | --- |
| Installable and upgradeable Odoo 19 plugin | Main China country pack and optional XBRL parser are packaged as standard Odoo addons with versioned migrations. | `addons/sudo_country_pack_cn/__manifest__.py`, `addons/sudo_country_pack_cn/migrations/`, `addons/sudo_country_pack_cn_einvoice_xbrl/`, delivery bundle metadata. | Production deployment still requires an isolated restore or staging upgrade before touching a live database. |
| Auditable delivery package | Bundle, manifest, acceptance summary, status summary, objective completion audit, sign-off packet, version-aligned sign-off evidence draft and sign-off validation carry deterministic file inventory, SHA-256 evidence and human sign-off action items. | `tools/run_cn_delivery_acceptance.py`, `tools/build_cn_delivery_bundle.py`, `tools/verify_cn_delivery_artifacts.py`, `tools/summarize_cn_delivery_status.py`, `tools/audit_cn_objective_completion.py`, `tools/generate_cn_signoff_packet.py`, `tools/render_cn_signoff_evidence_template.py`, `tools/validate_cn_signoff_evidence.py`. | Delivery evidence proves software-package integrity and records required human decisions; it does not prove the correctness of a customer's tax position. |
| Odoo accounting and business-data basis | Rule facts and workbench summaries expose posted/draft accounting entries, invoice counts and period-scoped accounting basis. | `models/assessment_data_basis.py`, `models/workbench.py`, `tests/test_assessment_data_basis.py`, `tests/test_workbench.py`. | Real customer ledgers must be posted, complete for the scanned period and reconciled to external tax data before conclusions are reliable. |
| External tax data and data sufficiency | External datasets, normalization, sealing, authenticity/integrity checks and data readiness center make data gaps visible. | `models/external_dataset.py`, `models/data_readiness_center.py`, `views/data_readiness_center_views.xml`, `docs/samples/`, `tests/test_data_readiness_center.py`. | The system does not legally obtain data by itself; users must provide lawfully obtained invoices, filings, payments and payroll/tax exports. |
| Source-governed and versioned rules | Candidate China rules, source records, rule versions, release readiness and review packets are governed and auditable. | `data/compliance_rule_drafts.xml`, `data/rule_review_candidates.xml`, `models/rule_governance.py`, `reports/rule_review_packet_report.xml`, `tests/test_rule_drafts.py`. | Candidate or draft rules are not official professional conclusions until reviewed, sourced and signed off by qualified China tax professionals. |
| National and local scope | Jurisdiction assignment, local rule scope and coverage states are represented and can block limited scans. | `models/jurisdiction.py`, `views/jurisdiction_views.xml`, `tests/test_jurisdiction.py`. | Local implementation still requires jurisdiction-specific source maintenance and professional validation for each supported province/city. |
| Risk discovery and fact traceability | Risk center exposes risk level, facts, rule basis, data basis, tax impact and remediation guidance. | `models/risk_center.py`, `views/risk_center_views.xml`, `tests/test_risk_center.py`. | A failed scan is a controlled risk indicator; human review remains required before management action or filing changes. |
| VAT, CIT and IIT reconciliation | VAT invoice/filing/payment, CIT accounting/filing and IIT payroll/withholding reconciliation flows create scoped issues and remediation links. | `models/invoice_reconciliation.py`, `models/vat_period_reconciliation.py`, `models/cit_period_reconciliation.py`, `models/iit_period_reconciliation.py`, related tests. | Coverage depends on configured account scopes, complete source data and customer-specific tax classifications. |
| Cross-border and withholding controls | Taxpayer classification and cross-border transaction register expose withholding and nonresident boundaries. | `models/cross_border.py`, `views/cross_border_views.xml`, `tests/test_workbench.py`. | Cross-border tax treatment is highly fact-specific and must be reviewed against contracts, payments, services and treaty/source rules. |
| Human review, remediation and verification rescan | Findings create remediation tasks; tasks carry responsibility, review state, evidence and verification rescan status. | `models/risk_center.py`, `models/workbench.py`, `tests/test_vat_period_reconciliation.py`, `tests/test_report_readiness.py`. | Operational owners must actually complete tasks and attach evidence; the system cannot guarantee execution outside Odoo. |
| Evidence, reports, filing and payment archives | Evidence center, formal report, report readiness and filing/payment archives preserve support and limitations. | `models/evidence_center.py`, `models/compliance_report.py`, `models/report_readiness.py`, `models/filing_center.py`, report XML and tests. | Report output is only as reliable as reviewed rules, complete data, verified evidence and sign-off controls. |
| Controlled AI guidance | AI guidance is generated from controlled snapshots and exposes missing facts, limitations and professional warnings. | `models/ai_guidance.py`, `tests/test_ai_guidance.py`, report and workbench AI guidance fields. | AI guidance assists explanation and step-by-step handling; it does not replace rule-engine results or professional China tax judgment. |
| User experience for overview and next action | Workbench, risk center, report readiness, data readiness, evidence, filing/payment archive and formal report pages make state, blockers and next actions visible; workbench offers a next-best-action entry point. | `views/workbench_views.xml`, `models/workbench.py`, `views/risk_center_views.xml`, `views/report_readiness_views.xml`, `models/data_readiness_center.py`, `models/evidence_center.py`, `models/filing_center.py`, `docs/MILESTONE_70_CHINA_BLOCKER_SUMMARY_VISIBILITY.md`, related tests. | Final user acceptance still requires walkthrough on a representative customer dataset and screen-size/browser checks. |
| Multi-company, security and native Odoo operation | Menus, actions, access files, domains and profile-scoped actions follow native Odoo patterns. | `security/`, `views/*.xml`, `tests/test_workbench.py`, `tests/test_data_readiness_center.py`, `tests/test_filing_center.py`. | Production groups and record rules should be reviewed with the customer's Odoo security policy. |

## Delivery Acceptance Evidence

Release candidates should include:

- deterministic delivery bundle and bundle metadata;
- delivery manifest with per-file SHA-256 checksums;
- acceptance summary generated by `tools/run_cn_delivery_acceptance.py`;
- artifact verification generated by `tools/verify_cn_delivery_artifacts.py`;
- delivery status summary generated by `tools/summarize_cn_delivery_status.py`;
- objective completion audit generated by `tools/audit_cn_objective_completion.py`;
- production sign-off action packet generated by `tools/generate_cn_signoff_packet.py`;
- missing-human-evidence items mapped to the objective areas they are meant to prove;
- production sign-off evidence draft generated by `tools/render_cn_signoff_evidence_template.py` from the current packet, then production sign-off evidence validation generated by `tools/validate_cn_signoff_evidence.py` when human approvals are complete, including blocked objective areas and the production blockers still addressed by missing or invalid human evidence;
- Odoo runtime test log with `0 failed / 0 errors` for the selected acceptance profile.

## Not A Completion Claim

Passing delivery acceptance means the packaged software and runtime regression
suite are consistent. It does not prove that every China tax rule has been
published, that every local rule is current, or that a customer's actual filing
position is correct. Production readiness still requires:

- current official-source maintenance;
- China tax professional review and sign-off for released rules;
- customer-specific data onboarding and completeness review;
- representative user acceptance testing;
- controlled deployment into the target Odoo environment.
