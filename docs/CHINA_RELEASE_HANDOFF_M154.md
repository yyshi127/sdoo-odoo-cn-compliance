# China Fiscal Compliance Pack Release Handoff - m154

This handoff is the reviewer-facing entry point for the current China fiscal
compliance pack release candidate. It is intentionally written in plain English
to avoid encoding loss in terminals, ticket systems and future chat handoffs.

## Current Release

- Delivery version: `19.0.1.130.0`
- Source branch: `main`
- Source commit: `d8ad9dbe27c43c8132a93da97fc3a879c2afeea1`
- Latest delivery package: `dist/sdoo-cn-compliance-delivery-m154.tgz`
- Latest delivery metadata: `dist/sdoo-cn-compliance-delivery-m154.bundle.json`
- Latest manifest: `dist/cn_delivery_manifest_m154_full.json`
- Latest local acceptance: `dist/cn_delivery_acceptance_m154_local.json`
- Latest remote acceptance: `dist/cn_delivery_acceptance_m154_remote.json`
- Latest delivery status: `dist/cn_delivery_status_m154.md`
- Latest sign-off packet: `dist/cn_signoff_packet_m154.md`

## Remote Preview And Runtime Evidence

- Remote host: `43.165.173.80`
- Remote delivery directory: `/tmp/codex_cn_m31`
- Preview database: `codex_cn_m31_demo_01`
- Latest clean runtime database: `codex_cn_m31_runtime_m154`
- Preview URL from delivery status:
  `http://127.0.0.1:8069/web/login?db=codex_cn_m31_demo_01`
- Odoo Python: `/opt/odoo/odoo19/odoo19-venv/bin/python`
- Odoo server: `/opt/odoo/odoo19/odoo-server/odoo-bin`
- Odoo config: `/tmp/codex_cn_m31/odoo-dev.conf`

Do not store private keys, passwords, customer data, production database dumps or
filestore backups in this repository or in the delivery bundle.

## What Is Ready

- The addon package is installable and upgradeable as an Odoo 19 addon.
- Local full acceptance passed with 94 tests.
- Remote clean-runtime Odoo acceptance passed on `codex_cn_m31_runtime_m154`.
- The delivery bundle, metadata, manifest and acceptance summary were verified
  for deterministic file inventory and SHA-256 consistency.
- The status summary reports `business_uat_ready=true`.
- The status summary reports `production_signoff_ready=false`, as expected
  before completed human evidence.
- The sign-off packet exposes automated evidence for:
  - delivery version consistency;
  - runtime acceptance;
  - clean source-control state;
  - preview health and preview module checks;
  - real-data closed-loop evidence;
  - UAT walkthrough script inclusion;
  - workbench, risk, remediation, report and evidence summaries;
  - official source governance summary;
  - IIT payroll withholding scope;
  - cross-border review scope.

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
- validated machine-readable sign-off evidence generated from
  `docs/samples/cn_signoff_evidence_template.json`.

This release candidate is not a China tax opinion and does not certify any real
taxpayer filing position.

## Reproduce Local Acceptance

From the repository root:

```bash
python tools/run_cn_delivery_acceptance.py \
  --profile full \
  --write-manifest dist/cn_delivery_manifest_m154_full.json \
  --write-summary dist/cn_delivery_acceptance_m154_local.json

python tools/build_cn_delivery_bundle.py \
  --output dist/sdoo-cn-compliance-delivery-m154.tgz \
  --metadata dist/sdoo-cn-compliance-delivery-m154.bundle.json

python tools/verify_cn_delivery_artifacts.py \
  --bundle dist/sdoo-cn-compliance-delivery-m154.tgz \
  --bundle-metadata dist/sdoo-cn-compliance-delivery-m154.bundle.json \
  --manifest dist/cn_delivery_manifest_m154_full.json \
  --summary dist/cn_delivery_acceptance_m154_local.json
```

## Reproduce Remote Runtime Acceptance

Run the same m154 bundle in an isolated runtime database:

```bash
cd /tmp/codex_cn_m31
tar -xzf dist/sdoo-cn-compliance-delivery-m154.tgz
chown -R odoo:odoo /tmp/codex_cn_m31
sudo -u odoo /opt/odoo/odoo19/odoo19-venv/bin/python \
  tools/run_cn_delivery_acceptance.py \
  --profile full \
  --python-bin /opt/odoo/odoo19/odoo19-venv/bin/python \
  --odoo-bin /opt/odoo/odoo19/odoo-server/odoo-bin \
  --config /tmp/codex_cn_m31/odoo-dev.conf \
  --database codex_cn_m31_runtime_m154 \
  --install \
  --http-port 18154 \
  --logfile dist/cn_delivery_runtime_m154_clean.log \
  --write-summary dist/cn_delivery_acceptance_m154_remote.json
```

## Generate Status And Sign-Off Packet

```bash
sudo -u odoo /opt/odoo/odoo19/odoo19-venv/bin/python \
  tools/summarize_cn_delivery_status.py \
  --bundle-metadata dist/sdoo-cn-compliance-delivery-m154.bundle.json \
  --manifest dist/cn_delivery_manifest_m154_full.json \
  --summary dist/cn_delivery_acceptance_m154_remote.json \
  --preview-health dist/cn_preview_health_m137.json \
  --preview-module dist/cn_preview_module_m137.json \
  --real-data-closed-loop dist/cn_real_data_closed_loop_m137.json \
  --preview-url 'http://127.0.0.1:8069/web/login?db=codex_cn_m31_demo_01' \
  --json-output dist/cn_delivery_status_m154.json \
  --markdown-output dist/cn_delivery_status_m154.md

sudo -u odoo /opt/odoo/odoo19/odoo19-venv/bin/python \
  tools/generate_cn_signoff_packet.py \
  --status dist/cn_delivery_status_m154.json \
  --json-output dist/cn_signoff_packet_m154.json \
  --markdown-output dist/cn_signoff_packet_m154.md \
  --require-business-uat-ready
```

## Validate Completed Production Sign-Off

After human reviewers complete real evidence, create a non-template evidence
file from `docs/samples/cn_signoff_evidence_template.json` and run:

```bash
python tools/validate_cn_signoff_evidence.py \
  --packet dist/cn_signoff_packet_m154.json \
  --evidence dist/cn_signoff_evidence_completed.json \
  --json-output dist/cn_signoff_validation_m154.json \
  --require-production-signoff-ready
```

Then regenerate delivery status with `--signoff-validation`. Only a passed
sign-off validation can make `production_signoff_ready=true`.

## Next Best Work

1. Run the UAT walkthrough with a business reviewer on representative data.
2. Capture screenshots or recording references for workbench, risk center,
   remediation tracker, AI guidance, filing/payment archive and reports.
3. Have a China tax professional sign off released rules and official sources.
4. Review current official-source freshness and local jurisdiction scope.
5. Validate completed sign-off evidence and regenerate the final delivery
   status with `--require-production-signoff-ready`.
