# FailFixer — Next Session TODO (Operator + Cursor)

Updated: 2026-02-28
Branch: `cursor-recovery`
Current app release build: `dist/FailFixer_v1.0.0.exe`

## Immediate priorities

1. **Create public release branch/tag for V1**
   - Branch/tag proposal: `release/v1.0.0`
   - Keep `cursor-recovery` as active beta branch.

2. **Validate V1 behavior on clean machine(s)**
   - Confirm UI defaults:
     - On-Plate selected by default
     - In-Air option greyed out/unselectable
   - Confirm output filename prefixes are enforced:
     - `On-Plate_...`
   - Confirm EXE icon displays correctly cross-machine.

3. **Bambu/Orca compatibility expansion (top priority)**
   - Collect real startup snippets in `startup_samples/bambu_orca/`
   - Add tests in `tests/test_core.py` for each marker/macro pattern found.
   - Track safe/unsafe startup lines in `STARTUP_COMPAT_MATRIX.md`.

4. **On-Plate quality hardening**
   - Run additional real printer tests with simple and complex models.
   - Capture first 150 lines of original + generated files for regressions.
   - Add tests for any discovered startup edge cases.

---

## Cursor-ready task queue

### Task A — Bambu startup corpus + tests
- Add at least 3 real startup snippets under `startup_samples/bambu_orca/`.
- Add parser/detect tests for each in `tests/test_core.py`.
- Keep changes small and test-backed.

### Task B — Startup normalizer scaffolding
- Introduce a lightweight classifier function for startup lines:
  - `safe_both`, `safe_on_plate_only`, `needs_neutralization`
- No big refactor; just scaffold + tests.

### Task C — Release hygiene
- Add `RELEASE_CHECKLIST.md` including:
  - version bump
  - py_compile
  - pytest
  - build output path
  - smoke test list

---

## Non-goals for public V1
- Do **not** re-enable In-Air UI in public build.
- Do **not** ship broad risky refactors without tests.

---

## Commands

```bash
python -m py_compile __init__.py app/controller.py ui/main_window.py
python -m pytest tests/test_core.py -q
build.bat
```

---

## Key references
- `PROJECT_STATUS.md` — full state/history/roadmap
- `STARTUP_COMPAT_MATRIX.md` — compatibility strategy
- `ARCHITECTURE.md` — module map
- `CURSOR_ZERO_START_ISSUE.md` — prior regression context
