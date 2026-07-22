# China Compliance Delivery m138 Status

## Current Decision

The China compliance package is ready for business UAT, but it is not production
sign-off ready.

- Delivery version: `19.0.1.131.0`
- Source commit: `a513d109709eb6cca403a791df8ab9b0c07f05c9`
- Preview database: `codex_cn_m31_demo_01`
- Preview URL on the server: `http://127.0.0.1:8069/web/login?db=codex_cn_m31_demo_01`
- GitHub repository: `git@github.com:yyshi127/sdoo-odoo-cn-compliance.git`

## Automated Gates

The automated delivery gates passed on m138:

- Bundle, manifest and acceptance version are consistent.
- Bundle and manifest aggregate checksums are consistent.
- Source worktree was clean when the m138 package was built.
- Local acceptance passed.
- Remote Odoo runtime acceptance passed on a clean runtime database.
- Preview health check passed.
- Preview module version check passed.
- Representative real-data closed-loop check passed.

Evidence files:

- `dist/sdoo-cn-compliance-delivery-m138.tgz`
- `dist/sdoo-cn-compliance-delivery-m138.bundle.json`
- `dist/cn_delivery_manifest_m138_full.json`
- `dist/cn_delivery_acceptance_m138_remote.json`
- `dist/cn_preview_health_m137.json`
- `dist/cn_preview_module_m137.json`
- `dist/cn_real_data_closed_loop_m137.json`
- `dist/cn_delivery_status_m138.json`
- `dist/cn_delivery_status_m138.md`
- `dist/cn_signoff_packet_m138.json`
- `dist/cn_signoff_packet_m138.md`
- `dist/cn_signoff_validation_template_m138.json`

## Tax Domain Coverage

The representative demo database now has ready evidence for all current target
domains:

| Domain | Status | Evidence boundary |
| --- | --- | --- |
| VAT invoice / filing / payment | Ready | Representative VAT reconciliation and filing/payment archive sample. |
| CIT accounting / filing | Ready | Representative CIT reconciliation and filing record. |
| IIT payroll / withholding / payment | Ready | Aligned IIT reconciliation with payroll, withholding filing and payment sample. |
| Cross-border and withholding review | Ready | Reviewed cross-border transaction with evidence, withholding consideration and checksum. |

## Important Fixes Completed After m135

- Formal reports now show a current rule-governance gate and refuse submission
  when an official source or professional sign-off has changed since the
  assessment. The frozen report payload records this status for audit.
- CIT payment dataset selection now filters payment datasets by `tax_type_code == "CIT"` for the target period. This prevents VAT/IIT payment datasets from being treated as duplicate CIT payment datasets.
- The controlled CIT demo filing now calculates adjustment increase dynamically from the real accounting profit snapshot and keeps a stable representative taxable income/payment bridge for UAT.
- The demo preparation output now includes CIT issue details so future failures show exact issue code, severity, source area, amounts and action hints.

## Production Sign-off Is Still Blocked

`production_signoff_ready` is intentionally `false`. Do not override this with
automation or demo data.

Remaining human gates:

1. Business UAT decision must be recorded outside the automated status.
2. Current official China sources and released rules require China tax professional sign-off evidence.
3. Customer-specific accounting/data gaps, evidence gaps and open critical risks must be reviewed.
4. Representative UX walkthrough must be completed on the target screens.
5. Blocker summaries and controlled AI disclosure must be reviewed by the business reviewer.
6. Release owner must record deploy/defer/reject decision and rollback owner.

Use `dist/cn_signoff_packet_m138.md` as the action list. The template validation
file `dist/cn_signoff_validation_template_m138.json` is expected to fail because
the sample template still contains placeholders. That failure proves the
validator does not accept unsigned placeholder evidence.

## Do Not Repeat These Pitfalls

- Do not run Odoo runtime acceptance against the long-lived demo database. It can
  contain existing users, companies and record rules that are not part of the
  module test fixture. Use a clean runtime database instead.
- Do not count all `tax_payment` datasets as CIT payment evidence. Filter by tax
  type and period.
- Do not mark production as ready from demo data. Production readiness requires
  real business UAT and China tax professional sign-off.
- Do not rely on the generated status Markdown for human-readable Chinese when
  the source demo database contains older mojibake records. Use the JSON evidence
  and this curated status note for decisions.

## Reproduction Commands

Local checks:

```powershell
python tools\run_cn_delivery_acceptance.py --profile full --write-manifest dist\cn_delivery_manifest_m138_full.json --write-summary dist\cn_delivery_acceptance_m138_local.json
python tools\build_cn_delivery_bundle.py --output dist\sdoo-cn-compliance-delivery-m138.tgz --metadata dist\sdoo-cn-compliance-delivery-m138.bundle.json
python tools\verify_cn_delivery_artifacts.py --bundle dist\sdoo-cn-compliance-delivery-m138.tgz --bundle-metadata dist\sdoo-cn-compliance-delivery-m138.bundle.json --manifest dist\cn_delivery_manifest_m138_full.json --summary dist\cn_delivery_acceptance_m138_local.json
```

Remote clean runtime acceptance:

```bash
cd /tmp/codex_cn_m31
sudo -u postgres dropdb --if-exists codex_cn_m31_runtime_m138
sudo -u odoo /opt/odoo/odoo19/odoo19-venv/bin/python tools/run_cn_delivery_acceptance.py \
  --profile full \
  --python-bin /opt/odoo/odoo19/odoo19-venv/bin/python \
  --odoo-bin /opt/odoo/odoo19/odoo-server/odoo-bin \
  --config /tmp/codex_cn_m31/odoo-dev.conf \
  --database codex_cn_m31_runtime_m138 \
  --install \
  --http-port 18139 \
  --logfile dist/cn_delivery_runtime_m138_clean.log \
  --write-summary dist/cn_delivery_acceptance_m138_remote.json
```

Remote demo closed-loop preparation:

```bash
cd /tmp/codex_cn_m31
sudo -u odoo /opt/odoo/odoo19/odoo19-venv/bin/python tools/prepare_cn_demo_closed_loop.py \
  --python-bin /opt/odoo/odoo19/odoo19-venv/bin/python \
  --odoo-bin /opt/odoo/odoo19/odoo-server/odoo-bin \
  --config /tmp/codex_cn_m31/odoo-dev.conf \
  --database codex_cn_m31_demo_01 \
  --company "SG Company" \
  --allow-demo-data \
  --json-output dist/cn_demo_closed_loop_m137.json
```
