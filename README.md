# FailFixer 🔧

**Resume failed 3D prints with one click.**

FailFixer generates a safe resume G-code file from your original failed print. Just tell it what layer the print failed at, and it outputs a new file you can print as if it were a fresh job — but it picks up right where the old one stopped.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

## Features

- **Simple** — Load G-code, pick the failed layer, generate. That's it.
- **Dual recovery modes** — Choose **Resume In-Air** (continue on top of the failed print) or **Restart from Build Plate** (print the missing section separately for glue-up).
- **Collision-safe** — Never homes Z (would crash into your print). Uses smart XY-only homing + G92 position setting.
- **Multi-firmware** — Supports Marlin, Klipper, and RepRapFirmware out of the box.
- **Drag & drop** — Drop your .gcode file right into the window.
- **Fast** — Parses 50MB G-code files in under 2 seconds.
- **Offline** — No internet, no accounts, no telemetry. Everything runs locally.
- **Standalone .exe** — Download and run. No Python installation needed.

## Activation

FailFixer requires a license key to unlock the Generate feature.

### For Customers — Lemon Squeezy (recommended)

1. Purchase FailFixer from our store (Lemon Squeezy).
2. You'll receive a **license key** (UUID format, e.g. `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) in your purchase confirmation email.
3. Launch FailFixer — the Activation dialog appears on first run.
4. **Paste your Lemon Squeezy license key** into the License Key field and click **Activate**.
5. The app contacts the Lemon Squeezy license server to validate and activate your key. No Machine ID exchange needed.
6. Your activation is stored locally. On subsequent launches, the app re-validates online.
   - If you're offline, a **7-day grace period** from the last successful validation allows continued use.
7. To view or replace your key later, click the **🔑 License** button in the main window.

### Backup / Offline Mode — FFX1 Manual Keys

If you need fully-offline activation (no internet required), a legacy FFX1 key can be issued manually. The app auto-detects the key format.

**For Seller — Generating FFX1 Keys:**

Set your secret once (keep this private!):
```bash
set FAILFIXER_LICENSE_SECRET=your-production-secret-here    # Windows
export FAILFIXER_LICENSE_SECRET=your-production-secret-here  # Linux/Mac
```

Generate a key for a customer:
```bash
# Perpetual key
python -m failfixer.tools.generate_license --name "John Doe" --machine <customer_machine_id>

# Key that expires in 365 days
python -m failfixer.tools.generate_license --name "John Doe" --machine <customer_machine_id> --days 365

# Append to CSV ledger for record-keeping
python -m failfixer.tools.generate_license --name "John Doe" --machine <customer_machine_id> --out keys.csv
```

**FFX1 manual flow:**
1. Customer purchases via your store.
2. Customer sends you their Machine ID (shown in the app activation dialog).
3. You run `generate_license.py` with their name + machine ID.
4. You email/DM them the generated `FFX1-…` key.

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

# Print remaining section from build plate for glue-up
python -m failfixer.app.main myprint.gcode --layer 120 --resume-mode from_plate
```

## How It Works

1. **Parses** your original G-code file, detecting layers, temperatures, and printer settings
2. **Strips** everything below your selected resume layer
3. **Generates** a mode-specific startup sequence:
   - Heats bed and nozzle
   - Homes X/Y only (never Z)
   - **Resume In-Air:** sets Z via G92 at the failed height + optional offset, then lifts to clearance
   - **Restart from Build Plate:** zeroes Z at the plate and prepares to print the remaining section as a separate part
   - Primes nozzle at a safe corner
4. **Appends** the remaining G-code from your resume layer onward
   - In Build Plate mode, Z values are shifted down so the remaining section starts from the bed
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
│   ├── profiles.py          # Printer profile loader
│   └── licensing.py         # Offline HMAC-SHA256 license system
├── ui/
│   ├── main_window.py       # PyQt6 main window + activation dialog
│   └── wizard.py            # Step-by-step wizard
├── tools/
│   └── generate_license.py  # Seller-side license key generator CLI
├── profiles/
│   ├── default_marlin.json
│   ├── klipper.json
│   └── reprapfirmware.json
├── assets/
│   ├── logo.png
│   └── logo.ico
├── tests/
│   ├── test_core.py         # 54 comprehensive tests
│   └── test_licensing.py    # 15 licensing tests
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

69 tests covering parser, layer mapper, resume generator, validator, controller, licensing, and end-to-end integration.

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

Developed by **FleX3Designs** · [@SlimQuiggle](https://github.com/SlimQuiggle)



## Project Handoff
- See PROJECT_STATUS.md for current state, completed work, open issues, roadmap, and AI contributor rules.

