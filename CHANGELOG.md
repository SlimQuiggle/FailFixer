# Changelog

## Unreleased

### Added
- Added user-selectable **Resume Mode** in desktop UI and wizard:
  - `in_air` (default, legacy behavior): resume at fail height on the existing print.
  - `from_plate`: print the selected remaining section from Z0 on the build plate for glue-up workflows.
- Added CLI flag `--resume-mode` with values `in_air` and `from_plate`.

### Changed
- Resume generator now emits mode-specific startup sequences.
- In `from_plate` mode, Z values in the resumed section are rebased so the selected start layer prints from the build plate.
- Validation is now mode-aware (in-air collision checks remain strict; plate mode allows Z homing).
