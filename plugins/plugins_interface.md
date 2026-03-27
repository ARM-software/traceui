# Plugins

Some documentation of the plugins:)

## Interface

This is to show what functions that is expected to be found in plugins to make it easier to implement new plugins:)

### tracetool

    class tracetool(object):
        #-- general functions ---
        def __init__(self, adb)     -> None
        def update(self)            -> None
        def uptodate(self)          -> ? and ?  # return self.basepath.exists() and self.base.exists()
        def load_capture_config(self, path)     -> None  # optional for CLI capture config support
        def get_capture_config_template(self)   -> dict  # optional for CLI sample-config support
        def export_capture_session_state(self)  -> dict  # optional for CLI capture stop support
        def import_capture_session_state(self, state) -> None  # optional for CLI capture stop support

        #-- Tracing commands --
        def trace_setup_device(self, app)       -> None
        def trace_reset_device(self)            -> None
        def trace_parse_logcat(self, app)       -> ? # return None when done
        def trace_find_output(self)             -> Path
        def trace_get_output(self, output_dir)  -> output path on computer
        def trace_start(self, app)              -> bool # Returns true if tracing has started (does not start the app)
        def trace_stop(self, app)               -> Path to trace on remote device  # app is expected to be package name, kills application from running

        #-- Replay commands --
        def replay_setup(self, device = None)       -> None
        def replay_start(self, file, screenshot=False, hwc=False, repeat=1, device = None) -> dict with paths to different results
        def replay_start_fastforward(self, file)    -> dict with paths to different results
        def replay_reset_device(self)               -> None

        #-- Tracing/Replay logcat parsing --
        def parse_logcat(self, mode=None, app=None)          -> ?  # return list of strings representing error and warning messages when done
