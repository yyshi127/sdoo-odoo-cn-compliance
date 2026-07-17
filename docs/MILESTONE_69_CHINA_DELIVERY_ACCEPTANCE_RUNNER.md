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

## Acceptance Result

For `19.0.1.99.0`, the delivery runner can emit both a deterministic delivery
manifest and a machine-readable acceptance summary.  Every selected profile
still expects `0 failed / 0 errors` before handoff.
