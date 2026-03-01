# FailFixer -- Architecture & Developer Reference

This document is for developers (human or AI) working on FailFixer. It explains
how the code is organized, how the key systems work, and where to look when
adding features or fixing bugs.

## Overview

FailFixer generates safe resume G-code for failed 3D prints. The user provides
the original `.gcode` file and the layer/Z-height where the print failed. The
app produces a new G-code file that safely picks up where the print stopped.

Two resume modes exist:
- **in_air** -- resume on top of the existing partial print (nozzle must not home Z)
- **from_plate** -- print the remaining section as a standalone part on the build plate

---

## Pipeline (data flow)

```
User Input (file + layer/Z + options)
        |
        v
  GCodeParser.parse()          -> ParsedGCode (layers, temps, preamble, state)
        |
        v
  LayerMapper.by_layer_number() -> LayerMatch (resolved layer + Z height)
  or .by_z_height()
        |
        v
  _detect_profile_name()       -> profile name string (auto-detection)
  ProfileLoader.load()         -> PrinterProfile (firmware settings)
        |
        v
  ResumeGenerator.generate()   -> list[str] (resume G-code lines)
        |
        v
  Validator.validate()         -> ValidationResult (errors/warnings)
        |
        v
  Save to disk                 -> <original>_resume_layer<NNNN>.gcode
```

This pipeline is orchestrated by `app/controller.py`. There are two controller
classes:
- `Controller` -- low-level, used by CLI (`app/main.py`)
- `FailFixerController` -- high-level wrapper used by the PyQt6 UI

---

## Key Modules

### `core/gcode_parser.py`
Parses raw G-code into a `ParsedGCode` structure containing:
- `lines` -- all lines of the file
- `layers` -- list of detected layers (each with layer number, Z height, start/end line)
- `state` -- detected bed temp, nozzle temp, units, positioning mode, extrusion mode
- `preamble_lines` -- everything before the first layer (startup code)

Layer detection uses a 3-tier priority:
1. `;LAYER:<n>` comment markers (Cura, PrusaSlicer, etc.)
2. `;LAYER_CHANGE` or similar patterns
3. Fallback: Z increases in `G0/G1 Z...` moves

### `core/layer_mapper.py`
Maps between layer numbers and Z heights. Provides `by_layer_number(n)` and
`by_z_height(z)` methods that return a `LayerMatch` with the resolved layer,
its Z height, and a tolerance indicator.

### `core/resume_generator.py`
The heart of the app. Builds the resume G-code output.

**In-air mode** (`_build_in_air_header`):
1. Emits metadata comments (original file, resume layer, version)
2. Replays the original preamble through `_filter_preamble_for_in_air()` which
   neutralizes dangerous commands (see below)
3. Appends the FailFixer safety sequence: `G92 Z<height>` (set Z position),
   lift to clearance, restore bed mesh, prime nozzle
4. Appends remaining G-code from the resume layer onward

**From-plate mode** (`_build_from_plate_header`):
1. Emits a standard start header with full homing (`G28`)
2. Rebases Z values so the resume layer prints at Z=0 on the plate

**Preamble filtering** (`_filter_preamble_for_in_air`):
This is where firmware-specific safety logic lives. It walks the original
startup G-code line by line and:
- **Keeps**: comments, metadata, thumbnails, `M104/M109/M140/M190` (temps),
  `M82/M83` (extrusion mode), `G21/G90/G91` (units/positioning), fan/accel
  M-codes, `EXCLUDE_OBJECT_DEFINE`, etc.
- **Neutralizes** (comments out + replaces):
  - `G28` (full or Z-only) -> `G28 X Y` (XY-only homing)
  - `G29` (bed probing) -> removed (probing risks Z collision)
  - `G9111` (Anycubic proprietary) -> explicit safe commands (see below)
  - Purge lines/sections -> removed
- **Skips**: `G0/G1` movement commands (would collide), `SET_VELOCITY_LIMIT`,
  `EXCLUDE_OBJECT`, and other non-essential commands

### `core/validator.py`
Post-generation safety checks:
- No Z movements below clearance height before the resume layer starts
- Temperature commands are present
- No bare `G28 Z` commands survived
- Movement order is safe (Z lift before XY travel)

### `core/profiles.py`
Loads printer profiles from `profiles/*.json`. Each profile specifies:
- `firmware` -- firmware type string
- `safe_lift_mm` -- default lift height
- `park_x` / `park_y` -- parking position
- `tolerance_mm` -- Z height matching tolerance
- `bed_mesh_cmd` -- command to restore saved bed mesh

### `app/controller.py`
Contains `_detect_profile_name()` which auto-detects the printer firmware by
scanning the first ~1200 lines of G-code:
- `G9111` -> `"anycubic"` (highest priority, proprietary marker)
- `PRINT_START` / `START_PRINT` -> `"klipper"`
- `M572` / `M671` / `M669` -> `"reprapfirmware"`
- Fallback -> `"default_marlin"`

---

## Firmware Handling: Anycubic G9111

Anycubic printers (Kobra S1, etc.) use modified Marlin firmware with a
proprietary `G9111` command that is an all-in-one init: it homes **all axes**
(including Z), auto-levels, and heats. Example:

```gcode
G9111 S1 bedTemp=60 extruderTemp=215
```

In in-air mode, Z homing is deadly (nozzle crashes into the existing print).
The `_neutralize_g9111()` function in `resume_generator.py` decomposes G9111
into safe explicit commands:

