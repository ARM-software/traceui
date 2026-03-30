from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer, QEventLoop
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QMessageBox, QStackedWidget, QHBoxLayout, QPushButton, QApplication

from core.page_navigation import PageNavigation
from core.page_navigation import PageIndex

import json
from pathlib import Path
import time
import subprocess

from core.logger_config import setup_logger

logger = setup_logger("replay")

class ReplayWorker(QObject):
    finished = Signal(bool)
    done_replaying = Signal(bool)
    result_ready = Signal(object)
    cleanup_finished = Signal(bool)
    move_pictures = Signal(bool)
    pull_pictures = Signal(bool)
    replay_started = Signal(bool)
    error = Signal(Exception)


    def __init__(self, adb, process, cmd, filename, screenshot, hwc, local_dir, extra_args={}, working_dir=Path("/sdcard/devlib-target")):
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
        self.extra_args = extra_args
        self.working_dir = Path(working_dir)

    def stop(self):
        self._killed = True

    def start_replay(self):
        self.replay_started.emit(True)
        self.adb.manage_app_permissions(self.process)
        if "gfxreconstruct" in self.process:
            logger.debug("Replaying with command: {}".format(
                " ".join([str(x) for x in self.cmd])))
            subprocess.run(" ".join(self.cmd), shell=True, capture_output=False)
        else:
            self.adb.command(self.cmd)
            logger.debug(f"Replaying with command: {self.cmd}")
        time.sleep(0.1)

        stdout, _ = self.adb.command([f"ps -A | grep {self.process}"])
        logger.info("Replay still ongoing.")
        while f'{self.process}' in stdout:
            time.sleep(0.5)
            stdout, _ = self.adb.command([f"ps -A | grep {self.process}"], print_command=False)
        if not self._killed:
            self.done_replaying.emit(True)
        else:
            self.finished.emit(True)

    def generatefastforward(self):
        self.results = dict()
        self.results['trace_path'] = self.filename
        self.results['fastforward_trace_path'] = self.extra_args["output_file"]
        self.adb.pull(self.results['fastforward_trace_path'], 'tmp')
        if self.extra_args['to_frame'] is None:
                self.extra_args['to_frame'] = 999_999
        if self.process == "com.lunarg.gfxreconstruct.replay":
            optimized_trace = self.extra_args["currentTool"].optimize_trace(f"tmp/{self.results['fastforward_trace_path'].split('/')[-1]}")
            if optimized_trace is not None:
                trace_base = Path(self.filename).parent
                ff_name = f"{Path(self.filename).stem}"
                self.results['fastforward_trace_path'] = f"{trace_base}/{ff_name}_frames_{self.extra_args['from_frame']}_through_{self.extra_args['to_frame']}.optimized.gfxr"
                self.adb.push(optimized_trace, trace_base, device=None, track=False)
        # Check if the fastforward tracing actually made a file
        try:
            ff_trace_output, _ = self.adb.command(
                [f"if [ -f {self.results['fastforward_trace_path']} ]; then echo true; else echo false; fi"])
            #currentTool.trace_reset_device()
            if ff_trace_output == 'true':
                self.result_ready.emit(self.results)
            else:
                raise AssertionError('Fastforward trace have NOT been created')
        except AssertionError as e:
            self.error.emit(e)
        finally:
            self.finished.emit(True)




    def postreplay(self):
        self.results = dict()
        if self.screenshot:
            dir_prefix = f"{Path(self.filename).stem}_screenshot"
            sdcard_dir = str(self.working_dir / dir_prefix)
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
            hwcpipe_layer_result_mask = f"{self.working_dir}/*_gpu_id_*_per_frame_counters.csv"
            if "gfxreconstruct" in self.process:
                hwcpipe_layer_result_mask = "/sdcard/*_gpu_id_*_per_frame_counters.csv"

            potential_paths, _ = self.adb.command(
                ['ls -S', hwcpipe_layer_result_mask])
            potential_paths = potential_paths.splitlines()

            if len(potential_paths) == 0:
                logger.error(f"Failed to generate HWC data, no files found matching mask: {hwcpipe_layer_result_mask} ")
            else:
                self.results['hwc_path'] = potential_paths[0]
            if len(potential_paths) > 1:
                logger.debug(
                    "More than one result file found from HWC data generation, picked the biggest one: " +
                    potential_paths[0])
        self.result_ready.emit(self.results)

    def __check_screenshots_on_device(self, base_dir, grep_string, cleanup=False):
        if cleanup:
            logger.debug(f"Cleaning up screenshot directory")
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
            sdcard_dir = str(self.working_dir / dir_prefix)
            screenshot_prefix = f'{dir_prefix}_frame_'
            self.__check_screenshots_on_device(base_dir=sdcard_dir, grep_string=screenshot_prefix, cleanup=True)
        self.finished.emit(True)

    def pullPictures(self):
        self.pull_pictures.emit(True)
        if self.local_dir and self.results.get('screenshot_path'):
            for image in self.results.get('screenshot_path'):
                self.adb.pull(image, self.local_dir)
        self.finished.emit(True)


