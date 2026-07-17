# China Fiscal Compliance Pack Delivery Index

This is the starting point for release handoff and acceptance of the
`sudo_country_pack_cn` delivery bundle.

## Read Order

1. `docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md`
   - Confirms how the product objective maps to software evidence and known
     production boundaries.
2. `docs/DELIVERY_RUNBOOK_CN.md`
   - Explains how to install, upgrade, build and verify the delivery bundle.
3. `docs/DEVELOPMENT_PREVIEW_ACCESS_CN.md`
   - Explains how to open an isolated development preview through a local SSH
     tunnel.
4. `docs/CHINA_BUSINESS_UAT_CHECKLIST.md`
   - Guides business reviewers through the workbench, data readiness, risk,
     remediation, AI guidance, report and evidence walkthrough.
5. `docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md`
   - Records the final deploy, defer or reject decision after automated
     acceptance and business UAT.

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
  --preview-url http://127.0.0.1:18069/web/login?db=target_database \
  --json-output dist/cn_delivery_status.json \
  --markdown-output dist/cn_delivery_status.md
```

The status summary includes machine-readable readiness gates for business UAT
and production sign-off. Production sign-off remains blocked until the business
UAT decision, current-source review, professional rule sign-off and
customer-specific limitations are recorded outside the automated status.

Check a preview URL before business UAT:

```bash
python tools/check_cn_preview_health.py \
  --url http://127.0.0.1:18069/web/login?db=target_database \
  --json-output dist/cn_preview_health.json
```

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
- preview health check returns `ok=true` for the intended preview URL.

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
