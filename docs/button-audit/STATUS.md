# Button audit status

Implemented: equipment wizard per-step validation, final validation, duplicate in-flight submission guard, disabled controls and aria-busy during requests, optional submitter handling, visible errors, required printer numeric fields, consistent equipment action styling, destructive printer removal styling, shared disabled and focus styling, coarse-pointer touch targets.

Playwright MCP against isolated development fixtures verified:
- Next rejects missing manufacturer/model with a specific error.
- Previous preserves entered printer information.
- PLA selection and adding blue persist through Next/Previous.
- 390 × 844 viewport has no horizontal overflow in the material step.
- Final application submission returns HTTP 200.

Incomplete: full public/buyer/host/admin control inventory and visual review; Save Draft, deletion, keyboard traversal, duplicate submission race, error recovery, cart and checkout regression coverage. The existing availability_browser.js run stopped at “PLA should have three colors”; its remaining assertions were not executed. A subsequent browser diagnostic encountered an automatic approval timeout. No conclusion about the cause of the color assertion failure has been established.

CAD: six exports generated and independently validated; see official_products/README.md and validation.json. STL assets attached to existing collection-key records (IDs 2, 3, 4) in the confirmed development Docker database. No production deployment. Existing GLB previews still depict conceptual open-deck models.
