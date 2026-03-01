# GitHub Findings: Startup/End/Resume G-code Intel

## High-signal repo findings

## Marlin (`MarlinFirmware/Marlin`)
- `Marlin/src/gcode/feature/pause/M600.cpp` contains `GcodeSuite::M600()`.
- `Configuration.h` includes `FILAMENT_RUNOUT_SCRIPT "M600"` patterns.
- Why it matters: `M600` is first-class filament-change behavior in Marlin and may appear from runout scripts or slicer-inserted color changes.

## Klipper (`Klipper3d/klipper`)
- `config/kit-voron2-250mm.cfg` includes `[gcode_macro PRINT_START]`.
- `config/printer-biqu-bx-2021.cfg` documents slicer usage like:
  - `PRINT_START BED=... NOZZLE=...`
- `config/sample-macros.cfg` includes `[pause_resume]` and `[gcode_macro M600]` patterns.
- Why it matters: Klipper behavior is macro-driven; startup safety depends on macro body, not only command names.

## PrusaSlicer (`prusa3d/PrusaSlicer`)
- Engine supports `start_gcode`, `end_gcode`, and `toolchange_gcode` options.
- Real examples in `resources/profiles/*.ini` (e.g., `Zonestar.ini`, `BIBO.ini`) show common startup blocks with:
  - temperature commands
  - `G28` homing
  - prime lines
  - `T[initial_tool]`
- Why it matters: profile files are rich fixtures for realistic slicer output patterns and multi-tool behavior.

## Search commands (repeatable)

```bash
gh search code "M600 repo:MarlinFirmware/Marlin" --limit 20
gh search code "PRINT_START repo:Klipper3d/klipper" --limit 20
gh search code "[gcode_macro M600] repo:Klipper3d/klipper" --limit 20
gh search code "start_gcode repo:prusa3d/PrusaSlicer" --limit 20
gh search code "end_gcode repo:prusa3d/PrusaSlicer" --limit 20
gh search code "toolchange_gcode repo:prusa3d/PrusaSlicer" --limit 20
```

Note: GitHub code search is rate-limited; batch queries and cache extracted snippets into `startup_samples/`.

## Practical actions for FailFixer

1. Add/expand parser markers:
   - Marlin: `M600`, runout-script-adjacent patterns.
   - Klipper: `PRINT_START`, `START_PRINT`, pause/resume macro signatures.
   - PrusaSlicer: preserve profile-style startup/comment structures.
2. Add validator tests around:
   - homing/probing in in-air mode
   - toolchange/multi-material startup lines
   - pause/resume injected commands
3. Build snippet corpus from these repos under:
   - `startup_samples/marlin/`
   - `startup_samples/klipper/`
   - `startup_samples/prusa/` (or map into existing folders)
