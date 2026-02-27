"""Pipeline controller for FailFixer.

Orchestrates: load → parse → map layers → generate resume → validate → save.

Exposes two APIs:
  - Controller.run(ResumeRequest) — low-level, used by CLI
  - FailFixerController.process(...) — high-level, used by UI
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from ..core.gcode_parser import GCodeParser, ParsedGCode
from ..core.layer_mapper import LayerMapper, LayerMatch
from ..core.profiles import PrinterProfile, ProfileLoader
from ..core.resume_generator import ResumeConfig, ResumeGenerator
from ..core.validator import ValidationResult, Validator


@dataclass
class ResumeRequest:
    """Everything needed to produce a resume file."""

    input_path: str | Path
    resume_selector: Union[int, float]       # int = layer number, float = Z mm
    z_offset_mm: float = 0.0
    output_dir: str | Path | None = None     # defaults to same dir as input
    profile_name: str | None = None          # profile filename or None for default


@dataclass
class ResumeResult:
    """What the pipeline returns."""

    output_path: Path
    layer_match: LayerMatch
    validation: ValidationResult
    line_count: int
    warnings: list[str]
    total_layers: int = 0
    bed_temp: float = 0.0
    nozzle_temp: float = 0.0


class Controller:
    """High-level orchestrator for the resume pipeline."""

    def __init__(self, profiles_dir: str | Path | None = None) -> None:
        self._parser = GCodeParser()
        self._generator = ResumeGenerator()
        self._validator = Validator()
        self._profile_loader = ProfileLoader(profiles_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, request: ResumeRequest) -> ResumeResult:
        """Execute the full pipeline and return a *ResumeResult*."""
        warnings: list[str] = []

        # 1. Load profile
        profile = self._profile_loader.load(request.profile_name)

        # 2. Parse
        input_path = Path(request.input_path)
        parsed = self._parser.parse_file(input_path)

        if not parsed.layers:
            raise RuntimeError(
                "No layers detected in the G-code file. "
                "Cannot generate a resume file."
            )

        # 3. Map layers
        mapper = LayerMapper(parsed.layers, tolerance_mm=profile.tolerance_mm)
        match = self._resolve_layer(mapper, request.resume_selector)

        if match.warning:
            warnings.append(match.warning)

        # 4. Build config
        config = ResumeConfig(
            resume_layer=match.layer.number,
            resume_z=match.layer.z_height,
            bed_temp=parsed.state.bed_temp,
            nozzle_temp=parsed.state.nozzle_temp,
            safe_lift_mm=profile.safe_lift_mm,
            z_offset_mm=request.z_offset_mm,
            bed_mesh_cmd=profile.bed_mesh_cmd,
        )

        # Temperature sanity
        if config.bed_temp <= 0:
            warnings.append(
                "Bed temperature not detected in original file — "
                "using 0. You may need to edit the output."
            )
        if config.nozzle_temp <= 0:
            warnings.append(
                "Nozzle temperature not detected in original file — "
                "using 0. You may need to edit the output."
            )

        # 5. Generate
        lines = self._generator.generate(parsed, match, config)

        # 6. Validate
        validation = self._validator.validate(
            lines,
            resume_z=config.resume_z + config.z_offset_mm,
            safe_lift_z=config.safe_lift_mm,
        )
        for issue in validation.warnings:
            warnings.append(f"[{issue.code}] line {issue.line_number}: {issue.message}")

        if not validation.ok:
            error_msgs = "; ".join(
                f"[{e.code}] line {e.line_number}: {e.message}"
                for e in validation.errors
            )
            raise RuntimeError(f"Validation failed: {error_msgs}")

        # 7. Save
        output_path = self._build_output_path(
            input_path, match.layer.number, request.output_dir
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="\n") as fh:
            for line in lines:
                fh.write(line)
                fh.write("\n")

        return ResumeResult(
            output_path=output_path,
            layer_match=match,
            validation=validation,
            line_count=len(lines),
            warnings=warnings,
            total_layers=len(parsed.layers),
            bed_temp=parsed.state.bed_temp,
            nozzle_temp=parsed.state.nozzle_temp,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_layer(
        mapper: LayerMapper,
        selector: Union[int, float],
    ) -> LayerMatch:
        if isinstance(selector, int):
            return mapper.by_layer_number(selector)
        return mapper.by_z_height(selector)

    @staticmethod
    def _build_output_path(
        input_path: Path,
        layer_number: int,
        output_dir: str | Path | None,
    ) -> Path:
        stem = input_path.stem
        suffix = input_path.suffix or ".gcode"
        name = f"{stem}_resume_layer{layer_number:04d}{suffix}"
        if output_dir is not None:
            return Path(output_dir) / name
        return input_path.parent / name


# ======================================================================
# High-level UI-facing controller
# ======================================================================


@dataclass
class ProcessResult:
    """UI-friendly result from FailFixerController.process()."""

    output_path: Path
    total_layers: int
    resume_layer: int
    resume_z: float
    bed_temp: float
    nozzle_temp: float
    line_count: int
    warnings: list[str]


class FailFixerController:
    """Convenience wrapper used by the PyQt6 UI.

    Translates the UI's keyword-argument style into the core
    Controller's ResumeRequest/ResumeResult API.
    """

    def __init__(self, profiles_dir: str | Path | None = None) -> None:
        self._core = Controller(profiles_dir)

    def process(
        self,
        gcode_path: str,
        layer_num: Optional[int] = None,
        z_height: Optional[float] = None,
        z_offset: float = 0.0,
        park_x: Optional[float] = None,
        park_y: Optional[float] = None,
        profile: str = "default_marlin",
        output_path: Optional[str] = None,
    ) -> ProcessResult:
        """Run the full pipeline and return a *ProcessResult*.

        Either *layer_num* or *z_height* must be provided (not both).
        """
        if layer_num is None and z_height is None:
            raise ValueError("Either layer_num or z_height must be provided.")

        # Build selector
        selector: Union[int, float]
        if layer_num is not None:
            selector = int(layer_num)
        else:
            selector = float(z_height)  # type: ignore[arg-type]

        # Ensure profile has .json extension
        profile_name = profile if profile.endswith(".json") else f"{profile}.json"

        # Build output_dir from output_path if provided
        output_dir: Optional[str] = None
        if output_path:
            output_dir = str(Path(output_path).parent)

        request = ResumeRequest(
            input_path=gcode_path,
            resume_selector=selector,
            z_offset_mm=z_offset,
            output_dir=output_dir,
            profile_name=profile_name,
        )

        result = self._core.run(request)

        # If user specified a specific output_path, rename to match
        if output_path:
            target = Path(output_path)
            if result.output_path != target:
                result.output_path.rename(target)
                result.output_path = target

        return ProcessResult(
            output_path=result.output_path,
            total_layers=result.total_layers,
            resume_layer=result.layer_match.layer.number,
            resume_z=result.layer_match.layer.z_height,
            bed_temp=result.bed_temp,
            nozzle_temp=result.nozzle_temp,
            line_count=result.line_count,
            warnings=result.warnings,
        )
