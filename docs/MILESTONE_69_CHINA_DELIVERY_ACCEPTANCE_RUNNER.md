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
  --odoo-bin C:\path\to\odoo-bin `
  --config C:\path\to\odoo.conf `
  --database codex_cn_acceptance_01 `
  --http-port 18075 `
  --logfile C:\tmp\cn_acceptance.log
```

Use `--install` for a clean install database; otherwise the runner updates
`sudo_country_pack_cn`.

## Acceptance Result

For `19.0.1.96.0`, the local delivery runner passed on the development
workstation.  The addon was then deployed to the isolated server dev database
and the same runner executed the default Odoo runtime delivery tag set with
`0 failed / 0 errors`.
