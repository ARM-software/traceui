#!/usr/bin/python3

import subprocess
import time
import re
import os
import zipfile
import tempfile
import shutil
from core.logger_config import setup_logger

ADB = "adb"

# Detection strings
VULKAN_SYMBOLS = [b"vkCreateInstance", b"vkCreateDevice", b"libvulkan"]
GLES_SYMBOLS = [b"glGetString", b"glDrawElements", b"libGLES", b"libEGL"]
ENGINES = {
    "Unity": [b"libunity", b"UnityEngine"],
    "Unreal": [b"libUnreal", b"UnrealEngine", b"libUE4", b"Epic Games", b"UE4"],
    "Feral3D": [b"libferal3d", b"Feral3D", b"Feral Engine"],
    "Godot": [b"godot", b"libgodot"],
    "Cocos2d-x": [b"cocos2d"],
    "Mono/Xamarin": [b"mono", b"xamarin"],
}

logger = setup_logger("adblib")

class print_codes:
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    END_CODE = '\033[0m'


class adb(object):
    POTENTIAL_SUDO_COMMANDS = ["su -c", "su 0"]

    def __init__(self):
        self.device = None
        self.devices = []
        self.configs = {}  # above device name -> model name
        self.restore_props = {}
        self.restore_settings = {}
        self.added_files = []

    def manage_app_permissions(self, pkg_name=None, device=None):
        """
        Set package permissions.

        Args:
            pkg_name: pachkage name of apk to be installed.
            device (str): Device name, if None adblib device will be used
        """
        device = self.__check_device(device)
        self.command(['appops', 'set', pkg_name, 'android:legacy_storage', 'allow'])
        self.command(['appops', 'set', pkg_name, 'MANAGE_EXTERNAL_STORAGE', 'allow'])


    def delete_file(self, target_file):
        stdout, _ = self.command(['ls', target_file], True, errors_handled_externally=True)
        if stdout:
            if str(target_file) in stdout.splitlines():
                logger.warning(f"File with path: {target_file} already exists. Deleting.")
                self.command(['rm', '-f', target_file], True)

    def get_pkg_path(self, pkg):
        apk_path = self.__get_apk_path(pkg)
        if apk_path:
            return apk_path.rpartition("/")[0]
        return None

    def __get_apk_path(self, pkg):
        """Return path from package"""
        args = ["pm", "path", f"{pkg}"]
        output, _ = self.command(args)
        for pkg_path in output.split("\n"):
            if pkg_path.startswith("package:") and pkg_path.endswith("base.apk"):
                return pkg_path.split(":", 1)[1]
        return None

    def __extract_so_files(self, apk_file, extract_dir):
        """extract .so files from apk"""
        with zipfile.ZipFile(apk_file, 'r') as zipf:
            so_files = [f for f in zipf.namelist() if f.startswith("lib/") and f.endswith(".so")]
            extracted = []
            for so in so_files:
                dest_path = os.path.join(extract_dir, os.path.basename(so))
                with zipf.open(so) as src, open(dest_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                extracted.append(dest_path)
            return extracted

    def __analyze_so_file(self, so_path):
        """Checks *.so files against API and ENGINE symbols"""
        uses_vulkan = False
        uses_gles = False
        engine = None

        try:
            with open(so_path, "rb") as f:
                content = f.read()
                # Graphics API detection
                uses_vulkan = any(sig in content for sig in VULKAN_SYMBOLS)
                uses_gles = any(sig in content for sig in GLES_SYMBOLS)
                # Engine detection
                for eng, sigs in ENGINES.items():
                    if any(sig in content for sig in sigs):
                        engine = eng
                        break

        except Exception as e:
            logger.error(f"[!] Failed to read {so_path}: {e}")

        return uses_vulkan, uses_gles, engine

    def analyze_package(self, pkg):
        """Pulls package from device and API/ENGINE information from  *.so files """
        apk_path = self.__get_apk_path(pkg)
        self.command(["am", "kill-all"], run_with_sudo=True)
        self.command(["am", "force-stop", pkg], run_with_sudo=True)
        if not apk_path:
            return (pkg, None, None, None)

        with tempfile.TemporaryDirectory() as tempdir:
            apk_tmpdir = os.path.join(tempdir, f"{pkg}")
            self.pull(apk_path, apk_tmpdir)
            # One apk file is pulled
            apk_file = [os.path.join(apk_tmpdir, f) for f in os.listdir(apk_tmpdir) if os.path.isdir(apk_tmpdir)]
            if not apk_file:
                return (pkg, None, None, None)

            so_dir = os.path.join(tempdir, "so_files")
            os.makedirs(so_dir, exist_ok=True)
            so_files = self.__extract_so_files(apk_file[0], so_dir)

            uses_vulkan = False
            uses_gles = False
            engine = None

            for so in so_files:
                v, g, e = self.__analyze_so_file(so)
                uses_vulkan |= v
                uses_gles |= g
                if not engine and e:
                    engine = e

            return (pkg, uses_vulkan, uses_gles, engine)

    def command(self, args, run_with_sudo=False, device=None, errors_handled_externally=False, print_command=True):
        """Runs adb shell commands on device. Only returns the stdout of the results"""
        device = self.__check_device(device)
        cmd = ['adb', '-s', device, 'shell']

        if run_with_sudo:
            cmd += [self.configs[device]["working_sudo_command"]]

        cmd += args

        # To deal with pathlib
        cmd = [str(x) for x in cmd]

        if print_command:
            logger.debug("Running ADB command: " + " ".join(cmd))
        process = subprocess.run(cmd, capture_output=True, text=True)
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        if stderr:
            cmd_str = " ".join(cmd)
            if not errors_handled_externally:
                logger.error(f"Command {cmd_str} failed on device {device}, got error: {stderr}")

            else:
                emark = f"Error detected but marked as ok. "
                logger.info(f"{emark} Command {cmd_str} failed on device {device}, got error: {stderr}")
        return stdout, stderr

    def fetch_logcat(self, device=None, filters=None):
        device = self.__check_device(device)
        cmd = ['adb', '-s', device, 'logcat', '-d']
        if filters is not None:
            cmd += ['-s', filters]
        process = subprocess.run(cmd, capture_output=True, text=True)
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        if stderr:
            logger.error(f"Failed to fetch logcat from device {device}, got error: {stderr}")

        return stdout.strip()

    def clear_logcat(self, device=None):
        device = self.__check_device(device)
        cmd = ['adb', '-s', device, 'logcat', '-c']
        subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

    def run_command_get_logcat(self, args, run_with_sudo=False, device=None):
        self.clear_logcat(device)
        stdout, stderr = self.command(args, run_with_sudo, device)
        return stdout, stderr, self.fetch_logcat(device)

    def init(self):
        """Fills self variables"""
        only_unath = None
        self.devices = []
        cmd = ["adb", "devices"]
        subprocess.run(cmd, capture_output=True, text=True)  # first just to initialize adb if needed
        out = subprocess.run(cmd, capture_output=True, text=True)  # second to actually get device list
        for d in out.stdout.split('\n')[1:]:
            m = re.match(r'(\S+)\s+(\w+)', d)
            if not m:
                continue
            if m.group(2) == 'device':
                self.devices.append(m.group(1))
                only_unath = False
            if m.group(2) == 'unauthorized' and only_unath is None:
                only_unath = True
        if only_unath is True:
            logger.warning(f'You need to enable USB debug on your Android device or click to permit the connection!')
            return False
        if len(self.devices) == 0:
            logger.error(f'No devices found!')
            return False
        for d in self.devices:
            config = {}
            config["working_sudo_command"] = ""

            su_errs = []
            logger.debug("Sanity checking sudo command, selecting best candidate")
            for sudo_command in self.POTENTIAL_SUDO_COMMANDS:
                _, suerr = self.command([sudo_command, 'whoami'], False, d, True)
                if not suerr:
                    logger.debug(f"Found working sudo command {sudo_command}")
                    config["working_sudo_command"] = sudo_command
                    break
                else:
                    logger.warning(f"Sudo command {sudo_command} returned error {suerr}, trying alternatives.")
                    su_errs.append(suerr)

            if config["working_sudo_command"] is None:
                err_string = ", ".join(su_errs)
                logger.error(f"Unable to find a working sudo command for device, tried: {err_string}")

            config['model'] = self.getprop('ro.product.model', d)
            config['abi'] = self.getprop('ro.vendor.product.cpu.abilist', d)
            config['android'] = self.getprop('ro.vendor_dlkm.build.version.release', d)
            config['sdk'] = self.getprop('ro.vendor_dlkm.build.version.sdk', d)
            config['soc'] = self.getprop('ro.soc.model', d)
            config['manufacturer'] = self.getprop('ro.soc.manufacturer', d)
            config['angle'] = self.getprop('ro.gfx.angle.supported', d) == 'angle'
            config['skia'] = self.getprop('debug.renderengine.backend', d)
            config['gpu'] = self.getprop('ro.hardware.egl', d)
            root_stdout, _ = self.command([config["working_sudo_command"], 'whoami'], False, d)
            config['root'] = root_stdout == 'root'

            if not config['android']:
                config['android'] = config['android'] = self.getprop('ro.build.version.release', d)

                if not config['android']:
                    logger.warning(f"Failed to fetch android version from device properties. Force setting to 13. This should be fixed.")

            self.configs[d] = config
        if len(self.devices) == 1:
            self.select_device(self.devices[0])
        return self.devices

    def call(self, cmd, device=None):
        """Runs adb shell commands. Returns the full result"""
        device = self.__check_device(device)
        fullcmd = ['adb', '-s', device] + cmd
        out = subprocess.run(fullcmd, capture_output=True, text=True)
        return out

    def select_device(self, device):
        """Cleans up previous device beore setting new"""
        if self.device:
            self.cleanup(self.device)
        assert device in self.devices
        self.device = device

    def getprop(self, prop, device=None):
        """Runs adb sell getprop"""
        device = self.__check_device(device)
        stdout, stderr = self.command(['getprop', prop], False, device)
        return stdout

    def setprop(self, prop, value, device=None):
        """Runs adb setprop"""
        device = self.__check_device(device)
        if not prop in self.restore_props:
            self.restore_props[prop] = self.getprop(prop, device)
        self.command(['setprop', prop, value], False, device)

    # def setting(self, key, value): # TBD

    def cleanup(self, device=None, keepfiles=False):
        """Cleans up the device, resets all props set with the setprop function and deletes all tracked files"""
        self.intermediate_cleanup(device=device)
        if not keepfiles:
            for f in self.added_files:
                logger.debug(f"Cleaning up file: {f} on device")
                self.command(['rm', f], True, device)
            self.added_files = []

    def intermediate_cleanup(self, device=None):
        """Cleans up the device, resets all props set with the setprop function but does not delete any files"""
        device = self.__check_device(device)
        for n in list(self.restore_props.keys()):
            self.command(['setprop', n, self.restore_props[n]], False, device)
            del self.restore_props[n]

    def push(self, file, path, device=None, track=True, progress_callback=None, stop_event=None):
        """Pushes a file to the device"""
        device = self.__check_device(device)
        basename = os.path.basename(file)
        total_size = os.path.getsize(file)
        remote_temp_path = f"/sdcard/{basename}"
        logger.info(f"Pushing file from local path {file} to /sdcard/")
        self._emit_progress(progress_callback, 0, f"Preparing to push {basename}")

        push_cmd = ['adb', '-s', device, 'push', '-p', file, '/sdcard/']
        push_return = self._run_subprocess_with_progress(
            push_cmd,
            progress_callback,
            f"Pushing {basename} to /sdcard/",
            stop_event=stop_event,
            total_size=total_size,
            poll_path=remote_temp_path,
            poll_remote=True,
            device=device,
        )
        if push_return == "cancelled":
            logger.info(f"Push for {basename} cancelled by user")
            return False
        if push_return:
            logger.error(f"adb push failed for {basename} with return code {push_return}")
            return False

        self.command(['mkdir', '-p', path], True, device)  # make sure destination exists
        logger.debug(f"Moving file from device path /sdcard/ to device path {path}")
        self.command(['mv', '/sdcard/%s' % basename, path], True, device)
        file_path = str(path) + '/' + str(basename)

        self.command(['chmod', 'a+r', file_path], True, device)
        self._emit_progress(progress_callback, 95, f"Applying permissions to {file_path}")

        if track and file_path not in self.added_files:
            self.added_files.append(file_path)

        self._emit_progress(progress_callback, 100, f"Finished pushing {basename}")
        return True

    def pull(self, file, path, device=None, progress_callback=None, stop_event=None):
        """Pulls a file from the device (adb pull)"""
        device = self.__check_device(device)
        subprocess.run(['mkdir', '-p', path], capture_output=True, text=True).stdout.strip()
        logger.debug(f"Pulling file from device path {file} to local path {path}")
        self._emit_progress(progress_callback, 0, f"Preparing to pull {file}")
        total_size = None
        try:
            size_out, _ = self.command(['stat', '-c%s', file], device=device)
            total_size = int(size_out.strip())
        except Exception:
            total_size = None
        local_dest = os.path.join(path, os.path.basename(file))
        pull_cmd = ['adb', '-s', device, 'pull', '-p', file, path]
        pull_return = self._run_subprocess_with_progress(
            pull_cmd,
            progress_callback,
            f"Pulling {os.path.basename(file)} to {path}",
            stop_event=stop_event,
            total_size=total_size,
            poll_path=local_dest,
            poll_remote=False,
            device=device,
        )
        if pull_return == "cancelled":
            logger.info(f"Pull for {file} cancelled by user")
            return False
        if pull_return:
            logger.error(f"adb pull failed for {file} with return code {pull_return}")
            return False

        self._emit_progress(progress_callback, 100, f"Finished pulling {file}")
        return True

    def _emit_progress(self, callback, percent, message):
        """Emit progress updates for adb transfers."""
        if callback:
            callback(percent, message)

    def _run_subprocess_with_progress(self, cmd, progress_callback, description, stop_event=None, total_size=None, poll_path=None, poll_remote=False, device=None):
        """
        Execute a subprocess command, streaming percentage progress to callback when available.
        """
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        state = {
            "last_percent": 0,
            "last_emit_time": time.time(),
            "last_log_dump": time.time(),
        }
        heartbeat_interval = 1

        def _emit_percent(percent):
            if percent is None or percent == state["last_percent"]:
                return
            self._emit_progress(progress_callback, percent, f"{description} ({percent}%)")
            state["last_percent"] = percent
            state["last_emit_time"] = time.time()

        def _percent_from_poll():
            if not (total_size and poll_path):
                return None
            try:
                if poll_remote:
                    size_out, _ = self.command(['stat', '-c%s', poll_path], device=device, errors_handled_externally=True, print_command=False)
                    polled_size = int(size_out.strip()) if size_out else None
                else:
                    polled_size = os.path.getsize(poll_path) if os.path.exists(poll_path) else None
                if polled_size is None:
                    return None
                return int(min(100, max(1, polled_size * 100 / total_size)))
            except (OSError, ValueError) as e:
                logger.debug(f"Failed to poll transfer progress for {poll_path}: {e}")
                return None

        if progress_callback:
            _emit_percent(0)

        # Poll stdout without blocking so we can emit heartbeats regularly
        while process.poll() is None:
            if stop_event and stop_event.is_set():
                process.terminate()
                self._emit_progress(progress_callback, state["last_percent"], f"{description} (cancelled)")
                return "cancelled"

            if progress_callback and time.time() - state["last_emit_time"] >= heartbeat_interval:
                polled_percent = _percent_from_poll()
                _emit_percent(polled_percent)

        process.wait()
        return process.returncode

    def apps(self, all=False, device=None):
        """Returns a list of packages/apps"""
        packages = []
        device = self.__check_device(device)
        cmdlist = ['cmd', 'package', 'list', 'packages']
        if not all:
            cmdlist.append('-3')  # only thirdparty apps
        else:
            cmdlist.append('-e')  # only enabled apps
        out, _ = self.command(cmdlist)
        for d in out.split('\n'):
            m = re.match(r'package:(.+)', d)
            name = m.group(1)
            package = {}
            package['name'] = name
            info, _ = self.command(['dumpsys', 'package', name])
            for i in info.split('\n'):
                if 'primaryCpuAbi=' in i:
                    package['abi'] = i.split('=')[1]
                # elif 'versionCode=' in i: packages[name]['version'] = i.split('=')[1]
                elif 'versionName=' in i:
                    package['version'] = i.split('=')[1]
                elif 'resourcePath=' in i:
                    package['path'] = i.split('resourcePath=')[1]
            packages.append(package)
        return packages

    def install(self, package_apk, device=None):
        """Runs adb install"""
        device = self.__check_device(device)
        subprocess.run(['adb', '-s', device, 'install', '-g', '-t', '-r', '-d', package_apk])

    def uninstall(self, package_name, device=None):
        """Runs adb uninstall"""
        device = self.__check_device(device)
        subprocess.run(['adb', '-s', device, 'uninstall', package_name])

    def __check_device(self, device):
        """Checks that a device is connected"""
        if not device:
            device = self.device

        if not device:
            logger.error("No device selected")
            raise ValueError("No device selected")

        if device not in self.devices:
            logger.error(f"Device '{device}' not found in connected devices!")
            raise ValueError("Device not found!")

        return device

    def cleanUpSDCard(self, working_dir="/sdcard/devlib-target", older_than_days=30, delete=False, files=None):
        """
        List stale files in the device working directory and optionally delete them.

        If ``files`` is provided, those paths are used for deletion instead of
        running a fresh device scan.
        """
        if files is None:
            stdout, _ = self.command(['ls', working_dir], True, errors_handled_externally=True)
            if not stdout:
                return []

            stdout, _ = self.command(
                [f'find "{working_dir}" -mindepth 1 -type f -mtime +{int(older_than_days)} | sort'],
                True,
                errors_handled_externally=True,
            )
            files = [line.strip() for line in stdout.splitlines() if line.strip()]
        else:
            files = [str(file_path).strip() for file_path in files if str(file_path).strip()]
        if files:
            logger.debug(
                f"Files older than {older_than_days} days in {working_dir}:\n" + "\n".join(files)
            )
        if delete:
            for file_path in files:
                self.command(['rm', '-f', file_path], True, errors_handled_externally=True)
        return files


if __name__ == '__main__':
    a = adb()
    a.init()
    if a.device is None:
        a.select_device(a.devices[0])
    for d in a.devices:
        print("%s : %s" % (d, a.configs[d]))
        for v in a.apps():
            print('\t' + str(v))
