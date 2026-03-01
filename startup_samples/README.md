# Startup Samples Corpus

Drop startup snippets here to improve FailFixer compatibility across printer ecosystems.

## Folder layout
- `anycubic/`
- `klipper/`
- `marlin/`
- `reprapfirmware/`
- `bambu_orca/`

## File naming
Use:
`<printer>__<firmware>__<slicer>__<date>.gcode`

Example:
`kobra_s1__anycubic_mod__orcaslicer_2.2__2026-02-28.gcode`

## Include with each sample
- First 150–300 lines from original source G-code
- Notes block at top with:
  - printer model
  - firmware/version (if known)
  - slicer + version
  - intended mode tested (`in_air` or `from_plate`)
  - observed result

## Purpose
These samples back parser/validator tests and startup normalization rules.
