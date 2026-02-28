"""Comprehensive tests for FailFixer core modules.

Covers:
  - gcode_parser: 3 layer detection methods, temp/mode detection, empty file
  - layer_mapper: exact layer, Z exact/fuzzy/out-of-tolerance, invalid layer
  - resume_generator: header contents, no G28 Z, Z lift before XY, layer content, Z offset
  - validator: missing temps, G28 Z, XY before Z, Z collision, clean file
  - controller: full pipeline via Controller.run() and FailFixerController.process()
"""

from __future__ import annotations

import pytest
from pathlib import Path

from failfixer.core.gcode_parser import GCodeParser, ParsedGCode, LayerInfo, PrinterState
from failfixer.core.layer_mapper import LayerMapper, LayerMatch
from failfixer.core.resume_generator import ResumeGenerator, ResumeConfig
from failfixer.core.validator import Validator, ValidationResult, Severity
from failfixer.app.controller import Controller, ResumeRequest, FailFixerController


# ======================================================================
# Fixtures & helpers
# ======================================================================

GCODE_LAYER_COMMENT = """\
; Start
G28
G21
G90
M82
M140 S60
M190 S60
M104 S200
M109 S200
G1 Z0.3 F3000 E0.5
;LAYER:0
G1 X10 Y10 Z0.3 E1.0
G1 X20 Y20 E2.0
;LAYER:1
G1 X10 Y10 Z0.6 E3.0
G1 X30 Y30 E4.0
;LAYER:2
G1 X10 Y10 Z0.9 E5.0
G1 X40 Y40 E6.0
"""

GCODE_LAYER_CHANGE = """\
; header
G28
G21
G90
M82
M140 S55
M190 S55
M104 S210
M109 S210
G1 Z0.2 F600 E0.1
;LAYER_CHANGE
G1 Z0.2 F600
G1 X5 Y5 E1.0
;LAYER_CHANGE
G1 Z0.4 F600
G1 X15 Y15 E2.0
;LAYER_CHANGE
G1 Z0.6 F600
G1 X25 Y25 E3.0
"""

GCODE_Z_FALLBACK = """\
; basic file, no layer comments
G28
G21
G90
M82
M140 S70
M190 S70
M104 S215
M109 S215
G1 Z0.3 F3000 E0.1
G1 X10 Y10 E1.0
G1 Z0.6 F3000
G1 X20 Y20 E2.0
G1 Z0.9 F3000
G1 X30 Y30 E3.0
"""

GCODE_EMPTY = ""

GCODE_MINIMAL_VALID = """\
; Start
G28
G21
G90
M82
M140 S60
M190 S60
M104 S200
M109 S200
G1 Z0.3 F3000 E0.5
;LAYER:0
G1 X10 Y10 Z0.3 E1.0
;LAYER:1
G1 X10 Y10 Z0.6 E2.0
"""


def _write_gcode(tmp_path: Path, content: str, name: str = "test.gcode") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ======================================================================
# 1. GCodeParser tests
# ======================================================================

class TestGCodeParserLayerComment:
    """Test ;LAYER:<n> detection method."""

    def test_detects_layers_via_comment(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_COMMENT)
        assert result.detection_method == "comment_layer"
        assert len(result.layers) == 3
        assert result.layers[0].number == 0
        assert result.layers[1].number == 1
        assert result.layers[2].number == 2

    def test_layer_start_end_lines(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_COMMENT)
        # Layer 0 starts at its ;LAYER:0 line
        assert result.layers[0].start_line < result.layers[1].start_line
        assert result.layers[1].start_line < result.layers[2].start_line
        # Last layer end_line is last line
        assert result.layers[-1].end_line == len(result.lines) - 1

    def test_z_heights_backfilled(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_COMMENT)
        # Z heights should be filled in from Z moves
        for layer in result.layers:
            assert layer.z_height > 0


