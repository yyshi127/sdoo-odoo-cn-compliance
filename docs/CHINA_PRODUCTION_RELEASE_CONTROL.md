# China Production Release Control

This document is the release-control checklist for deploying the China fiscal
compliance pack into a customer Odoo environment. It is not a tax opinion and it
does not replace the production sign-off template.

## Required Controls Before Deployment

- Confirm the target Odoo major version is 19 and the selected package version
  matches the delivery status, bundle metadata and manifest.
- Record the target database, target company scope, release owner, rollback
  owner and go-live monitoring owner.
- Capture a database backup and filestore backup outside this repository and
  record the backup references in the production sign-off evidence.
- Restore the backups into an isolated staging database before production
  deployment.
- Run the delivery acceptance command in install mode on a clean runtime
  database.
- Run the delivery acceptance command in update mode with
  `-u sudo_country_pack_cn` on the same runtime database.
- Confirm the delivery status shows `runtime_passed=true` and
  `upgrade_runtime_passed=true`.
- Confirm the preview database can open and reports the expected installed
  `sudo_country_pack_cn` version.
- Confirm business UAT, official-source freshness review, China tax
  professional rule sign-off and customer data-scope review are complete.

## Rollback Triggers

Use `defer`, `reject` or roll back instead of proceeding when any of these are
true:

- The database or filestore backup cannot be restored into staging.
- Odoo install or update acceptance has failed tests or errors.
- The target database cannot open after deployment.
- The installed module version differs from the delivery package version.
- Company access, record rules or menu access differs from the approved scope.
- Risk, remediation, evidence, filing or report pages cannot be reviewed by the
  intended users.
- Human sign-off evidence is missing, stale, cross-environment or not bound to
  the selected source commit and preview URL.

## Rollback Procedure

1. Stop user access to the affected Odoo database.
2. Record the incident time, release package, source commit, database and
   affected companies.
3. Restore the last approved database and filestore backup.
4. Start Odoo against the restored database and verify login, accounting menus
   and the China compliance menu.
5. Re-run preview health and module version checks.
6. Record the rollback owner, result, residual data risks and next decision in
   the production sign-off evidence.

## Post-Deployment Monitoring

- Verify login, application menu loading and China compliance menu access.
- Verify one compliance profile, one risk finding, one remediation task, one
  evidence record, one filing/payment archive and one compliance report can be
  opened under the approved company context.
- Review Odoo logs for errors during the monitoring window.
- Keep the delivery bundle, manifest, acceptance summaries, upgrade summary,
  preview checks, closed-loop evidence, sign-off packet and completed sign-off
  evidence together as the release audit packet.
