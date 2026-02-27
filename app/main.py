"""FailFixer — CLI entry point.

Usage:
    python -m failfixer.app.main <gcode_file> --layer <N>
    python -m failfixer.app.main <gcode_file> --z <mm>

Options:
    --layer     Resume from this layer number (int)
    --z         Resume from this measured Z height (float, mm)
    --offset    Z offset adjustment in mm (default: 0.0)
    --output    Output directory (default: same as input)
    --profile   Printer profile filename (default: default_marlin.json)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .controller import Controller, ResumeRequest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="failfixer",
        description="FailFixer — Resume failed 3D prints from G-code.",
    )
    p.add_argument(
        "gcode_file",
        type=str,
        help="Path to the original G-code file.",
    )

    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--layer",
        type=int,
        help="Resume from this layer number.",
    )
    group.add_argument(
        "--z",
        type=float,
        help="Resume from this measured Z height (mm).",
    )

    p.add_argument(
        "--offset",
        type=float,
        default=0.0,
        help="Z offset adjustment in mm (default: 0.0).",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: same as input file).",
    )
    p.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Printer profile filename (default: default_marlin.json).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.gcode_file)
    if not input_path.is_file():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 1

    # Determine selector
    selector: int | float
    if args.layer is not None:
        selector = args.layer
    else:
        selector = args.z

    request = ResumeRequest(
        input_path=input_path,
        resume_selector=selector,
        z_offset_mm=args.offset,
        output_dir=args.output,
        profile_name=args.profile,
    )

    controller = Controller()

    try:
        result = controller.run(request)
    except (RuntimeError, KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Report
    print(f"✓ Resume file saved: {result.output_path}")
    print(f"  Layer: {result.layer_match.layer.number}")
    print(f"  Z height: {result.layer_match.layer.z_height:.3f} mm")
    print(f"  Lines: {result.line_count}")

    if result.warnings:
        print("  Warnings:")
        for w in result.warnings:
            print(f"    ⚠ {w}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