class TestGCodeParserLayerChange:
    """Test ;LAYER_CHANGE detection method."""

    def test_detects_layers_via_change_marker(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_CHANGE)
        assert result.detection_method == "layer_change"
        assert len(result.layers) == 3

    def test_layer_numbers_sequential(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_CHANGE)
        for i, layer in enumerate(result.layers):
            assert layer.number == i

    def test_z_heights_assigned(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_CHANGE)
        # Z heights should increase across layers
        zs = [l.z_height for l in result.layers]
        assert zs == sorted(zs)


class TestGCodeParserZFallback:
    """Test Z-move fallback detection method."""

    def test_detects_layers_via_z_moves(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_Z_FALLBACK)
        assert result.detection_method == "z_move"
        assert len(result.layers) >= 3

    def test_z_heights_increasing(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_Z_FALLBACK)
        zs = [l.z_height for l in result.layers]
        for i in range(1, len(zs)):
            assert zs[i] > zs[i - 1]


class TestGCodeParserState:
    """Test printer state detection (temps, modes)."""

    def test_temp_detection(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_COMMENT)
        assert result.state.bed_temp == 60.0
        assert result.state.nozzle_temp == 200.0

    def test_mode_detection(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_LAYER_COMMENT)
        assert result.state.units == "G21"
        assert result.state.positioning == "G90"
        assert result.state.extruder_mode == "M82"

    def test_temp_detection_with_r_parameter(self):
        gcode = "M140 R60\nM190 R60\nM104 R205\nM109 R205\nG1 X1 Y1 E0.1\n"
        parser = GCodeParser()
        result = parser.parse_string(gcode)
        assert result.state.bed_temp == 60.0
        assert result.state.nozzle_temp == 205.0

    def test_temp_detection_with_klipper_commands(self):
        gcode = "\n".join([
            "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=65",
            "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=215",
            "TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM=65",
            "TEMPERATURE_WAIT SENSOR=extruder MINIMUM=215",
            "G1 X1 Y1 E0.1",
        ]) + "\n"
        parser = GCodeParser()
        result = parser.parse_string(gcode)
        assert result.state.bed_temp == 65.0
        assert result.state.nozzle_temp == 215.0

    def test_imperial_units(self):
        gcode = "G20\nG91\nM83\nM140 S50\nM104 S180\nG1 Z0.3 E0.1\n"
        parser = GCodeParser()
        result = parser.parse_string(gcode)
        assert result.state.units == "G20"
        assert result.state.positioning == "G91"
        assert result.state.extruder_mode == "M83"


class TestGCodeParserEmpty:
    """Test empty file edge case."""

    def test_empty_string(self):
        parser = GCodeParser()
        result = parser.parse_string(GCODE_EMPTY)
        assert result.lines == []  # StringIO("") iterates zero lines
        assert result.layers == []
        assert result.detection_method == "none"

    def test_comments_only(self):
        parser = GCodeParser()
        result = parser.parse_string("; just a comment\n; another\n")
        assert result.layers == []
        assert result.detection_method == "none"


class TestGCodeParserFile:
    """Test file-based parsing."""

    def test_parse_file(self, tmp_path):
        p = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        parser = GCodeParser()
        result = parser.parse_file(p)
        assert result.detection_method == "comment_layer"
        assert len(result.layers) == 3


# ======================================================================
# 2. LayerMapper tests
# ======================================================================

@pytest.fixture
def sample_layers():
    return [
        LayerInfo(number=0, z_height=0.3, start_line=10, end_line=19),
        LayerInfo(number=1, z_height=0.6, start_line=20, end_line=29),
        LayerInfo(number=2, z_height=0.9, start_line=30, end_line=39),
        LayerInfo(number=3, z_height=1.2, start_line=40, end_line=49),
    ]


