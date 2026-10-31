# Unified profile pictures

`users.profile_picture` is the sole active selection, stored as JSON:

- `{"kind":"initials"}` for new accounts.
- `{"kind":"photo","file":"<generated filename>.webp"}` for an uploaded image.
- `{"kind":"avatar","style":{"type":"dna","variant":"helix","foreground":"#1d3557","background":"#f1faee"}}` for an SVG avatar.

The API exposes only this selection. `avatarHtml` renders it in the topbar, account settings and admin user/host rows, with initials as the fallback for unavailable photos. Buyer and host workspaces use the same topbar. Saving refreshes every mounted picture belonging to the account.

## Editing and validation

The account picture opens one dialog. Its draft stays local until Save; Cancel, Escape and the close button discard it. Uploads are decoded for the preview, checked for supported formats, 2 MB size and 16 megapixels, then validated and re-encoded by the backend. One upload request activates the photo. One avatar request replaces the selection with a validated SVG configuration. A staged photo is not uploaded when the user switches to Create Avatar before saving.

The catalogue contains six motifs. Only Molecule offers variations (Triad, Ring, Chain). Both colour palettes contain five coordinated values. All palette combinations are allowed, including low contrast pairs. Foreground and background selections remain independent. The backend validates palette membership. SVGs are rendered directly, without generated image files or external services.

Photos use a centered circular preview. Profile-photo access is limited to the owner and administrators, so admin interfaces show the actual active picture without making uploads public.

## Migration

Deploy with the normal `alembic upgrade head` from `backend/`. Migration `72a_unified_profile_picture` follows `71a_lab_avatars` and copies the identifiable legacy selection. An explicitly selected valid avatar wins; otherwise an existing photo wins when both are present. Accounts with neither get initials. Malformed designs fall back to a valid photo or initials.

Legacy columns and files remain untouched during migration as recovery archives. The application never reads those columns as an active selection, and clears their assignments on the next picture save. Retired artwork remains in the SVG renderer solely to preserve saved pictures; it cannot be newly selected or saved. Opening/canceling the editor also preserves retired designs.

## Verification

From `backend/`, run `python -m pytest tests/test_avatars.py tests/test_accounts.py -q` with the existing test dependencies. Tests cover catalogue/palette parity, all designs, invalid writes, upload rollback, persistence, admin authorization and legacy migration.

For browser verification, start a **fresh isolated** `scripts/catalogue_preview.py` fixture, then run:

```sh
uv run --offline --no-project --python 3.12 --with playwright --with Pillow python tests/avatar_editor_browser.py /tmp/profile-picture-qa http://127.0.0.1:18101
```

The script saves desktop/mobile Bright and Dark screenshots, checks keyboard containment, previews, cancellation, photo/avatar replacement, failed-upload retry, fresh login persistence and shared rendering in account/workspace/admin views. `CHROME` can specify the Chromium executable.
