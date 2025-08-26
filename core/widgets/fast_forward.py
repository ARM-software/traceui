from core.page_navigation import PageNavigation, PageIndex
from plugins.fastforward import tracetool
from core.widgets.replay import ReplayWorker

import time
import subprocess

from core.config import ConfigSettings
from PySide6.QtCore import Qt, Signal, QObject, QThread, QEventLoop
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QPushButton, QStackedWidget

class FastForwardWorker(QObject):
    """
    Helper class to be able to run screen comparison in a QThread.
    """
    finished = Signal(bool)
    not_installed = Signal(bool)
    image_diffs_result = Signal(object)

    def __init__(self, adb, result_ff, result_src, start_frames, currentTool):
        """
        Initialise class.

        Args:
            adb: Device used to get screenshots
            result_ff (dict): Contains all screenshots from ff traces, where the key is the respective start frame
            result_src (list): List of screenshots containing every frame from original trace.
            start_frames (list): Frames from frame selection and start frame for ff trace(s).
        """
        super().__init__()
        self.adb = adb
        self.result_ff = result_ff
        self.result_source = result_src
        self.start_frames = start_frames
        self.currentTool = currentTool
        self.config = ConfigSettings()



    def compare_screenshot(self):
        """
        Screenshot comparison
        Compares screenshots between fastforward trace and source trace.
        """
        image_diffs_detected = {}
        for num in self.start_frames:
            if not num:
                print("[ ERROR ] Frame invalid. Skipping... ")
            image_diffs_detected[num] = []
            cmd_compare = ["compare", "-alpha", "off", "-metric", "RMSE"]
            source_frame_index = num
            ff_frame_index = 1
            if self.currentTool == 'gfxreconstruct':
                source_frame_index+=1
                ff_frame_index+=1
            ff_frame_list = self.result_ff[num].get('screenshot_path', [])
            source_frame_list = self.result_source.get('screenshot_path', [])
            # Compares all screenshots from FF trace with equivalent frame in source trace, pulling a reduced amount of screenshots. Assuming indices are set correctly.
            while True:
                ff_frame = next((i for i in iter(ff_frame_list) if f"frame_{ff_frame_index}.png" in i), None)
                source_frame = next((i for i in iter(source_frame_list) if f"frame_{source_frame_index}.png" in i), None)
                if ff_frame is None or source_frame is None:
                    break

                self.adb.pull(ff_frame, self.config.get_config()['Paths']['img_path'])
                self.adb.pull(source_frame, self.config.get_config()['Paths']['img_path'])

                ff_frame_local = f"{self.config.get_config()['Paths']['img_path']}/{ff_frame.split('/')[-1]}"
                source_frame_local = f"{self.config.get_config()['Paths']['img_path']}/{source_frame.split('/')[-1]}"
                diff_frame = f"{self.config.get_config()['Paths']['img_path']}/diff_frame_{source_frame_index}.png"

                cmd = cmd_compare + [ff_frame_local, source_frame_local, diff_frame]
                process = subprocess.run(" ".join(cmd), shell=True, capture_output=True)
                stdout = process.stdout.decode().strip()
                stderr = process.stderr.decode().strip()
                if "compare: not found" in stderr:
                    print("[ ERROR ] ImageMagick not installed. Please see README")
                    self.not_installed.emit(True)
                    self.finished.emit(True)
                    break
                elif stderr.split()[0] != '0':
                    diff_tuple = (diff_frame, ff_frame_local, source_frame_local)
                    image_diffs_detected[num].append(diff_tuple)
                ff_frame_index += 1
                source_frame_index += 1
        for num in self.start_frames:
            if len(image_diffs_detected[num]):
                print(f"[ INFO ] Image diff detected in fast forward trace {num}:")
                for i in range(len(image_diffs_detected[num])):
                    print(f"\t{image_diffs_detected[num][i][0]} when comparing {image_diffs_detected[num][i][1]} to {image_diffs_detected[num][i][2]}")
        self.image_diffs_result.emit(image_diffs_detected)
        self.finished.emit(True)




