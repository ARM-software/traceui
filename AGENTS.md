# Repository Guidelines

## Project Structure & Module Organization
- `traceui.py`: Application entry point; loads plugins then launches the Qt UI in `gui.py`.
- `core/`: Core logic (`adb_thread.py`, navigation, config) plus `core/widgets/` for the stacked UI pages used across tracing, replay, and fast-forward flows.
- `plugins/`: Tool implementations (`fastforward.py`, `gfxreconstruct.py`, `patrace.py`) following the interface documented in `plugins/plugins_interface.md`.
- `artifacts/`: Bundled toolchains unpacked by `update-artifacts.sh`; `config.ini` points to these paths. Runtime outputs are written under `tmp/`.
- `data/` and `external/`: Reserved for assets or external bundles when needed.

## Build, Test, and Development Commands
- `pip install pandas pyside6==6.2.4` (optionally inside a virtualenv) plus ImageMagick for fast-forward verification.
- `./run.sh`: Pulls latest changes (if the working tree is clean), updates artifacts from the configured release, then launches the GUI. Do not run during development.
- `python traceui.py`: Start the app without auto-update; useful for local iteration or offline work.
- `./update-artifacts.sh`: Re-fetch and unpack tracing tool archives into `artifacts/`; requires network access and write permissions.

## Coding Style & Naming Conventions
- Python 3.6+ with PEP 8 defaults: 4-space indentation, descriptive class/method names, and docstrings for public surfaces.
- Qt widgets and signals live under `core/widgets`; keep signal names explicit (`*_signal`) and preserve existing page index ordering when adding steps.
- Keep plugin classes named `tracetool` and expose `plugin_name`/`full_name` attributes to integrate cleanly with `traceui.py`.

## Testing Guidelines
- No automated test suite is present; rely on manual verification by running the GUI and exercising connect then trace/import then replay/fast-forward flows.
- When modifying plugins, confirm device interactions (start/stop trace, replay paths) and verify artifacts land in `tmp/` as expected.

## Commit & Pull Request Guidelines
- Follow the existing history: concise, present-tense subjects (e.g., "Improve README.md and update-artifacts.sh"), optionally prefixed for small fixes.
- PRs should describe the user-visible change, list manual test steps (commands run, pages visited), and note any dependency or artifact updates.

## Security & Configuration Tips
- Keep `config.ini` paths updated if artifacts move; avoid committing device identifiers, logs, or temporary `tmp/` outputs.
