# China Fiscal Compliance Pack Release Handoff

This handoff is the reviewer-facing entry point for the current China fiscal
compliance pack release candidate. It avoids pinning the document name to a
single milestone number so the same instructions remain usable as the delivery
bundle is rebuilt.

## Current Release Evidence

Delivery version: `19.0.1.144.0`

For the current production sign-off workflow, use
`docs/CHINA_CURRENT_PRODUCTION_SIGNOFF_RUNBOOK.md` before completing
`docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md`.

Select the latest verified `mNNN` evidence set in `dist/` and confirm the
candidate number, commit and manifest hash from the selected status file before
review.

Use the latest numbered files in `dist/` for the active release candidate:

- delivery package: `dist/sdoo-cn-compliance-delivery-m*.tgz`
- delivery metadata: `dist/sdoo-cn-compliance-delivery-m*.bundle.json`
- delivery manifest: `dist/cn_delivery_manifest_m*_full.json`
- local acceptance: `dist/cn_delivery_acceptance_m*_local.json`
- remote acceptance: `dist/cn_delivery_acceptance_m*_remote.json`
- remote upgrade acceptance: `dist/cn_delivery_acceptance_m*_upgrade_remote.json`
- delivery status: `dist/cn_delivery_status_m*.md`
- objective completion audit: `dist/cn_objective_completion_audit_m*.md`
- sign-off packet: `dist/cn_signoff_packet_m*.md`

Always confirm the exact source commit in the selected delivery status file:

- `Source branch`
- `Source commit`
- `Source worktree dirty`
- `Acceptance passed`
- `Runtime passed`
- `Business UAT ready`
- `Production sign-off ready`

Also confirm that
`dist/cn_delivery_mNNN_chain_latest_signoff_candidate.md` reports no selector
errors, and that
`dist/cn_delivery_mNNN_chain_production_signoff_actions.md` includes both the
owner summary and the blocker-to-action matrix before reviewer sign-off begins.
These sections are part of the current audit contract: every remaining
production blocker must map to at least one human action, and every action owner
must be visible to the reviewer.

For the last verified candidate before this handoff was generalized, the latest
status file showed `business_uat_ready=true` and
`production_signoff_ready=false`. That is the expected state before completed
human sign-off evidence.

## Remote Preview And Runtime Evidence

- Remote host: `43.165.173.80`
- Remote delivery directory: `/tmp/codex_cn_m31`
- Preview database: `codex_cn_m31_demo_01`
- Runtime database pattern: `codex_cn_m31_runtime_mNNN`
- Preview URL pattern:
  `http://127.0.0.1:18070/web/login?db=codex_cn_m31_demo_01`
- Odoo Python: `/opt/odoo/odoo19/odoo19-venv/bin/python`
- Odoo server: `/opt/odoo/odoo19/odoo-server/odoo-bin`
- Odoo config: `/tmp/codex_cn_m31/odoo-dev.conf`

Do not store private keys, passwords, customer data, production database dumps or
filestore backups in this repository or in the delivery bundle.

## What Is Ready

The release candidate can move to business UAT when the selected delivery
status shows all of the following:

- `Acceptance passed: True`
- `Runtime passed: True`
- `Source worktree dirty: False`
- `Business UAT checklist in manifest: True`
- `Business UAT walkthrough script in manifest: True`
- `Objective coverage in manifest: True`
- `Production sign-off template in manifest: True`
- `Production release-control checklist in manifest: True`
- `Preview health ok: True`
- `Preview module ok: True`
- `Real-data closed-loop evidence ready: True`
- `Official source governance summary ready: True`
- formal reports revalidate current official-source links, source hashes,
  source validity and professional sign-off against the assessment snapshot;
- Odoo 19 card views use the supported `card` template and load without legacy
  kanban-template errors;
- the Chinese workbench uses concise risk, remediation and closed-loop summaries,
  with translated conclusion, rule-basis and next-action guidance;
- `Business UAT ready: True`

The sign-off packet should expose automated evidence for delivery integrity,
runtime acceptance, preview health, real-data closed-loop evidence, UAT
walkthrough script inclusion, workbench/risk/remediation/report/evidence
summaries, official source governance, IIT payroll withholding scope and
cross-border review scope. The production sign-off action checklist should
then translate the remaining human gates into owner-specific action lists and a
blocker coverage matrix, making the handoff auditable without asking reviewers
to infer blocker ownership from free text.

## What Is Not Yet Complete

Production sign-off is intentionally blocked until all of the following are
completed and validated:

- representative business UAT;
- completed `docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md`;
- China tax professional review of released rules and official sources;
- current official-source freshness and local jurisdiction review;
- customer-specific accounting, external tax data, evidence gap and open risk
  review;
- final deploy, deploy-with-limitations, defer or reject decision;
- validated machine-readable sign-off evidence rendered from the current
  sign-off packet with `tools/render_cn_signoff_evidence_template.py`, then
  completed from real reviewer evidence.

This release candidate is not a China tax opinion and does not certify any real
taxpayer filing position.

## Reproduce Local Acceptance

Replace `mNNN` with the next delivery number for the current run:

