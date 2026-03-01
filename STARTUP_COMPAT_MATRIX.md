# FailFixer Startup Compatibility Matrix (WIP)

Goal: reduce reactive bugfixes by proactively handling firmware/vendor startup differences.

## Safety policy by mode

- **In-Place (in_air):**
  - Never allow homing/probing at print start (`G28`, `G29`, unknown full-init macros).
  - Replay only startup commands that are known-safe in-air.
  - Prefer explicit Z state set + clearance lift + controlled prime.
- **On-Plate (from_plate):**
  - Startup can be much closer to original file behavior.
  - Standard homing/heating/start lines usually safe.

---

## Command classes

### Class A — Safe in both modes
- Temperature set/wait (`M104/M109`, `M140/M190`, equivalent macro params)
- Fan commands (`M106/M107`)
- Non-motion metadata/comments/thumbnails
- Tool selection commands where motion side effects are known minimal

### Class B — Safe only On-Plate
- Homing (`G28`)
- Bed probing / leveling (`G29` and equivalents)
- Purge lines near plate
- Macros that include homing/probing internally

### Class C — Needs explicit handling
- Vendor-specific startup commands/macros with hidden side effects
- Unknown macros with motion commands embedded
- Any command that can alter coordinate state unexpectedly

---

## Firmware/vendor fingerprints (current)

### Anycubic
- Known marker: `G9111`
- Notes:
  - Appears in proprietary startup blocks.
  - Can include bed/nozzle temps as params.
  - Treat as high-risk for in-air unless normalized/neutralized.
- Detection status: implemented (parser + validator support exists).

### Klipper
- Known markers: `PRINT_START`, `START_PRINT`, `_START_PRINT`
- Notes:
  - Macro behavior depends on printer config and may include homing/probing.
  - Parse macro params for temps.
- Detection status: implemented (macro temp detection exists).

### Marlin
- Typical direct-code startup: `G28`, optional `G29`, temp M-codes.
- Notes:
  - Usually predictable; still unsafe to home/probe in in-air mode.
- Detection status: default profile path.

### RepRapFirmware
- Marker examples: `M572`, `M671`, `M669`
- Notes:
  - Startup highly configurable; treat unknown macros conservatively.
- Detection status: signature-based profile selection implemented.

### Bambu / Orca-style workflows (planned)
- Collect startup signatures from OrcaSlicer/Bambu exports.
- Map AMS/slot/tool-change behaviors and safe replay rules.

---

## Data collection plan

1. Build a startup corpus under `startup_samples/`:
   - `anycubic/`
   - `klipper/`
   - `marlin/`
   - `reprapfirmware/`
   - `bambu_orca/`
2. For each sample, capture:
   - Printer model
   - Firmware/version (if known)
   - Slicer + version
   - First 150–300 lines of original G-code
   - Failure mode observed (if any)
3. Add expected behavior tags:
   - `safe_in_air`
   - `safe_on_plate`
   - `needs_neutralization`

---

## Implementation roadmap

### Phase 1 (now)
- Establish matrix + sample corpus structure.
- Expand parser/validator command detection for temps + risky startup markers.
- Add tests for known vendor startup snippets.

### Phase 2
- Create startup normalizer layer:
  - classify each startup line
  - keep/neutralize/replace by mode
- Add warning telemetry in output log when unknown risky markers are seen.

### Phase 3
- Ship profile packs + compatibility page for users.
- Add quick “Startup fingerprint” export in bug report dialog.

---

## Immediate TODO

- [ ] Add first real Anycubic startup sample with `G9111`
- [ ] Add first Klipper macro-heavy startup sample
- [ ] Add first Bambu/Orca startup sample
- [ ] Add regression tests for in-air homing/probing neutralization
- [ ] Add tests for output naming + mode prefix behavior

Owner: Simulacra / swarm-builder
Status: Active
