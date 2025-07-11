from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer, QEventLoop
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QMessageBox, QStackedWidget, QHBoxLayout, QPushButton, QApplication

from core.page_navigation import PageNavigation
from core.page_navigation import PageIndex
from adblib import print_codes

import json
from pathlib import Path
import time
import subprocess

class ReplayWorker(QObject):
    finished = Signal(bool)
    done_replaying = Signal(bool)
    result_ready = Signal(object)
    cleanup_finished = Signal(bool)
    move_pictures = Signal(bool)
    pull_pictures = Signal(bool)
    replay_started = Signal(bool)


    def __init__(self, adb, process, cmd, filename, screenshot, hwc, local_dir):
        super().__init__()
        self.adb = adb
        self.process = process
        self._killed = False
        self.filename = filename
        self.cmd = cmd
        self.screenshot = screenshot
        self.hwc = hwc
        self.local_dir = local_dir
        self.results = None

    def stop(self):
        self._killed = True

    def start_replay(self):
        self.replay_started.emit(True)
        self.adb.manage_app_permissions(self.process)
        if "gfxreconstruct" in self.process:
            print("[INFO] Replaying with command: {}".format(
                " ".join([str(x) for x in self.cmd])))
            subprocess.run(" ".join(self.cmd), shell=True, capture_output=False)
        else:
            self.adb.command(self.cmd)
        time.sleep(0.1)

        stdout, _ = self.adb.command([f"ps -A | grep {self.process}"])
        print("Replay still ongoing.")
        while f'{self.process}' in stdout:
            time.sleep(0.5)
            stdout, _ = self.adb.command([f"ps -A | grep {self.process}"], print_command=False)
        if not self._killed:
            self.done_replaying.emit(True)
        else:
            self.finished.emit(True)

    def postreplay(self):
        self.results = dict()
        if self.screenshot:
            dir_prefix = f"{Path(self.filename).stem}_screenshot"
            sdcard_dir= f"/sdcard/devlib-target/{dir_prefix}"
            screenshot_prefix = f"{dir_prefix}_frame_"
            self.results['screenshot_path'] = self.__check_screenshots_on_device(base_dir=sdcard_dir, grep_string=screenshot_prefix, cleanup=False)
            # TODO: leave file name intact on device. Rename locally instead
            self.move_pictures.emit(True)
            if "paretrace" in self.process:
                for f in self.results['screenshot_path']:
                    fnum = f.split("frame_")[-1].split("_")[0]
                    self.adb.command([f'mv {f} {sdcard_dir}/{screenshot_prefix}{int(fnum)}.png'], True)
            self.results['screenshot_path'] = self.__check_screenshots_on_device(base_dir=sdcard_dir, grep_string=screenshot_prefix, cleanup=False)

        if self.hwc:
            hwcpipe_layer_result_mask = "/sdcard/devlib-target/*_gpu_id_*_per_frame_counters.csv"
            if "gfxreconstruct" in self.process:
                hwcpipe_layer_result_mask = "/sdcard/*_gpu_id_*_per_frame_counters.csv"

            potential_paths, _ = self.adb.command(
                ['ls -S', hwcpipe_layer_result_mask])
            potential_paths = potential_paths.splitlines()

            if len(potential_paths) == 0:
                print(f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] Failed to generate HWC data, no files found matching mask: {hwcpipe_layer_result_mask} ")
            else:
                self.results['hwc_path'] = potential_paths[0]
            if len(potential_paths) > 1:
                print(
                    "[ INFO ] More than one result file found from HWC data generation, picked the biggest one: " +
                    potential_paths[0])
        self.result_ready.emit(self.results)

    def __check_screenshots_on_device(self, base_dir, grep_string, cleanup=False):
        if cleanup:
            print(f"[ {print_codes.SUCCESS}INFO{print_codes.END_CODE} ] Cleaning up screenshot directory")
            self.adb.command(["rm", "-rf", base_dir])
            return
        paths, _ = self.adb.command(
            [f'ls {base_dir} | grep {grep_string}'])
        paths = paths.split()
        full_paths = []
        for path in paths:
            full_paths.append(f"{base_dir}/{path}")
        return full_paths

    def cleanup(self):
        if self.screenshot:
            dir_prefix = f'{Path(self.filename).stem}_screenshot'
            sdcard_dir = f"/sdcard/devlib-target/{dir_prefix}"
            screenshot_prefix = f'{dir_prefix}_frame_'
            self.__check_screenshots_on_device(base_dir=sdcard_dir, grep_string=screenshot_prefix, cleanup=True)
        self.finished.emit(True)

    def pullPictures(self):
        self.pull_pictures.emit(True)
        if self.local_dir and self.results.get('screenshot_path'):
            for image in self.results.get('screenshot_path'):
                self.adb.pull(image, self.local_dir)
        self.finished.emit(True)


