# FailFixer – Product Build Document (PBD) – V1
## Failed Print Resume Generator

---

## 1. Product Overview

FailFixer V1 is a standalone desktop application that generates a safe resume G-code file from an original failed FDM print.

This version focuses strictly on:
- Deterministic G-code parsing
- Resume generation from a required Z/layer input
- Offline execution
- Safe header injection
- File output only (no live printer control)

---

## 2. V1 Core Requirements

### Required Input
- Original `.gcode` file
- Resume selector (REQUIRED):
  - Layer number (int) OR
  - Measured Z height in mm (float)

### Optional Input
- Z offset adjustment (float, default 0.00mm)
- Optional park X/Y (advanced field)
- Optional printer profile selection

### Output
- New `.gcode` file
- Naming convention:
  `original_filename_resume_layerXXXX.gcode`

---

## 3. Technical Stack

- Python 3.11+
- PyQt6 for UI
- Packaged via PyInstaller
- Windows-first distribution
- Fully offline operation

---

## 4. Architecture

```
failfixer/
  app/
    main.py
    controller.py
  core/
    gcode_parser.py
    layer_mapper.py
    resume_generator.py
    validator.py
    profiles.py
  ui/
    main_window.py
    wizard.py
  profiles/
    default_marlin.json
```

---

## 5. G-code Parsing Requirements

Layer detection priority:
1. `;LAYER:<n>` comment markers
2. `;LAYER_CHANGE` or similar patterns
3. Fallback: detect Z increases via `G0/G1 Z...` moves

Must detect and preserve:
- Units (G20/G21)
- Positioning mode (G90/G91)
- Extruder mode (M82/M83)
- Bed temp (M140/M190)
- Nozzle temp (M104/M109)

---

## 6. Resume Logic

### Remove:
- Original header section
- All layers below selected layer

### Preserve:
- Temperature commands
- Units
- Extrusion mode
- Remaining G-code from selected layer onward

### Inject Resume Header

```
; --- FailFixer Resume Header ---
; Resume Layer: <n>
; Resume Z: <z>
; Offset: <offset>

M140 S<bed_temp>
M104 S<nozzle_temp>
M190 S<bed_temp>
M109 S<nozzle_temp>

G21
G90

G28 X Y
G1 Z<safe_lift>

G92 E0
G1 E5 F300
G92 E0

; --- End Resume Header ---
```

Then append the original G-code starting at the selected layer.

---

## 7. Safety Rules

- NEVER auto-home Z
- Always lift Z before any XY travel
- Default `safe_lift` = 10mm
- Measured Z tolerance warning at ±0.15mm
- User confirmation required before file generation

---

## 8. Configuration (default_marlin.json)

```json
{
  "firmware": "marlin",
  "safe_lift_mm": 10,
  "park_x": 0,
  "park_y": 200,
  "tolerance_mm": 0.15
}
```

---

## 9. Performance Requirements

- Parse up to 50MB G-code under 3 seconds
- Resume file generation under 1 second
- Deterministic output (same inputs → same file)

---

## 10. Non-Goals (V1)

- USB/serial control
- Klipper support
- OctoPrint integration
- Multi-extruder support
- Seam blending
- Cloud features
- Telemetry

---

## 11. Testing Requirements

Minimum 80% unit test coverage for:
- Layer detection
- Z-to-layer mapping
- Resume header injection
- File validation

Must validate on:
- At least 5 real failed prints
- Both absolute and relative extrusion modes (relative may be primary support)

---

## 12. Definition of Done

- Resume file successfully continues a failed print
- No Z collisions
- No missing temp commands
- No syntax errors in output G-code
- Packaged executable runs without Python installed

---

Engine correctness > UI polish.
