---
name: gcode-startup-intel
description: Research and normalize 3D-printer startup/end/resume G-code across firmware ecosystems. Use when asked to investigate start.gcode/end.gcode/resume.gcode, M600 filament change behavior, PrusaSlicer start/end/toolchange scripts, Klipper PRINT_START macros, Marlin examples, or vendor-modified firmware (Anycubic/Bambu/Orca). Produces actionable compatibility findings, test cases, and parser/validator TODOs.
---

# Gcode Startup Intel

Use this skill to turn ad-hoc GitHub searching into structured compatibility intel for FailFixer.

## Workflow

1. Gather evidence from target ecosystems:
   - `MarlinFirmware/Marlin`
   - `Klipper3d/klipper`
   - `prusa3d/PrusaSlicer`
2. Focus search terms:
   - `start.gcode`, `end.gcode`, `resume.gcode`
   - `M600 filament change`
   - `PRINT_START`, `print_start`
   - `toolchange_gcode`, pause/resume macros
3. Extract concrete startup lines and macros (not just prose docs).
4. Classify findings:
   - safe in both modes
   - safe on-plate only
   - risky/unknown (needs neutralization)
5. Convert findings into code/test actions:
   - parser detection markers
   - validator rules
   - profile updates
   - unit tests with snippet fixtures
6. Update project docs:
   - `STARTUP_COMPAT_MATRIX.md`
   - `startup_samples/`
   - `NEXT_SESSION_TODO.md` (if needed)

## Output format

When reporting findings, always include:
- **Source repo + file path**
- **Exact marker/command found**
- **Why it matters for FailFixer**
- **Action** (detect, preserve, neutralize, or test)

## Guardrails

- Prefer real config/profile files over forum posts.
- Assume vendor macros may hide homing/probing unless proven otherwise.
- Keep public V1 safety posture: On-Plate default, In-Air conservative.
- Add tests for every new marker before claiming support.

## References

- Use `references/github-findings.md` for known high-signal markers and search commands.
