# Trace UI

Trace UI is a Python application for capturing, replaying, and post-processing Android graphics traces. It supports both the Qt GUI and a non-GUI CLI flow.

## Purpose

* Make tracing on Android faster, easier, and more reliable.
* Standardize trace generation and replay workflows.
* Support both interactive GUI use and scriptable CLI use.

## Installation

Requirements:

* Python 3.6 or newer.
* `adb` in `PATH` for Android capture and replay commands.
* A connected Android device for capture and replay flows.

```bash
git clone ...
cd traceui
pip install pandas pyside6==6.7.0
```

If you are not using a virtual environment, run the install command with `sudo -H`.

To run fast-forward verification, ensure ImageMagick is installed:

```bash
apt install imagemagick
```

## Running The GUI

Linux:

```bash
./run.sh [--loglevel debug|info|warning|error|critical]
```

This checks for updates and then launches the GUI.

Use `./run.sh` for normal use and `python traceui.py` for local development.

For local development without the updater:

```bash
python traceui.py
```

## Running The CLI

Install the repository into your current environment in editable mode:

```bash
python -m pip install -e .
```

This installs the `traceui_cli` console script into the active environment. After that, the CLI entry point is:

```bash
traceui_cli
```

### Capture Commands

List installed Android packages:

```bash
traceui_cli capture list-packages
traceui_cli capture list-packages --device <serial>
```

Generate a sample config file:

```bash
traceui_cli capture sample-config
traceui_cli capture sample-config -o config.json
```

See [Capture/Replay Config File](#capturereplay-config-file) for the sample config structure and field meanings.

Trace capture:

```bash
traceui_cli capture setup \
  --plugin gfxr \
  --app com.example.game \
  -c config.json \
  --launch-app \
  --loglevel debug
```

Notes:

* `--plugin` is required for `capture setup` and must be `gfxr` or `patrace`.
* `gfxr` captures produce `.gfxr` trace files and `patrace` captures produce `.pat` trace files.
* `--app` accepts either the exact package name or a resolvable app name.
* `--launch-app` launches the app after trace setup completes.
* `-c` and `--config` are equivalent. If omitted, the plugin uses its current defaults.
* `capture setup` writes a capture session state JSON file that `capture stop` uses to recover the selected plugin, device, target app, and plugin-specific capture state.
* By default, the session state file is written to `tmp/traceui_cli_capture_session.json`.
* `--state-file` is optional and mainly useful for keeping separate capture sessions, for example when tracing on multiple devices in parallel.
* `capture stop` uses the stored session state and does not take `--plugin`.
* `capture stop` removes the session state file after a successful trace pull.

Stop capture and pull the trace:

```bash
traceui_cli capture stop
traceui_cli capture stop --app com.example.game
traceui_cli capture stop --pull-to tmp/output_traces
```

### Replay Command

Replay a local trace:

```bash
traceui_cli replay \
  tmp/example.gfxr \
  -c config.json \
  --screenshots \
  -o tmp/replay-output \
  --loglevel info
```

Notes:

* The trace path is a required positional argument.
* The replay plugin is resolved automatically from the trace suffix.
* `-c` and `--config` are equivalent and are used to apply config-driven device path overrides before replay starts.
* `devicepaths.replay` from the config controls where the trace is pushed on the Android device.
* `--screenshots` enables screenshot capture during replay.
* `--interval` is optional. When omitted, the screenshot interval defaults to `10`.
* Setting `--interval` to `0` disables screenshot capture.
* `-o` and `--outdir` are equivalent.

### Fastforward Command

Generate a fast-forwarded trace from a local source trace:

```bash
traceui_cli fastforward \
  tmp/example.gfxr \
  -sf 1550 \
  -c config.json \
  -o tmp/fastforward-output \
  --loglevel info
```

Notes:

* `--plugin` defaults to `auto`; if you override it, use `gfxr` or `patrace`.
* The trace path is a required positional argument.
* `-c` and `--config` are equivalent and are used to apply config-driven device path overrides before fast-forward generation starts.
* `-sf` and `--start-frame` are equivalent and required.
* `-ef` and `--end-frame` are equivalent and optional. If omitted, the generated fast-forward trace runs to the end of the source trace.
* `-o` and `--outdir` are equivalent.
* The CLI fastforward command currently generates and pulls the fast-forward trace; screenshot/HWC verification remains GUI-only.

### Capture/Replay Config File

The CLI sample config contains shared `devicepaths` and per-plugin config under `plugin`.

Example:

```json
{
  "devicepaths": {
    "layer": "/data/local/debug",
    "replay": "/sdcard/devlib-target",
    "capture": "/data"
  },
  "plugin": {
    "gfxreconstruct": {
      "setprops": {
        "debug.gfxrecon.page_guard_align_buffer_sizes": true,
        "debug.gfxrecon.page_guard_persistent_memory": true,
        "debug.gfxrecon.capture_file_timestamp": true,
        "debug.gfxrecon.capture_frames": ""
      },
      "custom_setprops": {
        "debug.example.extra_prop": "1"
      }
    },
    "patrace": {}
  }
}
```

Meaning:

* `devicepaths.layer`: base device path used for layer deployment.
* `devicepaths.replay`: device replay working directory.
* `devicepaths.capture`: base device capture directory.
* `plugin.gfxreconstruct.setprops`: built-in configurable GFXR trace setup properties.
* `plugin.gfxreconstruct.custom_setprops`: extra arbitrary setprops to apply during GFXR capture setup.
* `plugin.patrace`: currently supports shared `devicepaths` only.

For `gfxreconstruct`:

* Boolean entries in `setprops` enable or disable those built-in setprops.
* `debug.gfxrecon.capture_frames` is a string.
* An empty string for `debug.gfxrecon.capture_frames` means no frame filter.
* Legacy flat GFXR config with top-level `setprops` and `custom_setprops` is still accepted for compatibility.

## Logging

Logs are written to timestamped files under `logs/` in the repo root, for example `logs/traceui_YYYY-MM-DD_HH-MM-SS.log`.

`./run.sh`, `capture setup`, `replay`, and `fastforward` support:

```bash
--loglevel debug|info|warning|error|critical
```

## Outputs

Local outputs are written under `tmp/` by default unless a command-specific output path is provided.
