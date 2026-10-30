# Softened finish — revision 3

Same three product IDs, envelopes, pitches and nominal bores as revision 2.

| Feature | Revision 2 | Revision 3 |
|---|---|---|
| Vertical outer corner radius | 5 mm | 7 mm |
| Top perimeter | 0.7 mm chamfer | 1.6 mm fillet |
| Vault transitions | 0.8 mm radius | 2 mm radius |
| Tube entry | 0.6 mm chamfer | 1.1 mm chamfer |
| Bed-facing perimeter | 0.7 mm chamfer | 0.8 mm chamfer |

Current measured solid volumes: 127744.339, 138904.599 and 146984.270 mm³ for microtube, 15 mL and 50 mL respectively. All dimensions unchanged. Nominal clearance probes pass. STL and 3MF are equivalent, watertight and consistently wound single solids; all 730 geometric slices pass continuity checks at 0.2 mm spacing. Mesh chord tolerance is 0.025 mm and angular tolerance 0.1 rad; all STL files remain below 5 MB.

The enlarged vault crest radius increases the small local bridge: verify bridge quality on the target printer. Physical fit and strength trials remain necessary. The design does not require changing eligibility, pricing or any website code.

Previous Bridge assets are retained in `../previous/bridge_v2/`; development listing rollback snapshot is `cad_backups/bridge_v3_finish.json`. Original block assets remain in `../previous/block_v1/`.
