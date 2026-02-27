"""Performance test: 50MB synthetic G-code file."""
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from failfixer.core.gcode_parser import GCodeParser
from failfixer.core.layer_mapper import LayerMapper
from failfixer.core.resume_generator import ResumeGenerator, ResumeConfig

def generate_large_gcode(target_mb: float = 50.0) -> str:
    """Generate a ~target_mb synthetic G-code file."""
    lines = []
    lines.append("; synthetic large file")
    lines.append("M140 S60")
    lines.append("M104 S210")
    lines.append("M190 S60")
    lines.append("M109 S210")
    lines.append("G21")
    lines.append("G90")
    lines.append("M82")
    lines.append("G28")
    lines.append("G92 E0")

    z = 0.2
    e = 0.0
    layer = 0
    target_bytes = int(target_mb * 1024 * 1024)
    total = 0

    while total < target_bytes:
        lines.append(f";LAYER:{layer}")
        lines.append(f"G1 Z{z:.3f} F600")
        total += 30
        # ~50 moves per layer
        for i in range(50):
            e += 0.5
            x = 50 + (i % 10) * 10
            y = 50 + (i // 10) * 10
            line = f"G1 X{x} Y{y} E{e:.3f} F1200"
            lines.append(line)
            total += len(line) + 1
        z += 0.2
        layer += 1

    return "\n".join(lines) + "\n"

def main():
    print("Generating ~50MB synthetic G-code...")
    t0 = time.perf_counter()
    text = generate_large_gcode(50.0)
    gen_time = time.perf_counter() - t0
    size_mb = len(text.encode()) / (1024 * 1024)
    print(f"  Generated {size_mb:.1f} MB in {gen_time:.2f}s")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "large.gcode"
        path.write_text(text, encoding="utf-8")
        del text  # free memory

        # Parse timing
        parser = GCodeParser()
        t0 = time.perf_counter()
        parsed = parser.parse_file(path)
        parse_time = time.perf_counter() - t0
        print(f"  Parsed in {parse_time:.2f}s ({len(parsed.lines)} lines, {len(parsed.layers)} layers)")
        assert parse_time < 3.0, f"Parse took {parse_time:.2f}s > 3s limit!"

        # Resume gen timing (from middle layer)
        mid = len(parsed.layers) // 2
        mapper = LayerMapper(parsed.layers)
        match = mapper.by_layer_number(mid)
        config = ResumeConfig(
            resume_layer=mid,
            resume_z=match.layer.z_height,
            bed_temp=parsed.state.bed_temp,
            nozzle_temp=parsed.state.nozzle_temp,
        )
        gen = ResumeGenerator()
        t0 = time.perf_counter()
        lines = gen.generate(parsed, match, config)
        resume_time = time.perf_counter() - t0
        print(f"  Resume gen in {resume_time:.2f}s ({len(lines)} output lines)")
        assert resume_time < 1.0, f"Resume gen took {resume_time:.2f}s > 1s limit!"

    print("Performance test PASSED!")

if __name__ == "__main__":
    main()
