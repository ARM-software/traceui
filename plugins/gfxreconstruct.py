#!/usr/bin/python3

import os
import subprocess
import time
from pathlib import Path
import hashlib
import adblib
from adblib import print_codes

from core.config import ConfigSettings

##########################################################################
#
# Tracetool plugin for gfx reconstruct
#
##########################################################################


class tracetool(object):
    def __init__(self, adb):
        self.adb = adb
        self.config = ConfigSettings()
        self.plugin_name = 'gfxreconstruct'
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
        self.sdcard_working_dir = Path('/sdcard/devlib-target/')
        self.capture_root_dir = Path('/data/gfxr/')
        self.capture_file_fullpath = None
        self.capture_file_name = None
        self.device_layer_debug_root = Path("/data/local/debug/vulkan/")

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
        self.adb.setprop(
            'debug.gfxrecon.page_guard_align_buffer_sizes',
            'true')
        self.adb.setprop('debug.gfxrecon.page_guard_persistent_memory', 'true')
        self.adb.setprop('debug.gfxrecon.capture_file_timestamp', 'false')
        self.adb.setprop('debug.gfxrecon.capture_frames', "''")
        # TODO: Update the capture_file_name when capture_frames is set

        self.adb.command(['mkdir', '-p', self.capture_root_dir], True)
        self.adb.command(['chmod', 'o+rw', self.capture_root_dir], True)
        self.adb.command(['chcon', 'u:object_r:app_data_file:s0:c512,c768', self.capture_root_dir], True)
        self.capture_file_name = self.__generate_trace_name(app)
        self.capture_file_fullpath = self.capture_root_dir / self.capture_file_name
        self.adb.setprop('debug.gfxrecon.capture_file', self.capture_file_fullpath)
        print(
            f"[ INFO ] GFXReconstruct output trace file to: {self.capture_file_fullpath}")
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
            print("[ ERROR ] Trace layer not found on local device")
            raise Exception(f"Layer not found in {layer_path}")
            # TODO return to previous page and inform user

        # Put the layer at the right package/app
        self.adb.delete_file(device_layer_path_so)
        print(f"[ INFO ] Pushing layer: {layer_path} to {device_layer_path}")
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
        self.adb.cleanup()

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
        align_buffer_sizes_set = self.adb.getprop(
            'debug.gfxrecon.page_guard_align_buffer_sizes')
        if (layers_enabled == '1' and
            app_in_debug_prop == app and
            'VK_LAYER_LUNARG_gfxreconstruct' in tracing_layers_enabled and
                align_buffer_sizes_set == 'true'):
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
            print(f"[ INFO ] App ({app}) is already stopped")

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
        print(f"[ INFO ] Running optimizer on {trace}")
        optimized_trace = f"tmp/{Path(trace).stem}.optimized.gfxr"
        cmd = [str(self.basepath / self.replayer['optimizer']), trace, optimized_trace]
        subprocess.run(" ".join(cmd), shell=True, capture_output=True)
        if Path(optimized_trace).is_file(): # TODO Add more sophisticated error handling reading the output of the optimizer
            print(f"[ INFO ] Trace optimized {optimized_trace}")
            return optimized_trace
        else:
            print(f"[ ERROR ] Trace: {trace} failed to optimize!")
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
            print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Removing any old HWCPipe results to avoid mixups. We should stop doing this when replay plugins detect failures in a robust manner.")
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
                    print(f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] Found: {line} in logcat, potential source of the error. App may lack write permissions to the output folder.")
                    err_lines.append(estring)

            if "W gfxrecon: Extension " in line:
                print(
                    f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Extension missing on replay device, replay may fail: {line}")
                extension_missing_lines.append(line)

            if "F gfxrecon: API call at index:" in line:
                if "VK_ERROR_EXTENSION_NOT_PRESENT" in line:
                    print(f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] API call failed on replay:{line}, due to missing extension. Potential culprits: {extension_missing_lines}")
                    err_lines.append(
                        f"ERROR: API call failed on replay:\n{line}, due to missing extension.\nPotential culprits: {extension_missing_lines}\n")
                else:
                    print(
                        f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] API call failed on replay: {line}")
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
            print(f"[ {print_codes.SUCCESS}INFO{print_codes.END_CODE} ] Using debug directory instead")
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
        print(
            f"[ INFO ] Pushing layer {expected_lib_path} to {device_layer_path}")
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
