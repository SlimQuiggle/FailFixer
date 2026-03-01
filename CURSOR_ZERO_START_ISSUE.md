# Cursor Handoff: "Please start/reset from zero" Issue

## Context
Slim reported that after recent Cursor edits, the app regressed and began surfacing a **"please start/reset from zero"** behavior/error path that had previously been fixed using real G-code samples.

This appears to have come in with uncommitted local edits that also caused startup instability.

## What happened
- Cursor made local changes across core files.
- App behavior regressed (startup and processing reliability issues).
- We rolled back to known-good committed state and rebuilt.
- Versioned build output was restored (`FailFixer_v0.2.0-beta.exe` + `FailFixer.exe`).

## Current known-good baseline
- Repo HEAD includes recent UI/theme fixes, version labeling, and stable startup.
- Build script now outputs:
  - `dist/FailFixer_v0.2.0-beta.exe`
  - `dist/FailFixer.exe`

## Issue to investigate (for Cursor)
When processing certain files, the app can incorrectly require/force a **zeroed start** workflow ("please start/reset from zero") instead of proceeding with the intended resume mode.

### Suspected areas
1. **Resume mode routing** (`in_air` vs `from_plate`) in UI → controller handoff.
2. **Layer/Z selector validation** causing false rejection and fallback UX.
3. **Validator hard-fail conditions** if temperature/move detection is misread on vendor-specific startup blocks.
4. **Profile auto-detect interactions** (Anycubic/Klipper startup macros).

## Files most likely relevant
- `ui/main_window.py`
- `app/controller.py`
- `core/validator.py`
- `core/gcode_parser.py`
- `core/resume_generator.py`
- `tests/test_core.py`

## Guardrails for Cursor changes
- Do **not** break startup.
- Do **not** remove icon/build configuration.
- Keep versioned output behavior in `build.bat`.
- Preserve Anycubic/Klipper temperature detection support.
- Prioritize **from-plate stability**; in-air collision work remains backburner.

## Required test pass before handoff back
1. `python -m py_compile ui/main_window.py app/controller.py core/validator.py core/resume_generator.py`
2. `python -m pytest tests/test_core.py -q`
3. Build via `build.bat` and confirm EXE launches.
4. Validate with at least one real-world sample that previously triggered the zero-start issue.

## Notes
If Cursor proposes broad refactors, keep them small and incremental. Regressions have already happened from sweeping edits.
