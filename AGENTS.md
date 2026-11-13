# Repository Guidelines

## Project Structure & Module Organization

- `videodl/` contains the upstream Python library and CLI; platform parsers live in `modules/sources/`, shared parsing services in `modules/common/`, and helpers in `modules/utils/`.
- `desktop/` implements the PySide6 application. UI code lives in `app.py`, `pages.py`, and `resultview.py`; parsing and download integration belongs in `adapter.py`, `parsing.py`, and the worker modules. Icons and screenshots are in `desktop/assets/`.
- `desktop/tests/` covers application behavior; `scripts/tests/` covers maintenance automation. `scripts/` and `.github/workflows/` handle synchronization and releases; `docs/` contains Sphinx documentation; `mcp/` provides a local MCP server.

## Build, Test, and Development Commands

Run these PowerShell commands from the repository root:

```powershell
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r desktop/requirements.txt pytest==9.1.1 pyinstaller==6.22.3
.\.venv\Scripts\python.exe -m desktop
.\.venv\Scripts\python.exe -m pytest desktop/tests -q
.\.venv\Scripts\python.exe -m unittest discover -s scripts/tests -v
.\.venv\Scripts\python.exe -m desktop.build
```

These create the environment, install pinned dependencies, launch the application, run both test suites, and build the Windows portable distribution. Source execution requires FFmpeg and ffprobe on `PATH`. Building requires Git, network access, and a fresh output directory; artifacts default to `dist/desktop/`. See `desktop/README.md` for details.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and uppercase constants. Follow neighboring code, including Qt's required method names such as `resizeEvent`. No repository-wide formatter or linter is configured. Keep desktop integration changes in `desktop/` where practical to simplify upstream synchronization. Regenerate pinned dependencies using the command recorded in `desktop/requirements.txt`.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions for desktop regressions; maintenance tests use `unittest`. Add focused regression coverage for changed behavior. Reuse temporary directories, mocks, and the local HTTP media fixture. Media integration tests skip without FFmpeg. No numeric coverage threshold is configured. For UI changes, verify the actual window; packaging changes also need packaged smoke validation.

## Commit & Pull Request Guidelines

Create `codex/<feature>` branches from `desktop` and target PRs at `desktop`. Follow recent scoped commits, such as `feat(desktop): ...`, `fix(ci): ...`, and `ci(desktop): ...`. Describe the problem, resulting behavior, related issues, and validation; include screenshots for visible UI changes. Follow `desktop/MAINTAINING.md` and `desktop/AUTOMATION.md`. Keep local downloads, `edit/`, `videodl_outputs/`, and build artifacts out of commits.
