from core.page_navigation import PageNavigation, PageIndex
from core.frame_selection import select_frames
from pathlib import Path
import os
import json

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QFormLayout, QCheckBox, QPushButton, QMessageBox, QStackedWidget, QButtonGroup


class UiFrameSelectionWidget(PageNavigation):
    PAGE_PREFRAMESELECT = 0
    PAGE_LOADING = 1
    PAGE_POSTFRAMESELECT = 2

    goto_fastforward_signal = Signal()
    goback_signal = Signal()

    def __init__(self, replay_widget):
        super().__init__()
        self.selected1 = False
        self.selected3 = False
        self.replay_widget = replay_widget
        self.frames = None
        self.expected_local_output = None
        self.framerange_start = 0
        self.framerange_end = 0
        self.setupWidgets()
        self.setupLayouts()



    def setupWidgets(self):
        """
        Set up widgets, pre-frame selection
        """
        self.label = QLabel("How many representative frames for the chosen range is desired")
        self.label.setAlignment(Qt.AlignCenter)
        self.number1 = QCheckBox("1 frame")
        self.number3 = QCheckBox("3 frames")

        self.checkbox_group = QButtonGroup()
        self.checkbox_group.setExclusive(True)
        self.checkbox_group.addButton(self.number1)
        self.checkbox_group.addButton(self.number3)

        self.button = QPushButton("Continue")
        self.button.clicked.connect(self.update)


    def setupLayouts(self):
        """
        Set up layout for page pre frame selection
        """
        self.nestedStack = QStackedWidget()
        layout = QVBoxLayout()
        preselect_widget = QWidget()
        layout.addWidget(self.label)
        if self.detectGpu():
            layout.addWidget(self.number1)
            layout.addWidget(self.number3)
        else:
            self.label = QLabel("Frame selection is not supported on non-Mali devices!")
            self.button = QPushButton("Go back")
            self.button.clicked.connect(self.goback)
        layout.addWidget(self.button)
        layout.setAlignment(Qt.AlignCenter)
        preselect_widget.setLayout(layout)
        self.nestedStack.insertWidget(self.PAGE_PREFRAMESELECT, preselect_widget)
        self.setUpWaiting()
        self.setUpFinished()

        top_layout = QVBoxLayout(self)
        top_layout.addWidget(self.nestedStack)
        self.setLayout(top_layout)

        self.nestedStack.setCurrentIndex(self.PAGE_PREFRAMESELECT)

    def goback(self):
        self.next_signal.emit(PageIndex.FRAMERANGE)
        self.goback_signal.emit()


    def update(self):
        """
        If amount of frames is selected, set page index to loading and compute the frame(s)
        """
        self.selected1 = self.selectOne()
        self.selected3 = self.selectThree()
        if not (self.selected1 or self.selected3):
            msg = QMessageBox()
            msg_text = " Please select one alternative"
            msg.setText(msg_text)
            msg.exec()
        else:
            self.nestedStack.setCurrentIndex(self.PAGE_LOADING)
            QTimer.singleShot(100, self.computeFrames)


    def detectGpu(self):
        """
        Return True if GPU is detected to be Mali
        """
        stdout, _ = self.replay_widget.adb.command([f"getprop | grep mali"])
        if stdout:
            return True

        stdout, _ = self.replay_widget.adb.command([f"dumpsys SurfaceFlinger | grep GLES"])
        for line in stdout.splitlines():
            if "mali" in line.lower():
                return True
        print(f"[ WARNING ] Not detecting Mali GPU, frame selection will be unavailable!")
        return False


    def selectOne(self):
        """
        Return True if one frame was selected, if not return False
        """
        return self.number1.isChecked()


    def selectThree(self):
        """
        Return True if three frames were selected, if not return False
        """
        return self.number3.isChecked()


    def computeFrames(self):
        """
        Compute the frames and change label to tell user the # of the picked frame(s)
        """
        self.waiting_label.setText("Currently replaying the trace and selecting frames. Please wait...")
        extra_args = []
        if self.replay_widget.currentTool.plugin_name == 'gfxreconstruct':
            extra_args = ["--remove-unsupported"]

        results = self.replay_widget.replay(
            screenshots=False,
            hwc=True,
            repeat=1,
            fastforward=False,
            from_frame=self.framerange_start,
            to_frame=self.framerange_end,
            extra_args=extra_args,
            frame_selection=True
        )
        desired_output_dir = self.replay_widget.currentTool.local_output_dir / "results/frame_selection"
        if not os.path.exists(desired_output_dir):
            os.makedirs(desired_output_dir)

        print(f"[ INFO ] Storing frame selection results in: {str(desired_output_dir)}")


        if not results.get("hwc_path"):
            print(f"[ ERROR ] Frame selection post processing failed. No HWC results found after replay.")
        else:
            self.replay_widget.currentTool.trace_get_output(files=results["hwc_path"], output_dir=desired_output_dir)
            self.expected_local_output = os.path.join(desired_output_dir, os.path.basename(results["hwc_path"]))
            if not os.path.exists(self.expected_local_output):
                print(f"[ ERROR ] HWC data generation failed, expected output does not exist: {self.expected_local_output}")
            else:
                print(f"[ INFO ] HWC data generated successfully! Stored locally in: {self.expected_local_output}")
        if self.expected_local_output is None:
            self.waiting_label.setText("Frame selection failed. Retrying")
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle('')
            msg_box.setText("HWC generation failed. Do you wish to retry replay or download the trace to tmp/ and restart")

            retry_button = msg_box.addButton("Retry replay", QMessageBox.YesRole)
            download_button = msg_box.addButton("Download trace", QMessageBox.ActionRole)
            cancel_button = msg_box.addButton("Do not replay", QMessageBox.NoRole)
            msg_box.exec()
            if msg_box.clickedButton() == retry_button:
                self.computeFrames()
            elif msg_box.clickedButton() == download_button:
                self.replay_widget.adb.pull(self.replay_widget.currentTrace, "tmp/")
                self.cleanup_page()
                self.next_signal.emit(PageIndex.START)
            else:
                self.cleanup_page()
                self.next_signal.emit(PageIndex.START)
            return


        if self.selected1:
            print("[ INFO ] Selecting one frame.")
            self.frames = select_frames(self.expected_local_output, self.framerange_start, self.framerange_end, 1)
        elif self.selected3:
            print("[ INFO ] Selecting three frames")
            self.frames = select_frames(self.expected_local_output, self.framerange_start, self.framerange_end, 3)
        else:
            self.cleanup_page()
        if not self.frames:
            print("[ ERROR ] Frame Selection failed")
            msg = QMessageBox()
            msg.setText("Frame selection failed. Please try again.")
            msg.exec()
            self.cleanup_page()
            return
        frame_selection_json = desired_output_dir / "selected_frames.json"
        with open(frame_selection_json, 'w') as outfile:
            json.dump(self.frames, outfile, indent=2)

        print(f"[ INFO ] Representative frame details:")
        print(json.dumps(self.frames, indent=2))

        print(f"[ INFO ] Results stored in: {frame_selection_json}")

        self.replay_widget.adb.pull(self.replay_widget.currentTrace, desired_output_dir)
        self.location_label.setText(f"Location of trace and selected frame information: traceui/{desired_output_dir}")
        print("[ INFO ] Frame selection is completed.")
        num_frame_string = self.getFrameString()
        self.frame_label.setText(f"Frame(s) selected: {num_frame_string}")
        self.nestedStack.setCurrentIndex(self.PAGE_POSTFRAMESELECT)


    def setUpWaiting(self):
        """
        Set up the loading page
        """
        self.waiting_label = QLabel("Please wait...")
        loading_widget = QWidget()
        self.waiting_label.setAlignment(Qt.AlignCenter)
        self.waiting_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #444;")
        self.waiting_label.setAlignment(Qt.AlignCenter)

        h_layout = QVBoxLayout(loading_widget)
        h_layout.addStretch()
        h_layout.addWidget(self.waiting_label)
        h_layout.addStretch()
        loading_widget.setLayout(h_layout)
        self.nestedStack.insertWidget(self.PAGE_LOADING, loading_widget)


    def getFrameString(self):
        """
        Helper function to get frame numbers neatly presented.

        Return:
            the # of the selected frames. If three frames was selected it returns
            a string. If one frame was selected it is returned as an int
        """
        if self.selected1:
            return self.frames[0]["frame"]
        three_frames = ""
        for i in range(3):
            three_frames += str(self.frames[i]["frame"]) +  ", "
        return three_frames[:-2]

    def setUpFinished(self):
        """
        Set up page for after frame selection
        """
        self.done_label = QLabel("Frame selection completed.")
        self.frame_label = QLabel("")
        self.location_label = QLabel("")
        self.continue_button = QPushButton("Continue")
        self.continue_button.clicked.connect(self.continueToFastForward)
        layout = QVBoxLayout()
        layout.addWidget(self.done_label)
        layout.addWidget(self.frame_label)
        layout.addWidget(self.location_label)
        layout.addWidget(self.continue_button)
        layout.setAlignment(Qt.AlignCenter)

        nested_widget = QWidget()
        nested_widget.setLayout(layout)
        self.nestedStack.insertWidget(self.PAGE_POSTFRAMESELECT, nested_widget)


    def cleanup_page(self):
        """
        Go to pre frame select page and reset variables
        """
        self.nestedStack.setCurrentIndex(self.PAGE_PREFRAMESELECT)
        self.waiting_label.setText("Please wait...")
        pkg = self.replay_widget.currentTool.replayer["name"]
        self.replay_widget.adb.command(["am", "kill-all"], run_with_sudo=True)
        self.replay_widget.adb.command(["am", "force-stop", pkg], run_with_sudo=True)
        if self.expected_local_output:
            Path(self.expected_local_output).unlink(missing_ok=True)
        self.expected_local_output = None
        self.selected1 = None
        self.selected3 = None
        self.frames = None
        self.number1.setChecked(False)
        self.number3.setChecked(False)


    def continueToFastForward(self):
        """
        Emit signal to continue to fast forward page
        """
        self.goto_fastforward_signal.emit()
        self.next_signal.emit(PageIndex.FAST_FORWARD)
