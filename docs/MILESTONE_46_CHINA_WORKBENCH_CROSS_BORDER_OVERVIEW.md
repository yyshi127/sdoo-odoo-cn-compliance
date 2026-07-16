# Milestone 46 - China Workbench Cross-Border Overview

## Purpose

The China country pack declares a `cross_border` compliance domain, but the workbench previously emphasized VAT, CIT, and IIT only. This milestone surfaces cross-border and withholding exposure on the first workbench screen while keeping the boundary clear: the package does not yet make a full cross-border tax conclusion from transactions.

## Delivered

- Adds cross-border display fields on `sudo.compliance.profile`:
  - `cn_workbench_cross_border_state`
  - `cn_workbench_cross_border_basis`
  - `cn_workbench_cross_border_next_action`
- Derives the workbench cross-border state from the current controlled taxpayer classification snapshot:
  - nonresident CIT status
  - CIT withholding collection method
  - PIT withholding status
  - classification verification and integrity state
- Adds a workbench action to open related China taxpayer classification snapshots.
- Adds a cross-border / withholding card next to VAT, CIT, and IIT domain cards.
- Advertises the capability as `china_workbench_cross_border_overview`.

## Boundary

This milestone does not introduce transfer pricing, customs, treaty-benefit, non-trade payment, service import, royalty, interest, dividend, permanent establishment, or outbound payment rules. It only exposes whether the controlled taxpayer identity snapshot contains nonresident or withholding indicators, and tells the user to collect and review contracts, payments, filings, and supporting evidence when those indicators exist.

## Validation

- XML parse check for `views/workbench_views.xml`.
- Python compile check for the China addon and validator.
- `tools/validate_addon.py` verifies:
  - feature metadata
  - model fields and action
  - workbench card fields and button
  - runtime test coverage markers

## Acceptance Criteria

- The workbench shows a visible cross-border / withholding card.
- The card displays state, basis, and next action.
- The card navigates to China taxpayer classification snapshots.
- The workbench warns when the current identity snapshot indicates nonresident, source withholding, or PIT withholding exposure.