```bash
python tools/run_cn_delivery_acceptance.py \
  --profile full \
  --write-manifest dist/cn_delivery_manifest_mNNN_full.json \
  --write-summary dist/cn_delivery_acceptance_mNNN_local.json

python tools/build_cn_delivery_bundle.py \
  --output dist/sdoo-cn-compliance-delivery-mNNN.tgz \
  --metadata dist/sdoo-cn-compliance-delivery-mNNN.bundle.json

python tools/verify_cn_delivery_artifacts.py \
  --bundle dist/sdoo-cn-compliance-delivery-mNNN.tgz \
  --bundle-metadata dist/sdoo-cn-compliance-delivery-mNNN.bundle.json \
  --manifest dist/cn_delivery_manifest_mNNN_full.json \
  --summary dist/cn_delivery_acceptance_mNNN_local.json
```

## Reproduce Remote Runtime Acceptance

Upload the selected bundle to `/tmp/codex_cn_m31/dist/`, then run it in an
isolated runtime database:

```bash
cd /tmp/codex_cn_m31
tar -xzf dist/sdoo-cn-compliance-delivery-mNNN.tgz
chown -R odoo:odoo /tmp/codex_cn_m31
sudo -u odoo /opt/odoo/odoo19/odoo19-venv/bin/python \
  tools/run_cn_delivery_acceptance.py \
  --profile full \
  --python-bin /opt/odoo/odoo19/odoo19-venv/bin/python \
  --odoo-bin /opt/odoo/odoo19/odoo-server/odoo-bin \
  --config /tmp/codex_cn_m31/odoo-dev.conf \
  --database codex_cn_m31_runtime_mNNN \
  --install \
  --http-port 18NNN \
  --logfile dist/cn_delivery_runtime_mNNN_clean.log \
  --write-summary dist/cn_delivery_acceptance_mNNN_remote.json
```

## Generate Ordered Status And Sign-Off Chain

```bash
sudo -u odoo /opt/odoo/odoo19/odoo19-venv/bin/python \
  tools/build_cn_signoff_evidence_chain.py \
  --bundle-metadata dist/sdoo-cn-compliance-delivery-mNNN.bundle.json \
  --manifest dist/cn_delivery_manifest_mNNN_full.json \
  --summary dist/cn_delivery_acceptance_mNNN_remote.json \
  --upgrade-summary dist/cn_delivery_acceptance_mNNN_upgrade_remote.json \
  --preview-health dist/cn_preview_health_mNNN.json \
  --preview-module dist/cn_preview_module_mNNN.json \
  --real-data-closed-loop dist/cn_real_data_closed_loop_mNNN.json \
  --preview-url 'http://127.0.0.1:18070/web/login?db=codex_cn_m31_demo_01' \
  --output-prefix dist/cn_delivery_mNNN_chain
```

This is the preferred release command. It creates the initial status,
bootstrap validation, objective completion audit, final sign-off packet, final
evidence draft, final validation and final status in the correct order.
The chain output names correspond to the prior handoff artifacts:
`cn_objective_completion_audit_mNNN.json`,
`cn_signoff_packet_mNNN.json` and `cn_signoff_evidence_draft_mNNN.json`.
For one-step troubleshooting, the underlying tools are still
`tools/summarize_cn_delivery_status.py`, `tools/generate_cn_signoff_packet.py`,
`tools/audit_cn_objective_completion.py`,
`tools/render_cn_signoff_evidence_template.py` and
`tools/validate_cn_signoff_evidence.py`.

## Validate Completed Production Sign-Off

The rendered draft from the chain copies the release version, source commit and
production action keys from the final packet. It is intentionally not valid for
production while reviewer, date, evidence reference and notes placeholders
remain.

After human reviewers complete real evidence, create a non-template completed
evidence file from the rendered draft and rerun the ordered chain:

```bash
python tools/build_cn_signoff_evidence_chain.py \
  --bundle-metadata dist/sdoo-cn-compliance-delivery-mNNN.bundle.json \
  --manifest dist/cn_delivery_manifest_mNNN_full.json \
  --summary dist/cn_delivery_acceptance_mNNN_remote.json \
  --upgrade-summary dist/cn_delivery_acceptance_mNNN_upgrade_remote.json \
  --preview-health dist/cn_preview_health_mNNN.json \
  --preview-module dist/cn_preview_module_mNNN.json \
  --real-data-closed-loop dist/cn_real_data_closed_loop_mNNN.json \
  --preview-url 'http://127.0.0.1:18070/web/login?db=codex_cn_m31_demo_01' \
  --completed-evidence dist/cn_signoff_evidence_completed.json \
  --output-prefix dist/cn_delivery_mNNN_signed_chain
```

Only a passed final chain validation can make `production_signoff_ready=true`.

## Next Best Work

1. Run the UAT walkthrough with a business reviewer on representative data.
2. Capture screenshots or recording references for workbench, risk center,
   remediation tracker, AI guidance, filing/payment archive and reports.
3. Have a China tax professional sign off released rules and official sources.
4. Review current official-source freshness and local jurisdiction scope.
5. Validate completed sign-off evidence and regenerate the final delivery
   status with `--require-production-signoff-ready`.