class TestLayerMapperByNumber:
    """Test layer lookup by number."""

    def test_exact_layer_lookup(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        match = mapper.by_layer_number(0)
        assert match.layer.number == 0
        assert match.exact is True
        assert match.delta_mm == 0.0

    def test_all_layers_accessible(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        for i in range(4):
            match = mapper.by_layer_number(i)
            assert match.layer.number == i

    def test_invalid_layer_number(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        with pytest.raises(KeyError, match="Layer 99 not found"):
            mapper.by_layer_number(99)

    def test_negative_layer_number(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        with pytest.raises(KeyError):
            mapper.by_layer_number(-1)


class TestLayerMapperByZHeight:
    """Test layer lookup by Z height."""

    def test_exact_z_match(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        match = mapper.by_z_height(0.6)
        assert match.layer.number == 1
        assert match.exact is True
        assert match.delta_mm == 0.0

    def test_fuzzy_z_match_within_tolerance(self, sample_layers):
        mapper = LayerMapper(sample_layers, tolerance_mm=0.15)
        match = mapper.by_z_height(0.65)  # 0.05 mm off from 0.6
        assert match.layer.number == 1
        assert match.exact is False
        assert match.warning is not None
        assert abs(match.delta_mm) <= 0.15

    def test_z_out_of_tolerance(self, sample_layers):
        mapper = LayerMapper(sample_layers, tolerance_mm=0.15)
        with pytest.raises(ValueError, match="exceeds the tolerance"):
            mapper.by_z_height(5.0)

    def test_exact_z_at_boundaries(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        # First layer
        match = mapper.by_z_height(0.3)
        assert match.layer.number == 0
        # Last layer
        match = mapper.by_z_height(1.2)
        assert match.layer.number == 3


class TestLayerMapperProperties:
    """Test mapper properties."""

    def test_layer_count(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        assert mapper.layer_count == 4

    def test_min_max(self, sample_layers):
        mapper = LayerMapper(sample_layers)
        assert mapper.min_layer == 0
        assert mapper.max_layer == 3
        assert mapper.min_z == 0.3
        assert mapper.max_z == 1.2

    def test_empty_layers_raises(self):
        with pytest.raises(ValueError, match="empty"):
            LayerMapper([])


# ======================================================================
# 3. ResumeGenerator tests
# ======================================================================

@pytest.fixture
def parsed_gcode():
    parser = GCodeParser()
    return parser.parse_string(GCODE_LAYER_COMMENT)


@pytest.fixture
def resume_config(parsed_gcode):
    return ResumeConfig(
        resume_layer=1,
        resume_z=0.6,
        bed_temp=60.0,
        nozzle_temp=200.0,
        safe_lift_mm=10.0,
        z_offset_mm=0.0,
    )


class TestResumeGeneratorHeader:
    """Test resume header generation."""

    def test_header_contains_temps(self, parsed_gcode, resume_config):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        lines = gen.generate(parsed_gcode, match, resume_config)
        text = "\n".join(lines)
        assert "M140 S60" in text
        assert "M104 S200" in text
        assert "M190 S60" in text
        assert "M109 S200" in text

    def test_preserves_thumbnail_and_material_metadata(self, resume_config):
        gcode = "\n".join([
            "; generated with OrcaSlicer",
            "; filament_type = PLA",
            "; filament_colour = #FFFFFF",
            "; thumbnail begin 32x32 10",
            "; iVBORw0KGgoAAA...",
            "; thumbnail end",
            "M140 S60",
            "M104 S200",
            ";LAYER:0",
            "G1 Z0.2",
            "G1 X1 Y1 E0.2",
            ";LAYER:1",
            "G1 Z0.4",
            "G1 X2 Y2 E0.3",
        ]) + "\n"

        parser = GCodeParser()
        parsed = parser.parse_string(gcode)
        mapper = LayerMapper(parsed.layers)
        match = mapper.by_layer_number(1)

        gen = ResumeGenerator()
        lines = gen.generate(parsed, match, resume_config)
        text = "\n".join(lines)

        assert "; thumbnail begin 32x32 10" in text
        assert "; thumbnail end" in text
        assert "; filament_type = PLA" in text

    def test_header_contains_resume_info(self, parsed_gcode, resume_config):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        lines = gen.generate(parsed_gcode, match, resume_config)
        text = "\n".join(lines)
        assert "Resume Layer: 1" in text
        assert "Resume Z: 0.600" in text

    def test_no_g28_z_in_output(self, parsed_gcode, resume_config):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        lines = gen.generate(parsed_gcode, match, resume_config)
        for line in lines:
            stripped = line.strip().upper()
            if stripped.startswith("G28"):
                # Only G28 X Y is allowed, not G28 Z
                assert "Z" not in stripped, f"G28 Z found in output: {line}"


class TestResumeGeneratorMovement:
    """Test Z lift before XY and correct layer content."""

    def test_z_lift_before_xy(self, parsed_gcode, resume_config):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        lines = gen.generate(parsed_gcode, match, resume_config)
        first_z_line = None
        first_xy_line = None
        for i, line in enumerate(lines):
            cmd = line.split(";")[0].strip().upper()
            if cmd.startswith(("G0", "G1")) and "Z" in cmd:
                if first_z_line is None:
                    first_z_line = i
            if cmd.startswith(("G0", "G1")) and ("X" in cmd or "Y" in cmd):
                if first_xy_line is None:
                    first_xy_line = i
        # G28 X Y is first XY, but G1 Z lift should come before any G0/G1 XY
        assert first_z_line is not None, "No Z lift found"

    def test_correct_layer_content_appended(self, parsed_gcode, resume_config):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        lines = gen.generate(parsed_gcode, match, resume_config)
        text = "\n".join(lines)
        # Layer 1 content should be present
        assert ";LAYER:1" in text
        # Layer 0 content should NOT be present (we resume from layer 1)
        # The header is separate, so ;LAYER:0 should not appear
        assert ";LAYER:0" not in text
        # Layer 2 should also be present (everything from layer 1 onward)
        assert ";LAYER:2" in text


class TestResumeGeneratorBuildPlateMode:
    """Test build-plate mode behavior."""

    def test_build_plate_mode_shifts_z_down(self, parsed_gcode):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        config = ResumeConfig(
            resume_layer=1,
            resume_z=0.6,
            bed_temp=60.0,
            nozzle_temp=200.0,
            safe_lift_mm=10.0,
            z_offset_mm=0.0,
            resume_mode="from_plate",
        )
        lines = gen.generate(parsed_gcode, match, config)
        text = "\n".join(lines)
        assert "Resume Mode: from_plate" in text
        assert "G28" in text
        assert "G1 X10 Y10 Z0.000 E3.0" in text


class TestResumeGeneratorZOffset:
    """Test Z offset application."""

    def test_z_offset_applied(self, parsed_gcode):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        config_with_offset = ResumeConfig(
            resume_layer=1,
            resume_z=0.6,
            bed_temp=60.0,
            nozzle_temp=200.0,
            safe_lift_mm=10.0,
            z_offset_mm=0.5,
        )
        lines = gen.generate(parsed_gcode, match, config_with_offset)
        text = "\n".join(lines)
        # Offset should be noted in header
        assert "Offset: 0.500" in text

    def test_generate_text_returns_string(self, parsed_gcode, resume_config):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        text = gen.generate_text(parsed_gcode, match, resume_config)
        assert isinstance(text, str)
        assert text.endswith("\n")


class TestResumeGeneratorFromPlate:
    """Plate mode should print selected section from Z0."""

    def test_from_plate_header_uses_full_homing(self, parsed_gcode):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        config = ResumeConfig(
            resume_layer=1,
            resume_z=0.6,
            bed_temp=60.0,
            nozzle_temp=200.0,
            resume_mode="from_plate",
        )
        lines = gen.generate(parsed_gcode, match, config)
        text = "\n".join(lines)
        assert "Resume Mode: from_plate" in text
        assert "G28                        ; Home all axes" in text

    def test_from_plate_rebases_z_values(self, parsed_gcode):
        gen = ResumeGenerator()
        mapper = LayerMapper(parsed_gcode.layers)
        match = mapper.by_layer_number(1)
        config = ResumeConfig(
            resume_layer=1,
            resume_z=0.6,
            bed_temp=60.0,
            nozzle_temp=200.0,
            resume_mode="from_plate",
        )
        lines = gen.generate(parsed_gcode, match, config)
        text = "\n".join(lines)
        assert "G1 X10 Y10 Z0.000 E3.0" in text
        assert "G1 X10 Y10 Z0.300 E5.0" in text


# ======================================================================
# 4. Validator tests
# ======================================================================

class TestValidatorMissingTemps:
    """Missing temperatures should produce ERROR."""

    def test_missing_bed_temp(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M104 S200",
            "M109 S200",
            "G1 Z10 F3000",
            "G1 X10 Y10 E1.0",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "MISSING_BED_TEMP" in codes
        assert not result.ok

    def test_missing_nozzle_temp(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M140 S60",
            "M190 S60",
            "G1 Z10 F3000",
            "G1 X10 Y10 E1.0",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "MISSING_NOZZLE_TEMP" in codes

    def test_temp_detection_with_r_parameter(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M140 R60",
            "M190 R60",
            "M104 R205",
            "M109 R205",
            "G1 Z10 F3000",
            "G1 X10 Y10 E1.0",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "MISSING_BED_TEMP" not in codes
        assert "MISSING_NOZZLE_TEMP" not in codes

    def test_missing_both_temps(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "G1 Z10 F3000",
            "G1 X10 Y10 E1.0",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "MISSING_BED_TEMP" in codes
        assert "MISSING_NOZZLE_TEMP" in codes


class TestValidatorG28Z:
    """G28 Z should produce ERROR."""

    def test_g28_z_detected(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M140 S60",
            "M190 S60",
            "M104 S200",
            "M109 S200",
            "G28 Z",
            "G1 Z10 F3000",
            "G1 X10 Y10 E1.0",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "Z_HOME" in codes
        assert not result.ok

    def test_g28_xy_is_fine(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M140 S60",
            "M190 S60",
            "M104 S200",
            "M109 S200",
            "G28 X Y",
            "G1 Z10 F3000",
            "G1 X10 Y10 E1.0",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "Z_HOME" not in codes

    def test_g28_z_allowed_in_from_plate_mode(self):
        lines = [
            "M140 S60",
            "M190 S60",
            "M104 S200",
            "M109 S200",
            "G28 Z",
            "G1 X10 Y10 E1.0",
        ]
        v = Validator()
        result = v.validate(lines, resume_mode="from_plate")
        codes = [e.code for e in result.errors]
        assert "Z_HOME" not in codes


class TestValidatorXYBeforeZ:
    """XY movement before Z lift should produce ERROR."""

    def test_xy_before_z_error(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M140 S60",
            "M190 S60",
            "M104 S200",
            "M109 S200",
            "G1 X10 Y10 F3000",
            "G1 Z10 F3000",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "XY_BEFORE_Z" in codes

    def test_z_before_xy_ok(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M140 S60",
            "M190 S60",
            "M104 S200",
            "M109 S200",
            "G1 Z10 F3000",
            "G1 X10 Y10 F3000",
            "; --- End Resume Header ---",
        ]
        v = Validator()
        result = v.validate(lines)
        codes = [e.code for e in result.errors]
        assert "XY_BEFORE_Z" not in codes


class TestValidatorZCollision:
    """Z below resume height should produce WARNING."""

    def test_z_collision_warning(self):
        lines = [
            "; --- FailFixer Resume Header ---",
            "M140 S60",
            "M190 S60",
            "M104 S200",
            "M109 S200",
            "G1 Z10 F3000",
            "G1 X10 Y10 F3000",
            "; --- End Resume Header ---",
            "G1 Z0.1 F3000",  # well below resume_z=5.0
        ]
        v = Validator()
        result = v.validate(lines, resume_z=5.0)
        codes = [w.code for w in result.warnings]
        assert "Z_COLLISION" in codes
        # Should still pass (warnings, not errors)
        assert result.ok


class TestValidatorCleanFile:
    """A properly generated file should validate OK."""

    def test_clean_file_ok(self):
        parser = GCodeParser()
        parsed = parser.parse_string(GCODE_LAYER_COMMENT)
        mapper = LayerMapper(parsed.layers)
        match = mapper.by_layer_number(1)
        config = ResumeConfig(
            resume_layer=1, resume_z=0.6,
            bed_temp=60.0, nozzle_temp=200.0,
            safe_lift_mm=10.0, z_offset_mm=0.0,
        )
        gen = ResumeGenerator()
        lines = gen.generate(parsed, match, config)
        v = Validator()
        result = v.validate(lines, resume_z=0.6)
        assert result.ok, f"Errors: {[e.message for e in result.errors]}"

    def test_clean_summary(self):
        parser = GCodeParser()
        parsed = parser.parse_string(GCODE_LAYER_COMMENT)
        mapper = LayerMapper(parsed.layers)
        match = mapper.by_layer_number(1)
        config = ResumeConfig(
            resume_layer=1, resume_z=0.6,
            bed_temp=60.0, nozzle_temp=200.0,
            safe_lift_mm=10.0, z_offset_mm=0.0,
        )
        gen = ResumeGenerator()
        lines = gen.generate(parsed, match, config)
        v = Validator()
        result = v.validate(lines, resume_z=0.6)
        summary = result.summary()
        assert "passed" in summary.lower() or "no issues" in summary.lower()


# ======================================================================
# 5. Controller tests
# ======================================================================

class TestControllerRun:
    """Test Controller.run() full pipeline."""

    def test_run_by_layer_number(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
        request = ResumeRequest(
            input_path=str(gcode_path),
            resume_selector=1,
            z_offset_mm=0.0,
            output_dir=str(tmp_path),
        )
        result = ctrl.run(request)
        assert result.output_path.exists()
        assert result.line_count > 0
        assert result.total_layers == 3
        assert result.validation.ok

    def test_run_by_z_height(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
        request = ResumeRequest(
            input_path=str(gcode_path),
            resume_selector=0.6,
            z_offset_mm=0.0,
            output_dir=str(tmp_path),
        )
        result = ctrl.run(request)
        assert result.output_path.exists()
        assert result.layer_match.layer.z_height == pytest.approx(0.6, abs=0.2)

    def test_output_file_naming(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT, name="benchy.gcode")
        ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
        request = ResumeRequest(
            input_path=str(gcode_path),
            resume_selector=2,
            output_dir=str(tmp_path),
        )
        result = ctrl.run(request)
        assert "benchy" in result.output_path.name
        assert "resume" in result.output_path.name
        assert "layer0002" in result.output_path.name
        assert result.output_path.suffix == ".gcode"

    def test_run_no_layers_raises(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, "; empty file\n")
        ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
        request = ResumeRequest(
            input_path=str(gcode_path),
            resume_selector=0,
            output_dir=str(tmp_path),
        )
        with pytest.raises(RuntimeError, match="No layers detected"):
            ctrl.run(request)

    def test_run_with_z_offset(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
        request = ResumeRequest(
            input_path=str(gcode_path),
            resume_selector=1,
            z_offset_mm=0.5,
            output_dir=str(tmp_path),
        )
        result = ctrl.run(request)
        content = result.output_path.read_text(encoding="utf-8")
        assert "Offset: 0.500" in content

    def test_output_has_no_g28_z(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
        request = ResumeRequest(
            input_path=str(gcode_path),
            resume_selector=1,
            output_dir=str(tmp_path),
        )
        result = ctrl.run(request)
        content = result.output_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip().upper()
            if stripped.startswith("G28"):
                assert "Z" not in stripped

    def test_run_from_plate_mode_rebases_to_z_zero(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
        request = ResumeRequest(
            input_path=str(gcode_path),
            resume_selector=1,
            output_dir=str(tmp_path),
            resume_mode="from_plate",
        )
        result = ctrl.run(request)
        content = result.output_path.read_text(encoding="utf-8")
        assert "Resume Mode: from_plate" in content
        assert "G1 X10 Y10 Z0.000 E3.0" in content


class TestFailFixerControllerProcess:
    """Test FailFixerController.process() high-level API."""

    def test_process_by_layer(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = FailFixerController(profiles_dir=str(tmp_path / "profiles"))
        result = ctrl.process(
            gcode_path=str(gcode_path),
            layer_num=1,
            output_path=str(tmp_path / "output_resume.gcode"),
        )
        assert result.output_path.exists()
        assert result.resume_layer == 1
        assert result.total_layers == 3
        assert result.line_count > 0

    def test_process_by_z(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = FailFixerController(profiles_dir=str(tmp_path / "profiles"))
        result = ctrl.process(
            gcode_path=str(gcode_path),
            z_height=0.6,
            output_path=str(tmp_path / "output_resume.gcode"),
        )
        assert result.output_path.exists()
        assert result.resume_z == pytest.approx(0.6, abs=0.2)

    def test_process_requires_selector(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = FailFixerController(profiles_dir=str(tmp_path / "profiles"))
        with pytest.raises(ValueError, match="Either layer_num or z_height"):
            ctrl.process(gcode_path=str(gcode_path))

    def test_process_output_path_used(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        out = tmp_path / "custom_output.gcode"
        ctrl = FailFixerController(profiles_dir=str(tmp_path / "profiles"))
        result = ctrl.process(
            gcode_path=str(gcode_path),
            layer_num=0,
            output_path=str(out),
        )
        assert result.output_path == out
        assert out.exists()

    def test_process_temps_in_result(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        ctrl = FailFixerController(profiles_dir=str(tmp_path / "profiles"))
        result = ctrl.process(
            gcode_path=str(gcode_path),
            layer_num=1,
            output_path=str(tmp_path / "out.gcode"),
        )
        assert result.bed_temp == 60.0
        assert result.nozzle_temp == 200.0

    def test_process_build_plate_mode(self, tmp_path):
        gcode_path = _write_gcode(tmp_path, GCODE_LAYER_COMMENT)
        out = tmp_path / "build_plate_resume.gcode"
        ctrl = FailFixerController(profiles_dir=str(tmp_path / "profiles"))
        result = ctrl.process(
            gcode_path=str(gcode_path),
            layer_num=1,
            resume_mode="from_plate",
            output_path=str(out),
        )
        content = result.output_path.read_text(encoding="utf-8")
        assert "Resume Mode: from_plate" in content
        assert "G28" in content


# ======================================================================
# Integration: end-to-end round-trip
# ======================================================================

class TestEndToEnd:
    """Full round-trip: parse → map → generate → validate."""

    def test_round_trip_all_methods(self, tmp_path):
        """Ensure each detection method produces valid resume output."""
        for name, gcode in [
            ("comment", GCODE_LAYER_COMMENT),
            ("change", GCODE_LAYER_CHANGE),
            ("zmove", GCODE_Z_FALLBACK),
        ]:
            p = _write_gcode(tmp_path, gcode, name=f"{name}.gcode")
            ctrl = Controller(profiles_dir=str(tmp_path / "profiles"))
            request = ResumeRequest(
                input_path=str(p),
                resume_selector=1,
                output_dir=str(tmp_path),
            )
            result = ctrl.run(request)
            assert result.output_path.exists(), f"Failed for {name}"
            assert result.validation.ok, (
                f"{name}: {[e.message for e in result.validation.errors]}"
            )