```gcode
; [FailFixer] Neutralized: G9111 S1 bedTemp=60 extruderTemp=215
; [FailFixer] Replaced G9111 with explicit commands:
M140 S60              ; start heating bed (from G9111)
M104 S215             ; start heating nozzle (from G9111)
G28 X Y               ; home XY only (safe for in-air)
M190 S60              ; wait for bed temp
M109 S215             ; wait for nozzle temp
```

Temperatures are extracted via regex from the `bedTemp=` and `extruderTemp=`
parameters on the G9111 line.

**Important:** In the UI firmware dropdown, Anycubic is NOT listed separately
-- users select "Klipper" (since Anycubic runs Klipper-based firmware). The
auto-detection handles it internally when `G9111` is found.

---

## Adding Support for a New Printer / Firmware

To add a new printer or proprietary command:

1. **Profile**: Create `profiles/<name>.json` with the firmware's settings
2. **Auto-detection**: Add a detection rule in `controller.py` ->
   `_detect_profile_name()`. Put specific/rare signatures first, generic ones
   last
3. **Preamble neutralization**: If the firmware has proprietary init commands
   that home Z or do unsafe things, add handling in
   `resume_generator.py` -> `_filter_preamble_for_in_air()`. Follow the
   G9111 pattern:
   - Detect the command
   - Comment out the original line
   - Inject safe replacement commands (heat + XY-only home + wait)
4. **Tests**: Add test cases in `tests/test_core.py`:
   - Detection test (does auto-detect pick the right profile?)
   - Neutralization test (is the command replaced correctly?)
   - End-to-end test (does the full pipeline produce safe output?)
   - Safety simulator test (does the dry-run show no XY below clearance Z?)
5. **Profile JSON bundling**: If adding a new profile, make sure `build.bat`
   already includes `--add-data "profiles;profiles"` (it does)

---

## Licensing

Two systems coexist:

- **Lemon Squeezy** (`core/lemon_licensing.py`): Online validation via the
  Lemon Squeezy API. 7-day offline grace period from last successful check.
  UUID-format keys.
- **FFX1** (`core/licensing.py`): Offline HMAC-SHA256 signed keys. Format:
  `FFX1-<base64 payload>`. Machine-locked. Seller generates with
  `tools/generate_license.py`.

The UI auto-detects key format and routes to the correct system.

---

## Build System

- **`build.bat`**: PyInstaller build script. Calls `get_version.py` to extract
  the version from `__init__.py` and names the output
  `FailFixer_<version>.exe`.
- **`get_version.py`**: Helper that prints the `__version__` string. Exists
  because batch file quoting makes inline Python one-liners fragile.
- **Version**: Defined in `__init__.py` as `__version__ = "v0.2.0-beta"`.
  Update this when releasing. The version appears in the exe filename and in
  generated G-code comments.
- **Windows Long Paths**: Must be enabled (`LongPathsEnabled = 1` in registry)
  for PyQt6 to install correctly. Qt has deeply nested file paths that exceed
  the 260-char Windows limit.

---

## Testing

```bash
python -m pytest tests/test_core.py -v
```

80 tests as of v0.2.0-beta. Key test classes:

| Class | What it tests |
|-------|--------------|
| `TestGCodeParser` | Layer detection, temp extraction, preamble capture |
| `TestLayerMapper` | Layer number and Z height resolution |
| `TestResumeGenerator` | In-air and from-plate header generation |
| `TestValidator` | Safety validation (Z collisions, missing temps) |
| `TestController` | Full pipeline end-to-end |
| `TestProfileLoader` | Profile JSON loading and defaults |
| `TestG9111Neutralization` | G9111 decomposition into safe commands |
| `TestAnycubicDetection` | Auto-detection of Anycubic from G9111 |
| `TestAnycubicEndToEnd` | Full pipeline with Anycubic G-code (both modes) |
| `TestDryRunSafetySimulator` | Verifies no XY movement below clearance Z |

---

## Known Issues / Future Work

- **Other proprietary inits**: Bambu Lab and others may have similar
  all-in-one commands. Add handling as user reports come in.
- **Conservative mode**: Optional extra-safe mode with mandatory clearance
  lift and park-to-safe-XY before resume. Not yet implemented.
- **Real-printer validation**: The Anycubic G9111 fix has been tested in
  simulation (80 passing tests + dry-run safety) but needs real-printer
  confirmation on an Anycubic S1.
- **PBD_V1.md scope**: The original product build document listed Klipper
  as a non-goal. This has been superseded -- Klipper, RepRapFirmware, and
  Anycubic are all supported now.

---

## File Quick Reference

| File | Purpose |
|------|---------|
| `__init__.py` | Package root, `__version__` |
| `run_gui.py` | GUI launcher (entry point for PyInstaller) |
| `app/controller.py` | Pipeline orchestrator + firmware auto-detection |
| `app/main.py` | CLI entry point |
| `core/gcode_parser.py` | G-code parsing + layer detection |
| `core/layer_mapper.py` | Layer <-> Z mapping |
| `core/resume_generator.py` | Resume G-code generation + preamble filtering |
| `core/validator.py` | Output safety validation |
| `core/profiles.py` | Printer profile loader |
| `core/licensing.py` | FFX1 offline licensing |
| `core/lemon_licensing.py` | Lemon Squeezy online licensing |
| `ui/main_window.py` | PyQt6 GUI |
| `ui/wizard.py` | Step-by-step wizard UI |
| `tools/generate_license.py` | Seller-side key generator |
| `profiles/*.json` | Printer profile configs |
| `build.bat` | PyInstaller build script |
| `get_version.py` | Version extraction for build.bat |
| `CHANGELOG.md` | Release history |
| `TODO_RESUME_IN_AIR.md` | In-air collision fix tracker |
| `PBD_V1.md` | Original product build document |