class ReplaySetupWorker(QObject):
    finished = Signal(bool)
    error = Signal(Exception)

    def __init__(self, tool):
        super().__init__()
        self.tool = tool

    def setup_replay(self):
        try:
            self.tool.replay_setup()
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(e)
            self.finished.emit(False)


class UiReplayWidget(PageNavigation):
    frame_range_signal = Signal()
    ff_done = Signal()

    def __init__(self, adb, plugins, replay_working_dir):
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
        self.replay_working_dir = Path(replay_working_dir)
        self.errorsLastReplay = False
        self._replay_exception = None
        self._default_replay_label_text = "Please check device for potential infomation if the program remains stuck on this page."
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

    def setWorkingDir(self, path):
        """
        Update replay working directory on device.
        """
        self.replay_working_dir = Path(path)

    def cleanup_page(self):
        """
        Go to replay page
        """
        self.reset_status_label()
        self.errorsLastReplay = False
        self._replay_exception = None
        if hasattr(self, "adbWorker"):
            self.adbWorker.stop()
        if self.adb and self.currentTool and hasattr(self.currentTool, "replayer"):
            pkg = self.currentTool.replayer.get("name")
            self.adb.command(["am", "kill-all"], run_with_sudo=True)
            if pkg:
                self.adb.command(["am", "force-stop", pkg], run_with_sudo=True)


    def setupLoading(self):
        """
        Set up loading screen
        """
        self.replay_label = QLabel(self._default_replay_label_text)
        self.replay_label.setAlignment(Qt.AlignCenter)
        self.replay_label.setStyleSheet("font-weight: bold; color: #444;")
        self.replay_label.setAlignment(Qt.AlignCenter)
        self.h_layout = QHBoxLayout()
        self.h_layout.addStretch()
        self.h_layout.addWidget(self.replay_label)
        self.h_layout.addStretch()
        self.setLayout(self.h_layout)

    def reset_status_label(self):
        """
        Restore the default label text shown on the replay page.
        """
        self.replay_label.setText(self._default_replay_label_text)


    def gotoframe_range_signal(self):
        """
        Go to next page
        """
        self.replay_label.setText("Loading images. Please wait...")
        self.frame_range_signal.emit()
        self.next_signal.emit(PageIndex.FRAMERANGE)

    def replay(self, screenshots=False, hwc=False, repeat=1, fastforward=False, from_frame=None, to_frame=None, trace=None, interval=10, local_dir=None, extra_args=[]):
        trace_used = self.currentTrace
        if trace is not None:
            trace_used = trace
        self.errorsLastReplay = False
        self._replay_results = None
        self._replay_exception = None
        self.adb.clear_logcat()
        self.currentTool.adb = self.adb
        self.replay_label.setText("Installing replayer on device. Check Device for a popup...")
        self._setup_event_loop = QEventLoop()
        self.setup_thread = QThread()
        self.setup_worker = ReplaySetupWorker(self.currentTool)
        self.setup_worker.moveToThread(self.setup_thread)
        self.setup_thread.started.connect(self.setup_worker.setup_replay)
        self.setup_worker.error.connect(self._handle_worker_error)
        self.setup_worker.finished.connect(self.setup_thread.quit)
        self.setup_worker.finished.connect(self._setup_event_loop.quit)
        self.setup_worker.finished.connect(self.setup_worker.deleteLater)
        self.setup_thread.finished.connect(self.setup_thread.deleteLater)
        self.setup_thread.start()
        self._setup_event_loop.exec()
        if self._replay_exception is not None:
            logger.error(f"Failed during replay setup: {self._replay_exception}")
            QMessageBox.warning(self, "Replay setup failed", str(self._replay_exception))
            return None
        self.replay_label.setText("Cleaning the device. Please wait.")

        self._cleanup_event_loop = QEventLoop()
        self.cleanup_thread = QThread()
        self.cleanup_Worker = ReplayWorker(self.adb, None, None, trace_used, screenshots, hwc, None, working_dir=self.replay_working_dir)
        self.cleanup_Worker.moveToThread(self.cleanup_thread)
        self.cleanup_thread.started.connect(self.cleanup_Worker.cleanup)

        self.cleanup_Worker.finished.connect(self.cleanup_thread.quit)
        self.cleanup_Worker.finished.connect(self._cleanup_event_loop.quit)
        self.cleanup_Worker.finished.connect(self.cleanup_Worker.deleteLater)
        self.cleanup_thread.finished.connect(self.cleanup_thread.deleteLater)
        self.cleanup_thread.start()
        self._cleanup_event_loop.exec()
        if hasattr(self, 'adbThread') and self.adbThread is not None:
            try:
                if self.adbThread.isRunning():
                    logger.debug("Waiting for previous adbThread to finish...")
                    self.adbThread.quit()
                    self.adbThread.wait()
            except RuntimeError:
                logger.debug("adbThread was already deleted. Skipping wait.")
            self.adbThread = None

        self.adbThread = QThread()
        self._replay_event_loop = QEventLoop()

        if fastforward:
            self.plugins["fastforward"].adb = self.adb
            self.cmd, output_file = self.plugins["fastforward"].replay_start_fastforward(trace_used, self.currentTool, from_frame=from_frame, to_frame=to_frame)
            extra_args = {
                "output_file": output_file,
                "from_frame": from_frame,
                "to_frame": to_frame,
                "currentTool": self.currentTool
            }
            self.ff_worker = ReplayWorker(self.adb, self.currentTool.replayer["name"], self.cmd, trace_used, screenshots, hwc, local_dir, extra_args, working_dir=self.replay_working_dir)
            self.ff_worker.moveToThread(self.adbThread)
            self.adbThread.started.connect(self.ff_worker.start_replay)
            #generate fast forward and verifying
            self.ff_worker.done_replaying.connect(self.ff_worker.generatefastforward)

            self.ff_worker.result_ready.connect(self._handle_result_ready)
            self.ff_worker.result_ready.connect(lambda: self.ff_done.emit())
            self.ff_worker.error.connect(self._handle_worker_error)

            self.ff_worker.finished.connect(self.adbThread.quit)
            self.ff_worker.finished.connect(self.ff_worker.deleteLater)
            self.adbThread.finished.connect(self.adbThread.deleteLater)

            self.adbThread.start()
            self._replay_event_loop.exec()
            self.check_replay_errors()
            return self._replay_results

        else:
            self.cmd, data = self.currentTool.replay_start(trace_used, screenshot=screenshots, hwc=hwc, repeat=repeat, extra_args=extra_args, from_frame=from_frame, to_frame=to_frame, interval=interval)

            if self.cmd == None and data == None:
                return None
            if self.currentTool.plugin_name == "patrace":
                with open('tmp/replay_args.json', 'w') as outfile:
                    json.dump(data, outfile, indent=2)
                self.adb.command(["mkdir", "-p", str(self.replay_working_dir)], True)
                self.adb.push('tmp/replay_args.json', str(self.replay_working_dir))
            logger.debug("Currently replaying the thread.")
            QApplication.processEvents()

            self.adbWorker = ReplayWorker(self.adb, self.currentTool.replayer["name"], self.cmd, trace_used, screenshots, hwc, local_dir, working_dir=self.replay_working_dir)
            self.adbWorker.moveToThread(self.adbThread)
            self.adbThread.started.connect(self.adbWorker.start_replay)

            self.adbWorker.done_replaying.connect(self.adbWorker.postreplay)

            self.adbWorker.result_ready.connect(self.adbWorker.pullPictures)
            self.adbWorker.result_ready.connect(self._handle_result_ready)
            self.adbWorker.replay_started.connect(lambda: self.replay_label.setText("Replay has started. Please wait..."))
            if screenshots and interval !=0:
                self.adbWorker.replay_started.connect(lambda: self.replay_label.setText("Taking screenshots while replaying. Please wait..."))
            self.adbWorker.move_pictures.connect(lambda: self.replay_label.setText("Renaming screenshots. Please wait..." ))
            self.adbWorker.pull_pictures.connect(lambda: self.replay_label.setText("Pulling pictures from device to local tmp directory. Please wait..."))

            self.adbWorker.finished.connect(self.adbThread.quit)
            self.adbWorker.finished.connect(self.adbWorker.deleteLater)
            self.adbThread.finished.connect(self.adbThread.deleteLater)

            self.adbThread.start()

            self._replay_event_loop.exec()
            self.check_replay_errors()
            return self._replay_results

    def check_replay_errors(self):
        logger.info("Checking for errors during replay")
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

    def _handle_worker_error(self, exception):
        self._replay_results = None
        self._replay_exception = exception
        if hasattr(self, "_setup_event_loop") and self._setup_event_loop:
            self._setup_event_loop.quit()
        if self._replay_event_loop:
            self._replay_event_loop.quit()
