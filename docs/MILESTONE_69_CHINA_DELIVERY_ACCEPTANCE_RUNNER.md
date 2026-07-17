# Milestone 69: China Delivery Acceptance Runner

## Purpose

This milestone adds a repeatable delivery gate for the China country pack.  The
runner does not replace full business user acceptance, but it gives each handoff
or deployment candidate a single command that proves the packaged code still
passes the core local contracts and can optionally execute the most important
Odoo runtime checks.

## Scope

`tools/run_cn_delivery_acceptance.py` always runs:

- `tools/validate_addon.py`
- Python compilation for the workbench, risk center, report readiness, formal
  report and related tests
- XML parsing for the country pack data and the key user-facing views
- `git diff --check` for addon and tools paths

When `--odoo-bin`, `--config` and `--database` are supplied together, the runner
also executes the default Odoo runtime delivery tag set:

- `TestChinaComplianceWorkbench`
- `TestChinaRiskCenterDisplay`
- `TestChinaReportReadiness`
- `TestChinaFormalComplianceReport`

The default tag set focuses on the visible closed loop: compliance workbench,
risk visibility, remediation/report readiness gates and formal report issuance
controls.  VAT, CIT, IIT and XBRL deep-domain suites remain available as
separate targeted tests because they are larger and are often run in isolated
milestone or release jobs.

## Usage

Local gate:

```powershell
python tools\run_cn_delivery_acceptance.py
```

Runtime gate:

```powershell
python tools\run_cn_delivery_acceptance.py `
  --profile core `
  --odoo-bin C:\path\to\odoo-bin `
  --config C:\path\to\odoo.conf `
  --database codex_cn_acceptance_01 `
  --http-port 18075 `
  --logfile C:\tmp\cn_acceptance.log
```

Use `--install` for a clean install database; otherwise the runner updates
`sudo_country_pack_cn`.

Runtime profiles:

- `core`: fast visible closed-loop acceptance for workbench, risk center,
  report readiness and formal report controls.
- `tax`: VAT invoice normalization/reconciliation, VAT period reconciliation,
  CIT reconciliation, IIT reconciliation and filing center checks.
- `governance`: country-pack metadata, jurisdiction governance, taxpayer
  classification, source/rule governance, AI guidance and data readiness.
- `full`: combines `core`, `tax` and `governance`, and also runs local tax-data
  and e-invoice XBRL contract tests before the Odoo runtime tests.

Delivery manifest:

```powershell
python tools\run_cn_delivery_acceptance.py `
  --write-manifest dist\cn_delivery_manifest.json
```

The manifest records the addon version, Git commit when available, every
delivered addon/tool file, each file SHA-256 and a deterministic aggregate
SHA-256 over the sorted file paths and contents.  It is meant to prove what
code was handed off or deployed.  It does not replace accounting data,
business-rule or user-acceptance evidence.

Acceptance summary:

```powershell
python tools\run_cn_delivery_acceptance.py `
  --profile full `
  --write-manifest dist\cn_delivery_manifest.json `
  --write-summary dist\cn_delivery_acceptance_summary.json
```

The summary records the selected profile, selected runtime test tags, local
checks, manifest aggregate SHA-256, runtime database and parsed Odoo test-log
statistics when a logfile is supplied.  It is the handoff evidence that a
specific manifest passed a specific acceptance profile.

Delivery bundle:

```powershell
python tools\build_cn_delivery_bundle.py `
  --output dist\sdoo-cn-compliance-delivery.tgz `
  --metadata dist\sdoo-cn-compliance-delivery.bundle.json
```

The bundle builder uses the same audited file inventory as the delivery
manifest, including the China addon, optional e-invoice XBRL parser addon,
contract samples and delivery tools.  It writes a deterministic tar.gz archive
with normalized ownership, permissions and mtimes, plus metadata containing the
bundle SHA-256 and the same aggregate source SHA-256 used by the manifest.

Artifact verification:

```powershell
python tools\verify_cn_delivery_artifacts.py `
  --bundle dist\sdoo-cn-compliance-delivery.tgz `
  --bundle-metadata dist\sdoo-cn-compliance-delivery.bundle.json `
  --manifest dist\cn_delivery_manifest.json `
  --summary dist\cn_delivery_acceptance_summary.json
```

The verifier checks schema versions, addon versions, file counts, aggregate
SHA-256 values, per-file size/SHA-256 entries, the bundle file SHA-256 when the
bundle is available and the parsed runtime `0 failed / 0 errors` result when
the acceptance summary contains a runtime log.

Delivery runbook:

- `docs/DELIVERY_RUNBOOK_CN.md` is included in the audited delivery manifest and
  bundle.
- The runbook documents the standard bundle build, Odoo deployment, install,
  upgrade, acceptance and artifact verification commands without embedding
  production secrets, private keys, customer data or server-specific passwords.

## Acceptance Result

For `19.0.1.102.0`, the audited bundle also includes a clean Chinese delivery
runbook so deployment, acceptance and artifact verification can be repeated
without relying on chat history or operator memory.  Every selected profile
still expects `0 failed / 0 errors` before handoff.