class UiReplayWidget(PageNavigation):
    frame_range_signal = Signal()

    def __init__(self, adb, plugins):
        """
        Initialize the replay page
        Args:
            adb: Current connected device(s)
            plugins (dict): Current available plugins
        """
        super().__init__()
        self.currentTool = None
        self.currentTrace = None
        self.adb = adb
        self.plugins = plugins
        self.errorsLastReplay = False
        self.setupLoading()

    def setCurrentTool(self, tool):
        """
        Set current tool
        """
        self.currentTool = tool

    def setCurrentTrace(self, trace):
        """
        Set current trace
        """
        self.currentTrace = trace

    def cleanup_page(self):
        """
        Go to replay page
        """
        self.replay_label.setText("Please wait...")
        self.errorsLastReplay = False
        pkg = self.currentTool.replayer["name"]
        self.adbWorker.stop()
        self.adb.command(["am", "kill-all"], run_with_sudo=True)
        self.adb.command(["am", "force-stop", pkg], run_with_sudo=True)


    def setupLoading(self):
        """
        Set up loading screen
        """
        self.replay_label = QLabel("Please wait...")
        self.replay_label.setText("Cleaning up the device and removing old screenshots. Please wait...")
        self.replay_label.setAlignment(Qt.AlignCenter)
        self.replay_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #444;")
        self.replay_label.setAlignment(Qt.AlignCenter)
        self.h_layout = QHBoxLayout()
        self.h_layout.addStretch()
        self.h_layout.addWidget(self.replay_label)
        self.h_layout.addStretch()
        self.setLayout(self.h_layout)


    def gotoframe_range_signal(self):
        """
        Go to next page
        """
        self.frame_range_signal.emit()
        self.next_signal.emit(PageIndex.FRAMERANGE)

    def downloadTrace(self):
        """
        Download trace to tmp/
        """
        self.adb.pull(self.currentTrace, 'tmp')
        msg = QMessageBox()
        msg.setText("\n".join(["INFO: Trace Downloaded to:", f"tmp{self.currentTrace}"]))
        msg.exec()

    def replay(self, screenshots=False, hwc=False, repeat=1, fastforward=False, from_frame=None, to_frame=None, prev_results={}, local_dir=None, extra_args=[], frame_selection=False):
        # TODO: Fast forwading support
        self.errorsLastReplay = False
        self.adb.clear_logcat()
        self.currentTool.replay_setup()

        self._cleanup_event_loop = QEventLoop()
        self.cleanup_thread = QThread()
        self.cleanup_Worker = ReplayWorker(self.adb, None, None, self.currentTrace, screenshots, hwc, None)
        self.cleanup_Worker.moveToThread(self.cleanup_thread)
        self.cleanup_thread.started.connect(self.cleanup_Worker.cleanup)

        self.cleanup_Worker.finished.connect(self.cleanup_thread.quit)
        self.cleanup_Worker.finished.connect(self._cleanup_event_loop.quit)
        self.cleanup_Worker.finished.connect(self.cleanup_Worker.deleteLater)
        self.cleanup_thread.finished.connect(self.cleanup_thread.deleteLater)
        self.cleanup_thread.start()
        self._cleanup_event_loop.exec()

        self.cmd, data = self.currentTool.replay_start(self.currentTrace, screenshot=screenshots, hwc=hwc, repeat=repeat, extra_args=extra_args)

        if self.currentTool.plugin_name == "patrace":
            with open(f'tmp/replay_args.json', 'w') as outfile:
                json.dump(data, outfile, indent=2)
            self.adb.push(f'tmp/replay_args.json', '/sdcard/devlib-target/')
        print("[ INFO ] Currently replaying the thread.")
        QApplication.processEvents()

        self.adbThread = QThread()
        self.adbWorker = ReplayWorker(self.adb, self.currentTool.replayer["name"], self.cmd, self.currentTrace, screenshots, hwc, local_dir)
        self.adbWorker.moveToThread(self.adbThread)
        self.adbThread.started.connect(self.adbWorker.start_replay)

        self.adbWorker.done_replaying.connect(self.adbWorker.postreplay)

        self.adbWorker.result_ready.connect(self.adbWorker.pullPictures)
        self._replay_event_loop = QEventLoop()
        self.adbWorker.result_ready.connect(self._handle_result_ready)
        self.adbWorker.replay_started.connect(lambda: self.replay_label.setText("Replay has started. Please wait..."))
        if screenshots:
            self.adbWorker.replay_started.connect(lambda: self.replay_label.setText("Taking screenshots while replaying. Please wait..."))
        self.adbWorker.move_pictures.connect(lambda: self.replay_label.setText("Renaming screenshots. Please wait..." ))
        self.adbWorker.pull_pictures.connect(lambda: self.replay_label.setText("Pulling pictures from device to local tmp directory. Please wait..."))

        self.adbWorker.finished.connect(self.adbThread.quit)
        self.adbWorker.finished.connect(self.adbWorker.deleteLater)
        self.adbThread.finished.connect(self.adbThread.deleteLater)

        self.adbThread.start()

        self._replay_event_loop.exec()
        self.check_replay_errors(self._replay_results, local_dir)
        if not frame_selection:
            self.gotoframe_range_signal()
        return self._replay_results


    def check_replay_errors(self, results, local_dir):
        print("[ INFO ] Checking for errors during replay")
        #TODO: check this before pulling screenshots. Risk of reporting error about retracer not being found in logcat
        err_lines = self.currentTool.parse_logcat(mode="replay")
        if len(err_lines):
            self.errorsLastReplay = True
            msg = QMessageBox()
            msg.setText("\n".join(["WARNING: Trace replay encountered errors:\n"] + err_lines))
            msg.exec()

        self.currentTool.replay_reset_device()


    def _handle_result_ready(self, results):
        self._replay_results = results
        if self._replay_event_loop:
            self._replay_event_loop.quit()
