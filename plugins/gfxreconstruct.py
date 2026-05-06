#!/usr/bin/python3

import os
import subprocess
import time
import json
from pathlib import Path
import hashlib
import adblib
from adblib import print_codes

from core.config import ConfigSettings, DEFAULT_DEVICE_LAYER_BASE

from core.logger_config import setup_logger

logger = setup_logger("gfxreconstruct")
##########################################################################
#
# Tracetool plugin for gfx reconstruct
#
##########################################################################


class tracetool(object):
    TRACE_SETUP_CONFIG_SECTION = "GFXR"
    TRACE_SETUP_CONFIG_KEY = "trace_setup_setprops"
    TRACE_SETUP_SETPROPS_DEFAULTS = [
        {
            "prop": "debug.gfxrecon.page_guard_align_buffer_sizes",
            "value": "true",
            "enabled": True,
            "label": "Align buffer sizes with page-guard boundaries",
        },
        {
            "prop": "debug.gfxrecon.page_guard_persistent_memory",
            "value": "true",
            "enabled": True,
            "label": "Enable page-guard for persistent memory",
        },
        {
            "prop": "debug.gfxrecon.capture_file_timestamp",
            "value": "false",
            "enabled": True,
            "label": "Disable timestamp suffix in capture filename",
        },
        {
            "prop": "debug.gfxrecon.capture_frames",
            "value": "",
            "enabled": True,
            "ui_type": "text",
            "label": "Capture all frames (empty frame filter)",
        },
    ]

    def __init__(self, adb):
        self.adb = adb
        self.config = ConfigSettings()
        self.plugin_name = 'gfxreconstruct'
        self.extra_args = ['--remove-unsupported']
        self.suffix = 'gfxr'
        self.full_name = 'Official release of gfxreconstruct'
        self.variant = 'internal'
        self.version = 'latest'
        self.dirname = 'android'
        self.tracelib = {
            'arm64-v8a': 'layer/arm64-v8a/libVkLayer_gfxreconstruct.so',
            'armeabi-v7a': 'layer/armeabi-v7a/libVkLayer_gfxreconstruct.so'
        }
        self.replayer = {
            'script': Path('gfxrecon.py'),
            'apk': Path('replay-release.apk'),
            'optimizer': Path('x64/gfxrecon-optimize'),
            'name': 'com.lunarg.gfxreconstruct.replay'
        }
        self.basepath = Path('artifacts/gfxreconstruct-arm')
        self.base = None
        paths_cfg = self.config.get_config().get('Paths', {})
        workdir = paths_cfg.get('replay_working_dir', '/sdcard/devlib-target')
        capture_base = paths_cfg.get('capture_root_base', '/data')
        self.sdcard_working_dir = Path(workdir)
        self.capture_root_dir = Path(capture_base) / "gfxr"
        self.capture_file_fullpath = None
        self.capture_file_name = None
        self.device_layer_debug_root = Path(DEFAULT_DEVICE_LAYER_BASE) / "vulkan"
        self.trace_setup_setprops = [dict(item) for item in self.TRACE_SETUP_SETPROPS_DEFAULTS]
        self.trace_setup_custom_setprops = []
        self._load_trace_setup_config()

    def get_trace_setup_setprops(self):
        """
        Return default configurable setprop entries used in trace_setup_device.
        """
        return [dict(item) for item in self.trace_setup_setprops]

    def get_trace_setup_custom_setprops(self):
        """
        Return custom setprop entries used in trace_setup_device.
        """
        return [dict(item) for item in self.trace_setup_custom_setprops]

    def add_trace_setup_custom_setprop(self, prop, value):
        """
        Add or update a custom setprop entry used in trace setup.
        """
        prop = str(prop).strip()
        value = str(value).strip()
        if not prop:
            raise ValueError("Setprop name cannot be empty.")

        existing_item = self._find_trace_setup_setprop(prop)
        if existing_item:
            existing_item["value"] = value
            existing_item["enabled"] = True
            self._save_trace_setup_config()
            return False

        self.trace_setup_custom_setprops.append({
            "prop": prop,
            "value": value,
            "enabled": True,
            "custom": True,
            "label": prop,
            "ui_type": "text",
        })
        self._save_trace_setup_config()
        return True

    def remove_trace_setup_custom_setprop(self, prop):
        """
        Remove one custom setprop by property name.
        """
        prop = str(prop).strip()
        for idx, item in enumerate(self.trace_setup_custom_setprops):
            if item.get("prop") == prop:
                del self.trace_setup_custom_setprops[idx]
                self._save_trace_setup_config()
                return True
        return False

    def clear_trace_setup_custom_setprops(self):
        """
        Remove all custom setprops.
        """
        self.trace_setup_custom_setprops = []
        self._save_trace_setup_config()

    def reset_trace_setup_setprops_to_defaults(self):
        """
        Reset all trace setup setprops to defaults and clear custom entries.
        """
        self.trace_setup_setprops = [dict(item) for item in self.TRACE_SETUP_SETPROPS_DEFAULTS]
        self.trace_setup_custom_setprops = []
        self._save_trace_setup_config()

    def set_trace_setup_setprop_enabled(self, prop, enabled):
        """
        Enable/disable a specific setprop in trace setup.
        """
        item = self._find_trace_setup_setprop(prop)
        if item:
            item["enabled"] = bool(enabled)
            self._save_trace_setup_config()
            return
        logger.warning(f"Unknown gfxreconstruct trace setprop option: {prop}")

    def set_trace_setup_setprop_value(self, prop, value):
        """
        Update the value of a specific setprop in trace setup.
        """
        item = self._find_trace_setup_setprop(prop)
        if item:
            item["value"] = value
            self._save_trace_setup_config()
            return
        logger.warning(f"Unknown gfxreconstruct trace setprop value option: {prop}")

    def _is_trace_setup_setprop_enabled(self, prop):
        item = self._find_trace_setup_setprop(prop)
        if item:
            return item.get("enabled", True)
        return False

    def _iter_trace_setup_setprops(self):
        for item in self.trace_setup_setprops:
            yield item
        for item in self.trace_setup_custom_setprops:
            yield item

    def _find_trace_setup_setprop(self, prop):
        for item in self._iter_trace_setup_setprops():
            if item["prop"] == prop:
                return item
        return None

    def _load_trace_setup_config(self):
        raw_config = self.config.get_value(
            self.TRACE_SETUP_CONFIG_SECTION,
            self.TRACE_SETUP_CONFIG_KEY,
            fallback=""
        )
        if not raw_config:
            return
        try:
            persisted = json.loads(raw_config)
        except Exception as exc:
            logger.warning(f"Failed to parse persisted GFXR setprops config: {exc}")
            return

        default_overrides = persisted.get("defaults", {})
        for item in self.trace_setup_setprops:
            override = default_overrides.get(item["prop"])
            if not isinstance(override, dict):
                continue
            if "enabled" in override:
                item["enabled"] = bool(override["enabled"])
            if "value" in override:
                item["value"] = str(override["value"])

        custom_items = persisted.get("custom", [])
        if not isinstance(custom_items, list):
            custom_items = []
        for custom_item in custom_items:
            if not isinstance(custom_item, dict):
                continue
            prop = str(custom_item.get("prop", "")).strip()
            if not prop:
                continue
            value = str(custom_item.get("value", "")).strip()
            enabled = bool(custom_item.get("enabled", True))
            if self._find_trace_setup_setprop(prop):
                # If persisted custom collides with defaults, treat it as an override.
                self.set_trace_setup_setprop_value(prop, value)
                self.set_trace_setup_setprop_enabled(prop, enabled)
                continue
            self.trace_setup_custom_setprops.append({
                "prop": prop,
                "value": value,
                "enabled": enabled,
                "custom": True,
                "label": prop,
                "ui_type": "text",
            })

    def _save_trace_setup_config(self):
        config_payload = {
            "defaults": {},
            "custom": [],
        }
        for item in self.trace_setup_setprops:
            config_payload["defaults"][item["prop"]] = {
                "enabled": bool(item.get("enabled", True)),
                "value": str(item.get("value", "")),
            }
        for item in self.trace_setup_custom_setprops:
            config_payload["custom"].append({
                "prop": item.get("prop", ""),
                "value": str(item.get("value", "")),
                "enabled": bool(item.get("enabled", True)),
            })
        self.config.update_config(
            self.TRACE_SETUP_CONFIG_SECTION,
            self.TRACE_SETUP_CONFIG_KEY,
            json.dumps(config_payload, separators=(",", ":"))
        )

    def uptodate(self):
        """
        Checks if gfxr is up to date.

        Returns:
            bool: If gfxr is up to date
        """
        if not (self.base / self.replayer["apk"]).exists():
            return False
        for k, v in self.tracelib.items():
            if not (self.base / v).exists():
                return False

        return self.basepath.exists() and self.base.exists()

    # Tracing commands

    def trace_setup_device(self, app):
        """
        Sets up the device for tracing.

        Args:
            app (str): App package name, e.g. com.example.myapp
        """
        assert self.adb.device, 'No device selected'

        # chack that the package/app exists
        device_layer_path = self.__get_device_package_layer_path(app)

        self.adb.command(['setenforce', '0'], True)
        self.adb.command(['settings', 'put', 'global',
                         'enable_gpu_debug_layers', '1'])
        self.adb.command(['settings', 'put', 'global', 'gpu_debug_app', app])
        self.adb.command(
            ['settings', 'put', 'global', 'gpu_debug_layers',
             'VK_LAYER_LUNARG_gfxreconstruct'])
        for setprop_item in self._iter_trace_setup_setprops():
            if not setprop_item.get("enabled", True):
                continue
            self.adb.setprop(setprop_item["prop"], setprop_item["value"])
        # TODO: Update the capture_file_name when capture_frames is set

        self.adb.command(['mkdir', '-p', self.capture_root_dir], True)
        self.adb.command(['chmod', 'o+rw', self.capture_root_dir], True)
        self.adb.command(['chcon', 'u:object_r:app_data_file:s0:c512,c768', self.capture_root_dir], True)
        self.capture_file_name = self.__generate_trace_name(app)
        self.capture_file_fullpath = self.capture_root_dir / self.capture_file_name
        self.adb.setprop('debug.gfxrecon.capture_file', self.capture_file_fullpath)
        logger.info(
            f"GFXReconstruct output trace file to: {self.capture_file_fullpath}")
        self.adb.delete_file(self.capture_file_fullpath)

        # causes corruptions for UE
        #self.adb.setprop('debug.gfxrecon.page_guard_separate_read', 'false')

        # Retrieve the app "layer path" to put the capture layer in
        device_layer_path_so = device_layer_path / 'libVkLayer_gfxreconstruct.so'

        # Find the layer path

        adb_config_abi = self.adb.configs[self.adb.device]['abi']

        if len(adb_config_abi.split(",")) == 0:
            layer_path = os.getcwd() / self.basepath / self.dirname / adb_config_abi
        elif "arm64-v8a" in adb_config_abi:
            layer_path = os.getcwd(
            ) / self.basepath / self.dirname / self.tracelib["arm64-v8a"]
        else:
            layer_path = os.getcwd(
            ) / self.basepath / self.dirname / adb_config_abi.split(',')[0]
        # Ensure layer exists in local path
        if not layer_path.exists():
            logger.error("Trace layer not found on local device")
            raise Exception(f"Layer not found in {layer_path}")
            # TODO return to previous page and inform user

        # Put the layer at the right package/app
        self.adb.delete_file(device_layer_path_so)
        logger.debug(f"Pushing layer: {layer_path} to {device_layer_path}")
        self.adb.push(str(layer_path), str(device_layer_path))
        # (If this fails try putting the layer at this location insted: /data/local/debug/vulkan)

        if not self.adb.command(['ls', device_layer_path], True):
            raise Exception(f"Layer not found in {device_layer_path}")

        self.adb.command([f'chmod 755 {device_layer_path_so}'], True)
        self.adb.command([f'chown system:system {device_layer_path_so}'], True)

    def trace_reset_device(self):
        """
        Resets the parameters set by tracing/replaying to their original value.
        """
        self.adb.command(['settings', 'delete', 'global',
                          'enable_gpu_debug_layers'])
        self.adb.command(['settings', 'delete', 'global', 'gpu_debug_app'])
        self.adb.command(['settings', 'delete', 'global', 'gpu_debug_layers'])

        # Remove all costom settings
        self.adb.intermediate_cleanup()

    # TODO
    def trace_parse_logcat(self, app):  # return None when done
        return ''

    def trace_setup_check(self, app):
        """
        Checks if tracing setup was set correctly.

        Args:
            app (str): App package name, e.g. com.example.myapp

        Returns:
            bool: True if application is runing and all the nessesary parameters/layers are set
        """
        result, _ = self.adb.command([f"ps -A | grep {app}"])
        stdout, _ = self.adb.command([f"pm list package -f | grep {app}"])

        layers_enabled, _ = self.adb.command(
            ['settings', 'get', 'global', 'enable_gpu_debug_layers'])
        app_in_debug_prop, _ = self.adb.command(
            ['settings', 'get', 'global', 'gpu_debug_app'])
        tracing_layers_enabled, _ = self.adb.command(
            ['settings', 'get', 'global', 'gpu_debug_layers'])
        align_buffer_sizes_enabled = self._is_trace_setup_setprop_enabled(
            'debug.gfxrecon.page_guard_align_buffer_sizes'
        )
        align_buffer_sizes_ok = True
        if align_buffer_sizes_enabled:
            align_buffer_sizes_ok = (
                self.adb.getprop('debug.gfxrecon.page_guard_align_buffer_sizes') == 'true'
            )
        if (layers_enabled == '1' and
            app_in_debug_prop == app and
            'VK_LAYER_LUNARG_gfxreconstruct' in tracing_layers_enabled and
                align_buffer_sizes_ok):
            return True

        return False

    def trace_stop(self, app):
        """
        Stops the application.

        Args:
            app (str): App package name, e.g. com.example.myapp

        Returns:
            Path: Path to trace on remote device
        """
        # Check if the app is running
        stdout, _ = self.adb.command([f"ps -A | grep {app}"])
        if app in stdout:
            self.adb.command([f'am force-stop {app}'], True)
            logger.debug(f"Stopped '{app}'")
        else:
            logger.debug(f"App ({app}) is already stopped")

        #Check for tracefile and rename it to _self.capture_file_name
        grep_string = f'{str(self.capture_file_fullpath).rsplit(".")[0]}*'
        stdout, _ = self.adb.command(['ls', grep_string], True)
        if stdout:
            logger.info(f"Found tracefile: {stdout}")
            if stdout != str(self.capture_file_fullpath):
                logger.info(f"Renaming tracefile: {stdout}, moving to {self.capture_file_fullpath}")
                self.adb.command(['mv', stdout, self.capture_file_fullpath])
            self.adb.command(['chmod', 'o+rw', self.capture_file_fullpath], True)
            self.adb.pull(self.capture_file_fullpath, 'tmp')
            optimized_trace = self.optimize_trace(f"tmp/{self.capture_file_name}")
            if optimized_trace is not None:
                self.adb.push(optimized_trace, self.sdcard_working_dir, device=None, track=False)
                self.capture_file_name = f'{Path(self.capture_file_name).stem}.optimized.gfxr'

        return self.sdcard_working_dir / self.capture_file_name

    def optimize_trace(self, trace):
        """
        Runs gfxrecon-optimize on the tracefile

        Args:
            trace (str): Path to trace

        Returns:
            Path: Path to trace on remote device
        """
        logger.info(f"Running optimizer on {trace}")
        optimized_trace = f"tmp/{Path(trace).stem}.optimized.gfxr"
        cmd = [str(self.basepath / self.replayer['optimizer']), trace, optimized_trace]
        subprocess.run(" ".join(cmd), shell=True, capture_output=True)
        if Path(optimized_trace).is_file(): # TODO Add more sophisticated error handling reading the output of the optimizer
            logger.info(f"Trace optimized {optimized_trace}")
            return optimized_trace
        else:
            logger.error(f"Trace: {trace} failed to optimize!")
            return None

    # Replay commands

    def replay_setup(self, device=None):
        """
        Sets up the device for trace replay.

        Args:
            device (str): Device name, if None adblib device will be used
        """
        apk_path = self.basepath / self.dirname / self.replayer['apk']
        # by only reinstalling the replayer we don't have to get permissions
        # manually again
        self.adb.install(apk_path, device)
        self.adb.manage_app_permissions(self.replayer['name'], device)
        # clear the logcat after setup
        self.adb.clear_logcat()

    def replay_start(self, file, screenshot=False, hwc=False,
                     repeat=1, device=None, extra_args=[], from_frame=None, to_frame="", interval=10):
        """
        Does replay from start to finish. Returns paths to the results.

        Args:
            file (str): Path on remothe to trace file
            screenshot (list[str]): Screenshots wanted when replaying. Should not be set as the same time as hwc
            hwc (bool): Replay with HWCPipe layer
            repeat (int): How many times to replay (mostly relewant for screenshots)
            device (str): Device name, if None adblib device will be used

        Returns:
            list: With paths to result files
        """
        if not device:
            device = self.adb.device
        assert device, 'No device selected'
        assert screenshot or repeat == 1, 'Repeat runs only make sense with screenshotting'
        assert not screenshot or not hwc, 'Do not use both hwc and screenshot at the same time'

        hwcpipe_layer_result_mask = "/sdcard/*_gpu_id_*_per_frame_counters.csv"
        if from_frame is None:
            from_frame = 1

        if hwc:
            # Delete existing hwc data as this can lead to dangerous mixups on replay failure
            # TODO: Remove this when we properly detect success/failure on
            # replay
            logger.warning(f"Removing any old HWCPipe results to avoid mixups. We should stop doing this when replay plugins detect failures in a robust manner.")
            self.adb.command(['setenforce', '0'], True)
            self.adb.command(
                ['rm', hwcpipe_layer_result_mask],
                True, None, True)

        for i in range(repeat):
            # Set correct parameters
            cmd = [
                f"ANDROID_SERIAL={self.adb.device}",
                'python',
                str(self.basepath / self.dirname / self.replayer['script']),
                'replay']

            if screenshot:
                screenshot_prefix = f'{Path(file).stem}_screenshot'
                device_opdir = self.sdcard_working_dir / f"{screenshot_prefix}"
                self.adb.command(['mkdir', '-p', device_opdir])
                cmd.extend([
                    '--screenshot-all',
                    '--screenshot-dir', str(device_opdir),
                    '--screenshot-prefix', screenshot_prefix,
                    '--screenshot-format', "png",
                ])
                # support added in r4p1. Uncomment line after release
                #TODO: Check if this is all needed for FF generation
                if screenshot == "specific_framerange":
                    cmd.remove("--screenshot-all")
                    cmd.extend([f'--screenshots {from_frame}-{to_frame}'])
                elif screenshot == "interval":
                    if interval == 0:
                        cmd.remove("--screenshot-all")
                    else:
                        cmd.extend(["--screenshot-interval", f"{interval}"])
                elif screenshot == "selecting_frames" and isinstance(from_frame, list):
                    from_frame.sort()
                    total_range = ",".join([f"{f + 1}" for f in from_frame])

                    cmd.remove("--screenshot-all")
                    cmd.extend([f'--screenshots {total_range}'])
                # replayer produces .bmp - should be converted to .png

            if to_frame:
                cmd.extend([f'--quit-after-frame {to_frame}'])

            if hwc:
                try:
                    self.__setup_hwcpipe_layer()
                except FileNotFoundError:
                    return None, None
            cmd.extend(['-m', 'rebind'] + extra_args + [str(file)])
        return cmd, file

    def replay_reset_device(self):
        """
        Reset the device after doing replay.
        """
        self.adb.command(['appops', 'reset', self.replayer['name']])
        self.trace_reset_device()

    def parse_logcat(self, mode=None, app=None):
        if mode is None and app is None:
            return []
        if mode == "replay":
            app = "gfxrecon"
        elif mode == "trace" and app is None:
            raise Exception("Application not specified for tracing")
        logcat = self.adb.fetch_logcat(device=None, filters="vulkan,gfxrecon")
        loglines = logcat.splitlines()
        err_lines = []
        extension_missing_lines = []

        for line in loglines:

            # Check for potential permission or filesystem issues
            if "E gfxrecon: fopen(" in line:
                estring = "WARNING: App may lack write permissions to output folder, check logcat/shell for more info.\n"
                if estring not in err_lines:
                    logger.error(f"Found: {line} in logcat, potential source of the error. App may lack write permissions to the output folder.")
                    err_lines.append(estring)

            if "W gfxrecon: Extension " in line:
                logger.warning(
                    f"Extension missing on replay device, replay may fail: {line}")
                extension_missing_lines.append(line)

            if "File did not contain any frames" in line:
                frame_error = (
                    "ERROR: gfxreconstruct reported no frames in the trace file "
                    "(\"File did not contain any frames\")."
                )
                if frame_error not in err_lines:
                    logger.error(f"Found no-frame trace error in logcat: {line}")
                    err_lines.append(frame_error)

            if "F gfxrecon: API call at index:" in line:
                if "VK_ERROR_EXTENSION_NOT_PRESENT" in line:
                    logger.error(f"API call failed on replay:{line}, due to missing extension. Potential culprits: {extension_missing_lines}")
                    err_lines.append(
                        f"ERROR: API call failed on replay:\n{line}, due to missing extension.\nPotential culprits: {extension_missing_lines}\n")
                else:
                    logger.error(
                        f"API call failed on replay: {line}")
                    err_lines.append(
                        f"ERROR: API call failed on replay:\n{line}\n")

        return err_lines

    # Private helper functions
    def __get_device_package_layer_path(self, app):
        """
        Gets the aplication layer path

        Args:
            app (str): App package name, e.g. com.example.myapp

        Return:
            Path: pathlib path to package layer path
        """
        device_pkg_path_root = self.adb.get_pkg_path(app)
        if not device_pkg_path_root:
            raise Exception(f"Unable obtain package information for: {app}")
        device_layer_path = Path(device_pkg_path_root) / "lib" / "arm64"
        testfile = f"{device_layer_path}/testfile.txt"
        stdout, _ = self.adb.command(['touch', testfile], run_with_sudo=True,  errors_handled_externally=True)
        if not stdout:
            logger.debug(f"Using debug directory instead")
            device_layer_path = self.device_layer_debug_root
            self.adb.command(['mkdir', '-p', device_layer_path], True)
        return device_layer_path

    def __setup_hwcpipe_layer(self):
        """
        Sets up the hwc layer for replaying.
        """
        expected_lib_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "artifacts/hwcpipe/android/libVkLayerHWCPipe.so"
        )
        if not os.path.exists(expected_lib_path):
            raise FileNotFoundError(f"HWC layer not found in {expected_lib_path}\nTry running update-artifacts.sh")

        device_layer_path = self.__get_device_package_layer_path(
            self.replayer['name'])
        logger.debug(
            f"Pushing layer {expected_lib_path} to {device_layer_path}")
        self.adb.push(str(expected_lib_path), str(device_layer_path))

        self.adb.command([f'chmod 755 {device_layer_path}'], True)
        self.adb.command([f'chown system:system {device_layer_path}'], True)

        stdout, _ = self.adb.command(['ls', device_layer_path], True)
        if not stdout:
            raise FileNotFoundError(f"Layer not found on device in {self.replayer['name']}")

        self.adb.command(['settings', 'put', 'global',
                         'enable_gpu_debug_layers', '1'])
        self.adb.command(
            ['settings', 'put', 'global', 'gpu_debug_layers',
             'VK_LAYER_VKL_HWCPIPE'])
        self.adb.command(['settings', 'put', 'global',
                         'gpu_debug_app', self.replayer['name']])

    def __generate_trace_name(self, app_name):
        """ creates a file name from package name and hash of current time
        """
        time_now = str(time.time()).encode()
        time_hash = hashlib.sha256(time_now).hexdigest()[:16]
        return f'{app_name.replace(".", "_")}_{time_hash}_capture.gfxr'


if __name__ == '__main__':
    a = adblib.adb()
    g = tracetool(a)
    print(
        '[ INFO ] Up to date: %s' %
        'True' if g.uptodate() else 'False (installing)')
    if not g.uptodate():
        print(
            '[ INFO ] Up to date: %s' %
            'True (success)' if g.uptodate() else 'False (failed)')
