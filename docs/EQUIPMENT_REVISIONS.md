# Independent host accounts and equipment revisions

The old `PUT /api/host/equipment-application` deleted all live printers, wrote the edited
configuration into that same table, reassigned the host application to draft/pending,
and assigned the user the buyer role. This happened even on Save Draft. Availability
and host authorization both require an approved application and the host role, so all
previously certified capabilities and host access disappeared together.

The existing `HostApplication.status` now remains the durable account approval for
approved hosts. Its approve/reject/suspend/restore administration remains unchanged.
Equipment editing never writes a user role. First-time applications retain their
existing moderation process; their equipment cannot match marketplace jobs until the
account is approved.

`HostPrinter` remains the certified configuration used by the existing availability,
quote, checkout and assignment code. Approved hosts' edits are stored only in the new
`EquipmentRevision` table. A draft has no queue entry or moderation activity; submission
moves it to pending. Pending submissions are immutable, and a partial unique index
permits only one open draft/request per host. Rejection preserves the proposal, reason,
reviewer and account, allowing a new revised submission. Approved/rejected requests
remain review history. Discard restores a private draft from the certified configuration.

Approval atomically checks the account and baseline snapshot, validates active jobs,
and activates the proposed configuration. Identical printers keep their IDs. The
existing SQLite writer reservation serializes this with checkout, job acceptance,
account suspension and other equipment writes. Repeat decisions return a conflict.
Suspended accounts cannot activate revisions. A baseline conflict requires the admin
to reject the stale proposal before the host resubmits.

New order items snapshot machine-readable build dimensions alongside their existing
material, color and assignment history. Capability removal is blocked if any accepted,
printing or ready job cannot be manufactured by a single proposed printer. Legacy
items use their saved dimension text when it contains three positive dimensions in an unambiguous millimeter format;
unverifiable legacy requirements block removal until the job is completed or handled
through existing job administration. Pure additions remain allowed. Removing the last
printer is supported and leaves the account approved with no manufacturing availability.
This uses capability-level matching because existing jobs are assigned to hosts, not
individual printer IDs; it does not introduce scheduling or throughput estimates.

The editor displays certified equipment and proposed equipment separately, with revision
status, private save confirmation, restoration, and submission locking. Materials, color
names/hex values, quantities and build volumes appear in admin before/after review.
New or modified printer entries are marked as requiring approval. Saved drafts persist
in the database; session state preserves unsaved inputs between steps and account pages.

## Files

- `backend/app/equipment.py`: draft/revision persistence, review API and activation safeguards.
- `backend/app/models.py`: equipment revision model and order dimension snapshot.
- `backend/app/operations.py`: order snapshot creation, revision queue count and account deletion compatibility.
- `backend/migrations/versions/65a_equipment_revisions.py`: additive schema and rollback.
- `assets/equipment.js`: approved/draft editor, status, restore and save/submit behavior.
- `assets/workspaces.js`: separate equipment moderation queue and comparisons.
- `assets/navigation.js`: include equipment requests in approval counts.
- `index.html`: updated cache keys for changed scripts; existing edits preserved.
- `backend/tests/test_equipment_revisions.py`: isolated HTTP workflow and migration roundtrip tests.
- `backend/tests/test_availability_integration.py`: update legacy expectations for isolated drafts and schema version.
- `tests/equipment_revisions_browser.js`: host/admin Playwright lifecycle.
- `tests/availability_browser.js`: verify draft colors preserve certified marketplace availability.
- `scripts/equipment_preview.py`, `scripts/availability_preview.py`: isolated temporary browser fixtures, optional administrator.
- `docs/EQUIPMENT_REVISIONS.md`: design, deployment and validation notes.

## Migration and rollback

Read-only audit of the running SQLite database on 2026-10-30 found schema
`64a_material_colors`, one approved host with the host role, one pending buyer
application, two equipment records and four orders. No inconsistent approval/role
pair appeared in that audit. Implementation testing did not modify running database rows; the subsequent authorized
backend deployment applied the additive migration described below.
The migration does not infer or change anyone's approval, rewrite printers, or backfill
legacy order dimensions from mutable product records.

Before rollout, take a consistent SQLite backup using the existing backup procedure.
Rebuild/restart the backend with the updated code; its existing container startup runs
`alembic upgrade head`. For a local environment, from `backend/` run:

```sh
alembic upgrade head
```

The migration creates the revision table and adds an order-item dimension column.
All existing users, account applications, printers, products, orders and assignments
remain unchanged. No new runtime dependencies are needed.

For rollback, stop application writes and retain a database backup including revision
history. Run the following using the new migration code, then restore the previous
application version:

```sh
alembic downgrade 64a_material_colors
```

Downgrade removes revision history/drafts and the new dimension snapshots, so export
or back up them first. Existing account approvals, certified printers and orders remain.
The old application contains the equipment downgrade bug; do not resume equipment
editing on it. Upgrade/downgrade/upgrade was tested against populated isolated fixtures.
The Docker backend was subsequently rebuilt and deployed at the user's request on
2026-10-30. The initial build succeeded; only the backend was recreated, and both
backend and Caddy remained healthy after deployment. A consistent pre-migration SQLite
backup is stored at `backups/before-equipment-65a-f0q0zq8r.db`.
The deployed schema is `65a_equipment_revisions`; database integrity is `ok` with zero
foreign-key violations. Hash comparisons of all pre-existing columns confirmed unchanged
users (4), host applications (2), printers (2), listings (10), orders (4), order items (6),
and jobs (6). The proxied health endpoint returned HTTP 200, and OpenAPI includes the
new host revision and administrator review routes.

## Validation

Run backend tests with the existing development environment:

```sh
PYTHONPATH=backend /tmp/ol3d-availability-venv/bin/python -m pytest backend/tests -q
```

Browser fixtures use temporary databases and the existing development test credentials,
never real account records. Start `scripts/equipment_preview.py`, then use Playwright
`browser_run_code_unsafe` with `tests/equipment_revisions_browser.js`. For marketplace
coverage start `scripts/availability_preview.py` and run `tests/availability_browser.js`.
Ports default to 18099 and 18097 respectively; `AVAILABILITY_QA_PORT` overrides the
server port (adjust the test's base URL to match).

The full backend suite passed: 67 tests (five existing deprecation warnings).
After removing the remaining applicant-path role assignment, 26 account/operation/revision
checks passed. Final active-job safeguards, including rejection of ambiguous legacy units,
passed all 8 targeted revision checks.
JavaScript syntax checks and `git diff --check` also passed.

Both browser workflows passed against fresh isolated fixtures, covering private saves,
reload, unchanged availability, submission, pending locking, before/after moderation,
rejection, resubmission, approval, mobile overflow and host access after logout/login.
No uncaught JavaScript exceptions occurred. Backend tests cover active-job protection,
material/color/build-volume eligibility, permission boundaries, unchanged printer IDs,
last-printer removal, explicit suspension/restoration, and safe migration roundtrips.
