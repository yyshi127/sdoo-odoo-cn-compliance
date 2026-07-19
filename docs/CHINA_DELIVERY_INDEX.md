# China Fiscal Compliance Pack Delivery Index

This is the starting point for release handoff and acceptance of the
`sudo_country_pack_cn` delivery bundle.

## Read Order

1. `docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md`
   - Confirms how the product objective maps to software evidence and known
     production boundaries.
2. `docs/CHINA_RELEASE_HANDOFF_CURRENT.md`
   - Gives the current release candidate, artifact paths, remote runtime
     evidence, reproduction commands, sign-off boundary and next-best work.
3. `docs/DELIVERY_RUNBOOK_CN.md`
   - Explains how to install, upgrade, build and verify the delivery bundle.
4. `docs/DEVELOPMENT_PREVIEW_ACCESS_CN.md`
   - Explains how to open an isolated development preview through a local SSH
     tunnel.
5. `docs/CHINA_BUSINESS_UAT_CHECKLIST.md`
   - Guides business reviewers through the workbench, data readiness, risk,
     remediation, AI guidance, report and evidence walkthrough.
6. `docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md`
   - Converts the business UAT checklist into a screen-by-screen reviewer script
     with pass/fail criteria and screenshot or recording evidence fields.
7. `docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md`
   - Records the final deploy, defer or reject decision after automated
     acceptance and business UAT.
8. `docs/MILESTONE_70_CHINA_BLOCKER_SUMMARY_VISIBILITY.md`
   - Summarizes the final blocker-summary visibility pass across data,
     evidence, filing, remediation, report and report-readiness pages.
9. `docs/CHINA_CURRENT_PRODUCTION_SIGNOFF_RUNBOOK.md`
   - Converts the latest verified automated evidence into the exact human
     production sign-off workflow and validation commands.

## Command Index

Build the deterministic delivery bundle:

```bash
python tools/build_cn_delivery_bundle.py \
  --output dist/sdoo-cn-compliance-delivery.tgz \
  --metadata dist/sdoo-cn-compliance-delivery.bundle.json
```

Run full automated acceptance:

```bash
python tools/run_cn_delivery_acceptance.py \
  --profile full \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database acceptance_database \
  --install \
  --logfile /tmp/cn_full_acceptance.log \
  --write-manifest /tmp/cn_delivery_manifest.json \
  --write-summary /tmp/cn_delivery_acceptance_summary.json
```

Verify delivery artifacts:

```bash
python tools/verify_cn_delivery_artifacts.py \
  --bundle dist/sdoo-cn-compliance-delivery.tgz \
  --bundle-metadata dist/sdoo-cn-compliance-delivery.bundle.json \
  --manifest dist/cn_delivery_manifest.json \
  --summary dist/cn_delivery_acceptance_summary.json
```

Summarize delivery status:

```bash
python tools/summarize_cn_delivery_status.py \
  --bundle-metadata dist/sdoo-cn-compliance-delivery.bundle.json \
  --manifest dist/cn_delivery_manifest.json \
  --summary dist/cn_delivery_acceptance_summary.json \
  --upgrade-summary dist/cn_delivery_acceptance_upgrade_summary.json \
  --preview-health dist/cn_preview_health.json \
  --preview-module dist/cn_preview_module.json \
  --real-data-closed-loop dist/cn_real_data_closed_loop.json \
  --preview-url http://127.0.0.1:18069/web/login?db=target_database \
  --require-business-uat-ready \
  --require-source-control-clean \
  --json-output dist/cn_delivery_status.json \
  --markdown-output dist/cn_delivery_status.md
```

