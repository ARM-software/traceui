# Trace UI

Trace UI is a Python application for capturing, replaying, and post-processing Android graphics traces. It supports both the Qt GUI and a non-GUI CLI flow.

## Purpose

* Make tracing on Android faster, easier, and more reliable.
* Standardize trace generation and replay workflows.
* Support both interactive GUI use and scriptable CLI use.

## Installation

Requires Python 3.6 or newer.

If running outside a virtual environment:

```bash
sudo -H pip install pandas pyside6==6.7.0
git clone ...
cd traceui
```

If using a virtual environment:

```bash
pip install pandas pyside6==6.7.0
git clone ...
cd traceui
```

To run fast-forward verification, ensure ImageMagick is installed:

```bash
apt install imagemagick
```

## Running The GUI

Linux:

```bash
./run.sh [--loglevel info|debug|warning|error]
```

This checks for updates and then launches the GUI.

For local development without the updater:

```bash
python traceui.py
```

## Running The CLI

The CLI entry point is:

```bash
python traceui_cli.py
```

### Capture Commands

List installed Android packages:

```bash
python traceui_cli.py capture list-packages
python traceui_cli.py capture list-packages --device <serial>
```

Generate a sample config file:

```bash
python traceui_cli.py capture sample-config
python traceui_cli.py capture sample-config -o config.json
```

Arm capture:

```bash
python traceui_cli.py capture setup \
  --plugin gfxreconstruct \
  --app com.example.game \
  -c config.json \
  --launch-app \
  --loglevel debug
```

Notes:

* `--plugin` is required for `capture setup` and must be `gfxreconstruct` or `patrace`.
* `--app` accepts either the exact package name or a resolvable app name.
* `--launch-app` launches the app after trace setup completes.
* `-c` and `--config` are equivalent. If omitted, the plugin uses its current defaults.
* `--loglevel` is supported on `capture setup` and accepts `debug`, `info`, `warning`, `error`, or `critical`.
* `capture stop` uses the stored session state and does not take `--plugin`.

Stop capture and pull the trace:

```bash
python traceui_cli.py capture stop
python traceui_cli.py capture stop --app com.example.game
python traceui_cli.py capture stop --pull-to tmp/output_traces
```

### Replay Command

Replay a local trace:

```bash
python traceui_cli.py replay \
  -t tmp/example.gfxr \
  -c config.json \
  --screenshots \
  --interval 10 \
  -o tmp/replay-output \
  --loglevel info
```

Notes:

* `--plugin` defaults to `auto` and is resolved from the trace suffix.
* `-t` and `--trace` are equivalent.
* `-c` and `--config` are equivalent and are used to apply config-driven device path overrides before replay starts.
* `devicepaths.replay` from the config controls where the trace is pushed on the Android device.
* `--screenshots` enables screenshot capture during replay.
* `--interval` controls screenshot interval when screenshots are enabled.
* `-o` and `--outdir` are equivalent.

## Capture/Replay Config File

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

Logs are written to `traceui.log` in the repo root.

CLI commands support:

```bash
--loglevel debug|info|warning|error|critical
```

## Outputs

Local outputs are written under `tmp/` by default unless a command-specific output path is provided.
