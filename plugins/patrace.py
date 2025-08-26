#!/usr/bin/python3

import time
import os
import json
from pathlib import Path

import adblib
from adblib import print_codes


class tracetool(object):
    def __init__(self, adb):
        self.adb = adb
        self.plugin_name = 'patrace'
        self.suffix = 'pat'
        self.full_name = 'Official release of patrace'
        self.variant = 'scratch'
        self.dirname = 'android'
        self.tracelib = {'arm64-v8a': 'gleslayer/libGLES_layer_arm64.so', 'armeabi-v7a': 'gleslayer/libGLES_layer_arm.so'}
        self.replayer = {
            'script': Path(''),
            'apk': Path('eglretrace/eglretrace-release.apk'),
            'name': 'com.arm.pa.paretrace'
        }
        self.basepath = Path('artifacts/patrace')
        self.base = self.basepath / self.dirname
        self.sdcard_working_dir = Path('/sdcard/devlib-target/')
        self.capture_app_dir = None
        self.capture_file_fullpath = None
        self.capture_root_dir = Path('/data/apitrace/')
        self.device_layer_root = Path("/data/local/debug/gles/")
        self.layer_filename = 'libGLES_layer_arm64.so'

    def uptodate(self):
        pass

    # Tracing commands

    def trace_setup_device(self, app):
        """
        Sets up the device for tracing.

        Args:
            app (str): App package name, e.g. com.example.myapp
        """
        assert self.adb.device, 'No device selected'
        # Check and cleanup previous caputre file
        self.capture_app_dir = self.capture_root_dir / app
        self.adb.command(['mkdir', '-p', self.capture_app_dir], True)
        self.adb.command(['chmod', 'o+rw', self.capture_app_dir], True)
        self.adb.command(['chcon', 'u:object_r:app_data_file:s0:c512,c768', self.capture_app_dir], True)
        self.capture_file_fullpath = self.capture_root_dir / app / (app + ".1.pat")
        self.adb.delete_file(self.capture_file_fullpath)

        # Retrieve the app "layer path" to put the capture layer in
        device_layer_root_so = self.device_layer_root / self.layer_filename
        # Find the layer path
        adb_config_abi = self.adb.configs[self.adb.device]['abi']
        if len(adb_config_abi.split(",")) == 0:
            layer_path = os.getcwd() / self.basepath / self.dirname / adb_config_abi
        elif "arm64-v8a" in adb_config_abi:
            layer_path = os.getcwd() / self.basepath / self.dirname / self.tracelib["arm64-v8a"]
        else:
            layer_path = os.getcwd() / self.basepath / self.dirname / adb_config_abi.split(',')[0]
        # Ensure layer exists in local path
        if not layer_path.exists():
            print(f"[ ERROR ] Trace layer not found on local device")
            raise Exception(f"Layer not found in {layer_path}")

        # Put the layer on device
        self.adb.command(['mkdir', '-p', self.device_layer_root], True)
        print(f"[ INFO ] Pushing layer: {layer_path} to {self.device_layer_root}")
        self.adb.push(str(layer_path), str(self.device_layer_root))
        if not self.adb.command(['ls', self.device_layer_root], True):
            raise Exception(f"Layer not found in {self.device_layer_root}")
        self.adb.command([f'chmod 777 {device_layer_root_so}'], True)
        self.adb.command([f'chown system:system {device_layer_root_so}'], True)

        # setup patrace
        self.adb.command(['setenforce', '0'], True)
        self.adb.command(['settings', 'put', 'global', 'enable_gpu_debug_layers', '1'])
        self.adb.command(['settings', 'put', 'global', 'gpu_debug_app', app])
        self.adb.command(['settings', 'put', 'global', 'gpu_debug_layers_gles', self.layer_filename])

    def trace_reset_device(self):
        """
        Resets the parameters set by tracing/replaying to their original value.
        """
        self.adb.command(['settings', 'delete', 'global', 'enable_gpu_debug_layers'])
        self.adb.command(['settings', 'delete', 'global', 'gpu_debug_app'])
        self.adb.command(['settings', 'delete', 'global', 'gpu_debug_layers_gles'])

        # Remove all custom settings
        self.adb.cleanup()

    def trace_parse_logcat(self, app):
        return []


    def trace_setup_check(self, app):
        """
        Checks if tracing setup was set correctly.

        Args:
            app (str): App package name, e.g. com.example.myapp

        Returns:
            bool: True if application is runing and all the nessesary parameters/layers are set
        """
        result, _ = self.adb.command([f"ps -A | grep {app}"])
        device_layer_path = self.device_layer_root / self.layer_filename
        layer_found, _ = self.adb.command([f"if [ -f {device_layer_path} ]; then echo true; else echo false; fi"])
        layers_enabled, _ = self.adb.command(['settings', 'get', 'global', 'enable_gpu_debug_layers'])
        app_in_debug_prop, _ = self.adb.command(['settings', 'get', 'global', 'gpu_debug_app'])
        tracing_layers_enabled, _ = self.adb.command(['settings', 'get', 'global', 'gpu_debug_layers_gles'])
        if ((app in result) and
            layer_found == 'true' and
            layers_enabled == '1' and
            app_in_debug_prop == app and
                self.layer_filename in tracing_layers_enabled):
            print(f"[ INFO ] Attempted tracing for:  '{app}'")
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
            print(f"[ INFO ] Stopped '{app}'")
        else:
            print(f"[ INFO ] App ({app}) is not running")

        self.adb.command(['chmod', 'o+rw', self.capture_file_fullpath], True)
        return self.capture_file_fullpath

    def replay_setup(self, device=None):
        """
        Sets up the device for trace replay.

        Args:
            device (str): Device name, if None adblib device will be used
        """
        apk_path = self.basepath / self.dirname / self.replayer['apk']
        self.adb.install(apk_path, device)  # by only reinstalling the replayer we don't have to get permissions manually again
        self.adb.manage_app_permissions(self.replayer['name'], device)
        # clear the logcat after setup

    def replay_start(self, file, screenshot=False, hwc=False, repeat=1, device=None, extra_args=[], from_frame=None, to_frame=""):
        json_data = {}
        json_data["file"] = str(file)
        if from_frame is None:
            from_frame = 0

        # TODO make cleanup functions more efficient and run after frame selection/fastforwarding
        if hwc:
            hwcpipe_layer_result_mask = self.sdcard_working_dir / "*_gpu_id_*_per_frame_counters.csv"
            # Delete existing hwc data as this can lead to dangerous mixups on replay failure
            # TODO: Remove this when we properly detect success/failure on
            # replay
            print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Removing any old HWCPipe results to avoid mixups. We should stop doing this when replay plugins detect failures in a robust manner.")
            self.adb.command(
                ['rm', hwcpipe_layer_result_mask],
                True, None, True)

            json_data["perfmon"] = True
            json_data["perfmonout"] = f"{self.sdcard_working_dir}/"

        if screenshot:
            dir_prefix = f'{Path(file).stem}_screenshot'
            sdcard_dir = self.sdcard_working_dir / dir_prefix
            screenshot_prefix = f'{dir_prefix}_frame_'
            self.adb.command(['mkdir', '-p', sdcard_dir])
            json_data["snapshotCallset"] = "frame/*/10"
            json_data["snapshotPrefix"] = f"{sdcard_dir}/{screenshot_prefix}"
            json_data["snapshotFrameNames"] = True
            if screenshot == "fastforward":
                json_data["snapshotCallset"] = f"frame/{from_frame}-{to_frame}/1"
            elif screenshot == "all":
                json_data["snapshotCallset"] = "frame/*/1"
            if screenshot == "selecting_frames" and isinstance(from_frame, list):
                json_data["snapshotCallset"] = ",".join([f"frame/{f}/1" for f in from_frame])

        if repeat != 1:
            assert repeat > 1, 'Repeate cannot be less than one'
            json_data["loopTimes"] = repeat

        cmd = [
            'am', 'start',
            '-n', f'{self.replayer["name"]}/.Activities.RetraceActivity',
            '--es', 'jsonData', f'{self.sdcard_working_dir}/replay_args.json',
        ]
        cmd.extend(extra_args)

        return cmd, json_data

    def replay_reset_device(self):
        self.trace_reset_device()

    def parse_logcat(self, mode=None, app=None):  # return None when done
        filter = "patrace"
        if mode is None and app is None:
            return []
        if mode == "replay":
            app = "paretrace"
            filter = "paretrace64"
        if mode == "trace" and app is None:
            raise Exception("Application not specified for tracing")
        logcat = self.adb.fetch_logcat(device=None, filters=filter)
        loglines = logcat.splitlines()

        err_lines = []
        found_app = False

        for line in loglines:
            if app in line:
                found_app = True

            # Check for potential permission or filesystem issues
            if "Warning:" in line:
                print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] {line}")
                err_lines.append(line)

            if "Never rendered anything" in line:
                print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Unusable tracefile: {line}")
                err_lines.append(line)

            if "Failed to open" in line and "output JSON" not in line:
                print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] File not accessible : {line}")
                err_lines.append(line)

        if not found_app:
            print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Found no mention of the target app: {app} in the logcat output, app may not have been started.")
            err_lines.append(f"WARNING: Found no mention of the target app: {app} in the logcat output, app may not have been started.\n")

        return err_lines


if __name__ == '__main__':
    a = adblib.adb()
    g = tracetool(a)
    print('Up to date: %s' % 'True' if g.uptodate() else 'False (installing)')
    if not g.uptodate():
        print('Up to date: %s' % 'True (success)' if g.uptodate() else 'False (failed)')