The status summary includes machine-readable readiness gates for business UAT
and production sign-off. Business UAT readiness requires a passed preview health
check for the intended URL, and the preview health result URL must match the
status summary preview URL. It also requires the preview database to report the
expected installed `sudo_country_pack_cn` module version and synchronized
country-pack metadata. Production sign-off remains blocked until the
business UAT decision, current-source review, professional rule sign-off and
customer-specific limitations are recorded outside the automated status.
Use `--require-business-uat-ready` or `--require-production-signoff-ready` in
automation when a non-zero exit code should stop handoff.
Bundle metadata, delivery manifest, acceptance summary and status summary also
carry source-control evidence so reviewers can see the branch, commit and dirty
worktree state that produced the delivery artifact.
Artifact verification checks that the top-level `git_commit` matches the
structured source-control commit across bundle metadata, manifest and
acceptance summary.
Use `--require-source-control-clean` for formal release packaging when the
handoff must fail unless branch, commit and a clean worktree are recorded.

Build the ordered sign-off evidence chain from the current delivery evidence:

```bash
python tools/build_cn_signoff_evidence_chain.py \
  --bundle-metadata dist/sdoo-cn-compliance-delivery-mNNN.bundle.json \
  --manifest dist/cn_delivery_manifest_mNNN_full.json \
  --summary dist/cn_delivery_acceptance_mNNN_remote.json \
  --upgrade-summary dist/cn_delivery_acceptance_mNNN_upgrade_remote.json \
  --preview-health dist/cn_preview_health_mNNN.json \
  --preview-module dist/cn_preview_module_mNNN.json \
  --real-data-closed-loop dist/cn_real_data_closed_loop_mNNN.json \
  --preview-url http://127.0.0.1:8069/web/login?db=target_database \
  --output-prefix dist/cn_delivery_mNNN_chain
```

Use `tools/build_cn_signoff_evidence_chain.py` as the preferred release
command. It builds the initial status, bootstrap sign-off validation,
objective completion audit, final sign-off packet and final status in the
correct order so the final packet contains objective-audit evidence and the
final status keeps the current production blocker action list.

The lower-level commands remain available when a reviewer needs to inspect one
step at a time:

```bash
python tools/generate_cn_signoff_packet.py \
  --status dist/cn_delivery_status.json \
  --json-output dist/cn_signoff_packet.json \
  --markdown-output dist/cn_signoff_packet.md \
  --require-business-uat-ready
```

The sign-off packet converts automated evidence into a reviewer-facing action
list for business UAT, China tax professional rule/source sign-off,
official-source freshness review, customer data/scope gap review, representative
UX walkthrough, blocker-summary walkthrough and final deploy/defer/reject
decision. The walkthrough evidence must cover the workbench, risk center,
remediation tracking, controlled AI guidance, filing/payment archive and
compliance report pages, including whether risk level, cause, impact amount,
period, owner, due date, status, next action and controlled AI provider/prompt
checksum evidence are readable on representative desktop and laptop screen
sizes. The
blocker-summary walkthrough must separately confirm that data readiness,
evidence, filing/payment archive, remediation, report center and report
readiness blocker summaries, plus controlled AI guidance disclosures, explain
why non-ready records are blocked or limited. It intentionally keeps production
sign-off blocked until those human decisions and evidence references are
recorded.

Validate completed production sign-off evidence:

```bash
python tools/render_cn_signoff_evidence_template.py \
  --packet dist/cn_signoff_packet.json \
  --json-output dist/cn_signoff_evidence_draft.json

python tools/validate_cn_signoff_evidence.py \
  --packet dist/cn_signoff_packet.json \
  --evidence dist/cn_signoff_evidence_completed.json \
  --json-output dist/cn_signoff_validation.json \
  --require-production-signoff-ready
```

After validation passes, rerun `tools/build_cn_signoff_evidence_chain.py` with
`--completed-evidence dist/cn_signoff_evidence_completed.json`. Only then can
the automated status report `production_signoff_ready=true`.
Use `tools/render_cn_signoff_evidence_template.py` as the preferred starting
point for the machine-readable evidence file because it copies the current
packet version, source commit and action keys into the draft. Replace the
reviewers, dates, decisions, notes and evidence references with the actual
signed review records.
Template placeholders cannot pass validation. Reviewers and evidence references
must be real audit records, and dates must use ISO `YYYY-MM-DD` format such as
`2026-07-17`.

