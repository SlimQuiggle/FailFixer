# FailFixer 🔧

**Resume failed 3D prints with one click.**

FailFixer generates a safe resume G-code file from your original failed print. Just tell it what layer the print failed at, and it outputs a new file you can print as if it were a fresh job — but it picks up right where the old one stopped.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

## Features

- **Simple** — Load G-code, pick the failed layer, generate. That's it.
- **Collision-safe** — Never homes Z (would crash into your print). Uses smart XY-only homing + G92 position setting.
- **Multi-firmware** — Supports Marlin, Klipper, and RepRapFirmware out of the box.
- **Drag & drop** — Drop your .gcode file right into the window.
- **Fast** — Parses 50MB G-code files in under 2 seconds.
- **Offline** — No internet, no accounts, no telemetry. Everything runs locally.
- **Standalone .exe** — Download and run. No Python installation needed.

## Quick Start

### Option A: Download the .exe (recommended)
1. Download `FailFixer.exe` from [Releases](../../releases)
2. Double-click to run
3. Load your G-code → pick the failed layer → Generate

### Option B: Run from source
```bash
# Clone
git clone https://github.com/SlimQuiggle/FailFixer.git
cd FailFixer

# Install deps
pip install PyQt6

# Run
python run_gui.py
```

### Option C: Command line
```bash
# Resume from layer 50
python -m failfixer.app.main myprint.gcode --layer 50

# Resume from measured Z height
python -m failfixer.app.main myprint.gcode --z 12.5

# With Z offset adjustment
python -m failfixer.app.main myprint.gcode --layer 50 --offset 0.1
```

## How It Works

1. **Parses** your original G-code file, detecting layers, temperatures, and printer settings
2. **Strips** everything below your selected resume layer
3. **Generates** a collision-safe startup sequence:
   - Heats bed and nozzle
   - Homes X/Y only (never Z — that would crash into your print)
   - Sets Z position via G92 (no physical movement)
   - Lifts to clearance height
   - Primes nozzle at a safe corner
4. **Appends** the remaining G-code from your resume layer onward
5. **Validates** the output for safety (no Z collisions, temps present, correct movement order)

## Safety

FailFixer is designed to be safe:

- ⛔ **Never homes Z** — G28 Z drives the nozzle down, which would crash into your partial print
- ✅ **Homes X/Y only** — moves to the bed corner, away from the print
- ✅ **Lifts Z before travel** — always clears the print before any XY movement
- ✅ **Restores bed mesh** — uses saved mesh (M420/BED_MESH_PROFILE), never re-probes
- ✅ **Validates output** — checks for missing temps, Z collisions, unsafe movement order

> ⚠️ **IMPORTANT:** Your print must remain in the exact same position on the bed! Do not move it, bump the bed, or adjust anything before running the resume file.

## Supported Firmware

| Firmware | Profile | Bed Mesh Command |
|----------|---------|-----------------|
| **Marlin** (default) | `default_marlin` | `M420 S1` |
| **Klipper** | `klipper` | `BED_MESH_PROFILE LOAD=default` |
| **RepRapFirmware** | `reprapfirmware` | `M376 H5` |

## Project Structure

```
failfixer/
├── app/
│   ├── main.py              # CLI entry point
│   └── controller.py        # Pipeline orchestrator
├── core/
│   ├── gcode_parser.py      # 3-tier layer detection parser
│   ├── layer_mapper.py      # Layer ↔ Z height mapping
│   ├── resume_generator.py  # Collision-safe resume G-code generator
│   ├── validator.py         # Output safety validation
│   └── profiles.py          # Printer profile loader
├── ui/
│   ├── main_window.py       # PyQt6 main window
│   └── wizard.py            # Step-by-step wizard
├── profiles/
│   ├── default_marlin.json
│   ├── klipper.json
│   └── reprapfirmware.json
├── assets/
│   ├── logo.png
│   └── logo.ico
├── tests/
│   └── test_core.py         # 54 comprehensive tests
├── run_gui.py               # GUI launcher
├── build.bat                # PyInstaller build script
└── requirements.txt
```

## Building the .exe

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --icon=assets/logo.ico --add-data "assets;assets" --add-data "profiles;profiles" --name FailFixer run_gui.py
```

Output: `dist/FailFixer.exe`

## Testing

```bash
pip install pytest
cd ..  # run from parent of failfixer/
python -m pytest failfixer/ -v
```

61 tests covering parser, layer mapper, resume generator, validator, controller, and end-to-end integration.

## FAQ

**How do I find the failed layer number?**
Open your original G-code in a slicer preview (Cura, PrusaSlicer) and scrub to the height where it stopped. Or measure with calipers and use the Z Height option.

**What if I don't know the exact layer?**
Go one layer lower than you think. Overlapping a layer is much better than leaving a gap.

**Will there be a visible seam?**
Usually a slight line is visible. Minimize it with a small negative Z offset (-0.05 to -0.1mm).

**Can I resume a print from hours/days ago?**
Yes, as long as the print hasn't moved on the bed.

## License

MIT

## Credits

Built by [@SlimQuiggle](https://github.com/SlimQuiggle)