class UiFastForwardWidget(PageNavigation):
    PAGE_PREFASTFORWARD = 0
    PAGE_LOADING = 1
    PAGE_POSTFASTFORWARD = 2
    PAGE_POSTHWC = 3

    def __init__(self):
        super().__init__()
        self.replay_widget = None
        self.frames = None
        self.framerange_start = None
        self.framerange_end = None
        self.image_diffs = None

        self.setUpWidgetsPreFF()
        self.setUpLayoutsPreFF()
        self.setUpLoading()
        self.setUpVerification()
        self.setUpPostHWC()


    def setUpWidgetsPreFF(self):
        """"
        Set up widgets
        """
        self.label = QLabel("Click to generate fastforward trace")
        self.label.setAlignment(Qt.AlignCenter)
        self.button = QPushButton("Start")
        self.button.clicked.connect(self.performFastForward)

    def setUpLayoutsPreFF(self):
        """"
        Set up layout
        """
        self.nestedStack = QStackedWidget()
        layout = QVBoxLayout()
        pre_fastforward_widget = QWidget()
        layout.addWidget(self.label)
        layout.addWidget(self.button)
        layout.setAlignment(Qt.AlignCenter)
        pre_fastforward_widget.setLayout(layout)
        self.nestedStack.insertWidget(self.PAGE_PREFASTFORWARD, pre_fastforward_widget)

        top_layout = QVBoxLayout(self)
        top_layout.addWidget(self.nestedStack)
        self.setLayout(top_layout)

        self.nestedStack.setCurrentIndex(self.PAGE_PREFASTFORWARD)

    def setUpLoading(self):
        """
        Set up loading page
        """
        self.waiting_label = QLabel("Please wait...")
        loading_widget = QWidget()
        self.waiting_label.setAlignment(Qt.AlignCenter)

        v_layout = QVBoxLayout()
        v_layout.addWidget(self.waiting_label)
        loading_widget.setLayout(v_layout)

        self.nestedStack.insertWidget(self.PAGE_LOADING, loading_widget)


    def setUpVerification(self):
        """
        Set up page for post-verification of fast forwarding
        """
        self.finished_label = QLabel("Done with verification")
        self.result_label = QLabel()
        done_widget = QWidget()
        self.finished_label.setAlignment(Qt.AlignCenter)
        self.result_label.setAlignment(Qt.AlignCenter)
        self.generate_hwc = QPushButton("Generate HWC")
        self.generate_hwc.clicked.connect(self.generateHWC)

        v_layout = QVBoxLayout()
        v_layout.addStretch()
        v_layout.addWidget(self.finished_label)
        v_layout.addWidget(self.result_label)
        v_layout.addWidget(self.generate_hwc)
        v_layout.addStretch()
        done_widget.setLayout(v_layout)

        self.nestedStack.insertWidget(self.PAGE_POSTFASTFORWARD, done_widget)

    def setUpPostHWC(self):
        """
        Set up page for post hwc generation
        """
        label_done = QLabel("HWC completed!")
        label_done.setStyleSheet("font-weight: bold; color: #444;")
        label_done.setAlignment(Qt.AlignCenter)
        self.hwc_result = QLabel()

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(label_done)
        layout.addWidget(self.hwc_result)
        layout.addStretch()
        page_widget = QWidget()
        page_widget.setLayout(layout)

        self.nestedStack.insertWidget(self.PAGE_POSTHWC, page_widget)

    def setHWCResultLabel(self, hwc_dict):
        """
        Set label to show where diff is higher than allowed

        Args:
            hwc_dict (dict): contains result of hwc generation. Key is start frame for fast forward trace.
        """
        final_string = ""
        for frame in self.frames:
            string_h = f"Diffs detected in fast forward that starts at frame {frame}: \n"
            for diff in hwc_dict[frame]['ff_hwc_diffs']['diffs']:
                new_line = f"src_frame: {diff['source_frame']} ff_frame: {diff['ff_frame']} Metric: {diff['metric']} "
                new_line = new_line + f"Diffs percentage: {diff['diff_percentage']} Diff Ratio: {diff['diff_ratio']} \n"
                string_h = string_h + new_line
            final_string = final_string + string_h + "\n"

        self.hwc_result.setText(f"{final_string}")

    def generateHWC(self):
        """
        Generate HWC using plugin
        """
        self.waiting_label.setText("Generating HWC. Please wait...")
        self.nestedStack.setCurrentIndex(self.PAGE_LOADING)
        currentTrace = self.replay_widget.currentTrace
        currentTool = self.replay_widget.currentTool
        trace = tracetool(self.replay_widget.adb)
        hwc_dict = {}
        prev_result = {}
        for frame in self.frames:
            self.waiting_label.setText(f"Generating HWC for fast forwarding trace starting at frame {frame}")
            hwc_data = trace.generateHWC(ff_trace=self.ff_traces[frame], from_frame=frame, source_trace=currentTrace, prev_results=prev_result, currentTool=currentTool, replayer=self.replay_widget)
            prev_result = hwc_data
            hwc_dict[frame] = hwc_data
        self.setHWCResultLabel(hwc_dict)
        self.nestedStack.setCurrentIndex(self.PAGE_POSTHWC)


    def performFastForward(self):
        """
        Generate fast forward trace(s) for all selected frames and takes screenshots. Also
        take screenshots of original trace and compares.

        Returns:
            ff_trace_list (list): List of path(s) to fastforward trace(s).
        """
        self.nestedStack.setCurrentIndex(self.PAGE_LOADING)
        currentTool = self.replay_widget.currentTool
        original_trace = self.replay_widget.currentTrace
        tool = tracetool(self.replay_widget.adb)
        extra_args = []
        screenshots_ff = {}
        self.ff_traces = {}
        # This will cause ALOT of replays, which is not ideal....
        for i in range(len(self.frames)):
            if not self.frames[i]:
                print(f"[ ERROR ] Frame not valid. Skipping...")
                continue

            self.waiting_label.setText(f"Generating fast forward trace from trace number {self.frames[i]} ({i +1}/{len(self.frames)})")
            results = self.replay_widget.replay(
                screenshots=False,
                trace = original_trace,
                hwc=False,
                repeat=1,
                fastforward=True,
                from_frame=self.frames[i],
                extra_args=extra_args,
            )
            ff_trace = results["fastforward_trace_path"]
            self.ff_traces[self.frames[i]] = ff_trace

            self.waiting_label.setText(f"Getting screenshots of fast fastforward from trace number {self.frames[i]} ({i +1}/{len(self.frames)})")
            result_ff = self.replay_widget.replay(
                screenshots="fastforward",
                hwc=False,
                repeat=1,
                fastforward=False,
                to_frame=self.framerange_end,
                extra_args=[],
                trace = ff_trace,
            )

            screenshots_ff[self.frames[i]] = result_ff

        self.waiting_label.setText("Getting screenshots of original trace")
        result_original = self.replay_widget.replay(
            screenshots="fastforward",
            hwc=False,
            repeat=1,
            fastforward=False,
            from_frame=min(self.frames),
            to_frame=self.framerange_end,
            extra_args=[],
            trace = original_trace,
        )

        self._verify_event_loop = QEventLoop()
        self.waiting_label.setText("Comparing screenshots to verify the fast forward trace(s)")
        self.verify_worker = FastForwardWorker(self.replay_widget.adb, screenshots_ff, result_original, self.frames, currentTool)
        self.verify_thread = QThread()
        self.verify_worker.moveToThread(self.verify_thread)
        self.verify_thread.started.connect(self.verify_worker.compare_screenshot)

        self.verify_worker.not_installed.connect(lambda: self.result_label.setText("Verification failed. ImageMagick not installed. See README"))
        self.verify_worker.image_diffs_result.connect(self._get_result)
        self.verify_worker.finished.connect(self.verify_thread.quit)
        self.verify_worker.finished.connect(self._verify_event_loop.quit)
        self.verify_worker.finished.connect(self.verify_worker.deleteLater)
        self.verify_thread.finished.connect(self.verify_thread.deleteLater)

        self.verify_thread.start()
        self._verify_event_loop.exec()
        self.nestedStack.setCurrentIndex(self.PAGE_POSTFASTFORWARD)
        print("[ INFO ] Comparison is completed")
        self.displayComparisonResult()


    def cleanup_page(self):
        """
        Clean up page
        """
        self.nestedStack.setCurrentIndex(self.PAGE_PREFASTFORWARD)
        self.frames = None
        self.framerange_start = None
        self.framerange_end = None
        self.ff_frame_list = None
        self.image_diffs = None
        self.result_label.clear()
        self.ff_traces = None
        self.waiting_label.setText("Please wait...")

    def displayComparisonResult(self):
        """
        Set label to display which frames differ
        """
        diff_detected = False
        tmp_string = ""

        for num in self.frames:
            if len(self.image_diffs[num]):
                diff_detected = True
                tmp_string = tmp_string + f"Image diff detected in fast forward trace {num}:\n"
                for i in range(len(self.image_diffs[num])):
                    first_file = self.image_diffs[num][i][0].split('/')[-1]
                    second_file = self.image_diffs[num][i][1].split('/')[-1]
                    third_file = self.image_diffs[num][i][2].split('/')[-1]
                    tmp_string = tmp_string + f" Diff in {first_file} when comparing {second_file} to {third_file}\n"
        if not diff_detected:
            tmp_string = "No difference detected between the original trace and the fast forward trace(s)!"
        self.result_label.setText(tmp_string)

    def _get_result(self, result):
        """
        Get image diffs from thread
        """
        self.image_diffs = result
        if self._verify_event_loop:
            self._verify_event_loop.quit()
