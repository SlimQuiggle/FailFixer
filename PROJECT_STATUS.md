# FailFixer — Project Status & AI Handoff (Living Document)

Last updated: 2026-02-28
Branch focus: `cursor-recovery` (active)
Public release target: **V1.0.0 (On-Plate first)**

---

## 1) Current Product Strategy

### Public V1 track (stable)
- Goal: release broadly with **On-Plate** workflow as default.
- In-Air functionality remains in code but is **disabled in UI** for public safety.
- Versioning discipline: bump version for each meaningful release build.

### Beta track (advanced)
- Continue hardening **In-Air** mode (collision-risk sensitive).
- Re-enable in UI only when safety confidence is high.

---

## 2) What Is Implemented

## Core pipeline
- Parse source G-code
- Detect layers and map layer/Z selections
- Auto-detect profile for common firmware ecosystems
- Generate resume output for:
  - `in_air` (kept but disabled for public UI)
  - `from_plate` (public default)
- Validate generated output before save

## Compatibility improvements already done
- Temp parsing/validation support for:
  - `M104/M109` + `S/R`
  - `M140/M190` + `S/R`
  - Klipper temp commands/macros
  - Anycubic `G9111 bedTemp=... extruderTemp=...`
- Fallback temperatures when missing (safe defaults)
- Preserve metadata/thumbnail sections in generated output
- Preserve and filter startup preamble according to mode

## Output naming behavior
- Generated G-code filename now mode-prefixed:
  - `On-Plate_...` for plate mode
  - `In-Place_...` for in-air mode
- UI save path logic enforces the prefix even if user edits filename.

## UI/UX status
- Theme toggle with moon/sun icons restored
- Light mode improvements landed
- Footer button theming fixed
- Public V1 mode selector behavior:
  - **On-Plate selected by default**
  - **In-Air disabled/greyed out** (coming in beta)

## Build/versioning behavior
- Version sourced from `__init__.py`
- Build output is versioned (no overwrite):
  - `dist/FailFixer_<version>.exe`
- Current release build target: `v1.0.0`

---

## 3) High-Signal Commits (Recent)

- `346bbe7` — V1 public mode: On-Plate default, In-Air disabled in UI, Bambu groundwork
- `af870d4` — Output filename mode prefix enforcement + in-air safety bump
- `bdbaedd` — Regenerated `logo.ico` from FailFixer logo for embedded EXE icon correctness
- `b11b2c0` — Fixed packaged icon path resolution (prefer `.ico`)
- `6da5de1` — Added startup compatibility matrix + sample corpus scaffold
- `e1a2b41` — Prefix output filenames with In-Place/On-Plate

---

## 4) Architecture & Important Files

## Key code files
- `app/controller.py` — orchestration, profile detect, output naming
- `core/gcode_parser.py` — parsing, layer/state/preamble detection
- `core/resume_generator.py` — mode-specific generation + startup filtering
- `core/validator.py` — safety checks and validation gates
- `ui/main_window.py` — public UI behavior, defaults, save naming enforcement
- `run_gui.py` — app startup + app-level icon
- `build.bat` — versioned build output

## Profile definitions
- `profiles/default_marlin.json`
- `profiles/klipper.json`
- `profiles/reprapfirmware.json`
- `profiles/anycubic.json`
- `profiles/bambu_orca.json` (groundwork)

## Strategy/docs for AI contributors
- `STARTUP_COMPAT_MATRIX.md` — compatibility roadmap and safety classes
- `startup_samples/README.md` — corpus collection format
- `ARCHITECTURE.md` — module-level design notes
- `CURSOR_ZERO_START_ISSUE.md` — regression handoff context

---

## 5) Known Risks / Open Issues

1. **In-Air collision sensitivity**
   - Still not public-ready; remains beta-only behavior.
   - Real printer collisions can still occur if fail-layer assumptions are wrong.

2. **Cross-printer startup variance**
   - Vendor macros differ significantly (Anycubic/Bambu/Klipper hybrids).
   - Need broader startup corpus and normalization rules.

3. **Bambu ecosystem depth**
   - Marker-based detection exists, but runtime behavior coverage is still early.

---

## 6) What Still Needs Work (Priority Queue)

## Priority A (public-quality)
- [ ] Add explicit “V1 Public” branch/tag and freeze criteria.
- [ ] Add release notes/checklist for each versioned build.
- [ ] Confirm icon/resource correctness on multiple clean machines.

## Priority B (compatibility scale)
- [ ] Expand startup sample corpus (`startup_samples/*`) from real user files.
- [ ] Add unit tests for each new vendor startup signature.
- [ ] Implement startup normalizer classification pipeline:
  - keep / neutralize / replace by mode.

## Priority C (Bambu focus)
- [ ] Collect Bambu Studio + Orca samples (X1/P1/A1 families, AMS variants).
- [ ] Map AMS/tool-change startup commands and safe replay behavior.
- [ ] Add Bambu-specific validator cases and expected outcomes.

## Priority D (beta track)
- [ ] Continue in-air safety hardening under beta branch.
- [ ] Add optional advanced controls + warnings when beta in-air is enabled.

---

## 7) How To Build / Test

## Local validation
1. `python -m py_compile __init__.py app/controller.py ui/main_window.py`
2. `python -m pytest tests/test_core.py -q`

## Build
- Run: `build.bat`
- Output: `dist/FailFixer_<version>.exe`

---

## 8) Rules for Future AI Contributors

- Do not remove versioned build outputs.
- Bump version when shipping meaningful behavior changes.
- Keep public V1 safe: On-Plate default, In-Air disabled in UI unless explicitly moving beta -> public.
- Add tests for every compatibility rule added.
- Prefer small, reviewable commits over broad refactors.
- Preserve this file as the top-level project handoff ledger.