Generate an objective completion audit whenever the status file changes:

```bash
python tools/audit_cn_objective_completion.py \
  --status dist/cn_delivery_status.json \
  --json-output dist/cn_objective_completion_audit.json \
  --markdown-output dist/cn_objective_completion_audit.md
```

Check a preview URL before business UAT:

```bash
python tools/check_cn_preview_health.py \
  --url http://127.0.0.1:18069/web/login?db=target_database \
  --json-output dist/cn_preview_health.json
```

Check a copied real-data database before walkthroughs:

```bash
python tools/check_cn_real_data_closed_loop.py \
  --python-bin /opt/odoo/odoo19/odoo19-venv/bin/python \
  --odoo-bin /opt/odoo/odoo19/odoo-server/odoo-bin \
  --config /path/to/odoo.conf \
  --database copied_real_data_db \
  --expected-version 19.0.1.130.0 \
  --json-output dist/cn_real_data_closed_loop.json \
  --require-demo-ready
```

The real-data checker is read-only. It reports whether the current database has
installed China pack metadata, posted Odoo accounting data, China compliance
profiles, external tax or invoice data, reconciliation runs, risk/remediation
activity and formal report records. Use `--require-closed-loop-evidence` only
after the database is expected to contain reconciliation, risk/remediation and
report evidence.

For development walkthroughs only, a copied demo database can be prepared with
an explicitly marked demo profile setup:

```bash
python tools/prepare_cn_demo_profile.py \
  --python-bin /opt/odoo/odoo19/odoo19-venv/bin/python \
  --odoo-bin /opt/odoo/odoo19/odoo-server/odoo-bin \
  --config /path/to/odoo.conf \
  --database copied_demo_db \
  --company "新加坡内账" \
  --allow-demo-data \
  --json-output dist/cn_demo_profile_preparation.json
```

The preparer refuses to write unless `--allow-demo-data` is passed. It creates
`CODEX-DEMO` registration and taxpayer identity evidence only for a development
walkthrough. These records must never be treated as real taxpayer evidence or
used for production sign-off.

After the active China profile belongs to a company with posted accounting
ledger data, prepare the controlled demo closed loop:

```bash
python tools/prepare_cn_demo_closed_loop.py \
  --python-bin /opt/odoo/odoo19/odoo19-venv/bin/python \
  --odoo-bin /opt/odoo/odoo19/odoo-server/odoo-bin \
  --config /path/to/odoo.conf \
  --database copied_demo_db \
  --company "新加坡内账" \
  --allow-demo-data \
  --json-output dist/cn_demo_closed_loop_preparation.json
```

The closed-loop preparer creates clearly marked `CODEX-DEMO` rule-governance,
assessment, finding, remediation task and draft report records through the same
model actions used by the UI. It is development/UAT evidence only and is not a
real Chinese tax opinion.

## Release Candidate Is Ready For Business UAT When

- bundle, manifest and acceptance summary versions are consistent;
- artifact verification passes;
- automated acceptance result is `passed`;
- Odoo runtime log shows `0 failed / 0 errors`;
- delivery status reports these files are included in the manifest:
  - objective coverage matrix;
  - business UAT checklist;
  - production sign-off template;
  - preview health checker;
  - preview module checker;
  - real-data closed-loop checker;
  - controlled demo profile preparer;
  - controlled demo closed-loop preparer;
- preview health check returns `ok=true` for the intended preview URL.
- preview module check returns `ok=true` for the intended preview database.

## Release Candidate Is Ready For Production Sign-off When

- business UAT is accepted or accepted with documented limitations;
- current official sources and released rules have been reviewed;
- China tax professional sign-off status is recorded for released rules;
- data gaps, evidence gaps and open high/critical risks are documented;
- rollback owner and rollback trigger are recorded;
- the production sign-off template is completed and approved.

## Boundary

This index organizes delivery evidence. It does not certify a taxpayer's filing
position or replace China tax professional judgment.

