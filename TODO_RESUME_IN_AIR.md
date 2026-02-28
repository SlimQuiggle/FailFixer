# TODO - Resume In-Air Collision Regression (Kobra S1)

## Status
Backburner for now (per Slim). Prioritize **from-plate** stability first.

## What happened
- In-air run appeared to pass startup/leveling safely.
- At print start, nozzle collided with existing printed parts and knocked them loose.

## Known context
- Printer: Anycubic Kobra S1
- Slicer: AnycubicSlicerNext 1.3.9.3
- Startup preamble includes Anycubic proprietary `G9111 bedTemp=... extruderTemp=...`
- Resume now preserves original preamble and neutralizes dangerous commands (G28 Z/G29/purge handling), but collision still occurred in real run.

## Investigation checklist (for Cursor)
1. Capture generated resume file used in failed run.
2. Compare generated in-air file vs original around:
   - End of startup preamble
   - First movement before resumed layer
   - Any `G92 Z`, `G1 Z`, `EXCLUDE_OBJECT_*`, and purge-related moves
3. Verify absolute/relative mode transitions just before resume:
   - `G90/G91`, `M82/M83`, `G92 E0`
4. Add "dry-run safety simulator" test to ensure first XY move cannot occur below clearance Z.
5. Add optional conservative mode for in-air:
   - mandatory extra clearance lift (e.g., resume_z + 10)
   - optional park to user-selected safe XY before resume

## Desired outcome
- In-air mode never contacts existing object before reaching intended resume path.
- Add deterministic test reproducing and preventing this regression.
