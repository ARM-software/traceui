from core.page_navigation import PageNavigation, PageIndex
from core.frame_selection import select_frames
from core.adb_thread import AdbThread
from pathlib import Path
from adblib import print_codes
import os
import json

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QFormLayout, QCheckBox, QPushButton, QMessageBox, QStackedWidget, QButtonGroup, QComboBox, QLineEdit, QHBoxLayout


class UiFrameSelectionWidget(PageNavigation):
    PAGE_PREFRAMESELECT = 0
    PAGE_WRITEFRAMES = 1
    PAGE_LOADING = 2
    PAGE_CONFIRM_FRAMES = 3
    PAGE_POSTFRAMESELECT = 4

    goto_fastforward_signal = Signal()
    goback_signal = Signal()

    def __init__(self):
        super().__init__()
        self.replay_widget = None
        self.frames = None
        self.expected_local_output = None
        self.framerange_start = 0
        self.framerange_end = 0
        self.list_of_frames = None
        self.setupWidgets()
        self.setupLayouts()
        self.setUpWaiting()
        self.setUpFinished()
        self.setUpWritingFrames()
        self.setUpConfirmFrames()
        self.local_output_dir = Path(f'outputs/traces/')



    def setupWidgets(self):
        """
        Set up widgets, pre-frame selection
        """
        self.label = QLabel("How many representative frames for the chosen range is desired")
        self.label.setAlignment(Qt.AlignCenter)
        self.dropdown = QComboBox()
        self.dropdown.addItems(["1", "2", "3"])
        self.button = QPushButton("Continue")
        self.button.clicked.connect(self.update)
        self.know_frames = QCheckBox("I already know which frame number(s) I would like to use")
        self.nonmali_button = QPushButton("Go Back")
        self.nonmali_button.clicked.connect(self.goback)


    def setupLayouts(self):
        """
        Set up layout for page pre frame selection
        """
        self.nestedStack = QStackedWidget()
        layout = QVBoxLayout()
        preselect_widget = QWidget()
        layout.addWidget(self.label)
        layout.addWidget(self.dropdown)
        layout.addWidget(self.know_frames)
        layout.addWidget(self.button)
        layout.addWidget(self.nonmali_button)
        self.nonmali_button.hide()
        layout.setAlignment(Qt.AlignCenter)
        preselect_widget.setLayout(layout)
        self.nestedStack.insertWidget(self.PAGE_PREFRAMESELECT, preselect_widget)

        top_layout = QVBoxLayout(self)
        top_layout.addWidget(self.nestedStack)
        self.setLayout(top_layout)

        self.nestedStack.setCurrentIndex(self.PAGE_PREFRAMESELECT)

    def goback(self):
        self.next_signal.emit(PageIndex.FRAMERANGE)
        self.goback_signal.emit()

    def setUpWritingFrames(self):
        """
        Set up page for writing frame
        """
        label_informing = QLabel("Please write frame numbers you would like to use")
        label_informing.setStyleSheet("font-size: 18px; font-weight: bold; color: #444;")
        label_format = QLabel("Format: single number or comma separeted for multiple frames. eg 5,10,15")
        label_informing.setAlignment(Qt.AlignCenter)
        label_format.setAlignment(Qt.AlignCenter)
        self.frame_input = QLineEdit()
        button_continue = QPushButton("Continue")
        button_continue.clicked.connect(self.getFrameStringInput)
        button_goback = QPushButton("Go Back")
        button_goback.clicked.connect(lambda: self.nestedStack.setCurrentIndex(self.PAGE_PREFRAMESELECT))

        layout = QVBoxLayout()
        layout_widget = QWidget()
        layout.addStretch()
        layout.addWidget(label_informing)
        layout.addWidget(label_format)
        layout.addWidget(self.frame_input)
        layout.addWidget(button_continue)
        layout.addWidget(button_goback)
        layout.addStretch()

        layout_widget.setLayout(layout)
        self.nestedStack.insertWidget(self.PAGE_WRITEFRAMES, layout_widget)

    def getFrameStringInput(self):
        """
        Read input field for wanted frame(s) and validate
        """
        msg = QMessageBox()

        string_frame = self.frame_input.text()
        string_list = string_frame.split(",")
        if len(string_list) and string_list[0] == '':
            msg.setText("Incorrect format. Format is 'num1,num2,num3")
            msg.exec()
            return
        int_list = []
        for i in range(len(string_list)):
            try:
                int_list.append(int(string_list[i]))
            except ValueError:
                msg.setText(f"Please only write numbers. Not allowed: {string_list[i]}")
                msg.exec()
                return
            if int_list[i] > self.framerange_end:
                msg.setText(f"Please remain within frame range end, which is {self.framerange_end}.")
                msg.exec()
                return
        if len(int_list) > 3:
            msg.setText(f"Please select no more than three frames")
            msg.exec()
            return
        self.frame_num_list = int_list
        self.nestedStack.setCurrentIndex(self.PAGE_LOADING)
        self.generateConfirmationFrames()
        self.nestedStack.setCurrentIndex(self.PAGE_CONFIRM_FRAMES)

    def setUpConfirmFrames(self):
        """
        Set up page for frame confirmation
        """
        confirm_label = QLabel("Please confirm the selected frames")
        confirm_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #444;")
        confirm_label.setAlignment(Qt.AlignCenter)
        confirm_button = QPushButton("Confirm")
        confirm_button.clicked.connect(lambda: self.nestedStack.setCurrentIndex(self.PAGE_POSTFRAMESELECT))
        redo_button = QPushButton("Redo selection")
        redo_button.clicked.connect(self.cleanup_page)

        self.frames_displayed = QHBoxLayout()
        widget_helper = QWidget()

        widget_helper.setLayout(self.frames_displayed)

        layout = QVBoxLayout()
        layout.addStretch()
        layout_widget = QWidget()
        layout.addWidget(confirm_label)
        layout.addWidget(widget_helper)
        layout.addWidget(confirm_button)
        layout.addWidget(redo_button)
        layout.addStretch()
        layout_widget.setLayout(layout)
        self.nestedStack.insertWidget(self.PAGE_CONFIRM_FRAMES, layout_widget)


    def update(self):
        """
        If amount of frames is selected, set page index to loading and compute the frame(s)
        """
        if not self.detectGpu():
            self.button.hide()
            self.nonmali_button.show()
            self.dropdown.hide()
            self.know_frames.hide()
            self.label.setText("Frame selection is not supported on non-Mali devices!")
            return
        self.frames_amount = int(self.dropdown.currentText())
        if self.know_frames.isChecked():
            self.nestedStack.setCurrentIndex(self.PAGE_WRITEFRAMES)
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

    def fetch_files_from_device(self, files=None, output_dir=None):
        """
        Pulls the files from the device (remote) to the output dir (local).

        Args:
            files (str/list[str]): A path to a file or a list of paths
            output_dir: Local dir where one want the output to be stored, set to default if None

        Returns:
            list[str]: List of all local output file paths
        """
        assert files, "No output file(s)"

        if not isinstance(files, list):
            files = [files]

        outputs = []
        if not output_dir:
            output_dir = self.local_output_dir / Path(self.replay_widget.currentTool.plugin_name)
        for file_path in files:
            print(f"[ INFO ] Fetching result file: {file_path}")
            stdout, _ = self.replay_widget.adb.command(
                [f"if [ -f {file_path} ]; then echo true; else echo false; fi"])
            if stdout == 'true':
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                self.replay_widget.adb.pull(file_path, output_dir)
                outputs.append(output_dir / Path(file_path))
            else:
                print(
                    f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] Result file: {file_path} does not exist on device")

        return outputs

    def _hwcHelper(self, results):
        """
        Generate HWC data
        """
        desired_output_dir = self.local_output_dir / self.replay_widget.currentTool.plugin_name / "results/frame_selection"
        if not os.path.exists(desired_output_dir):
            os.makedirs(desired_output_dir)

        print(f"[ INFO ] Storing frame selection results in: {str(desired_output_dir)}")

        if not results.get("hwc_path"):
            print(f"[ ERROR ] Frame selection post processing failed. No HWC results found after replay.")
        else:
            self.fetch_files_from_device(files=results["hwc_path"], output_dir=desired_output_dir)
            self.expected_local_output = os.path.join(desired_output_dir, os.path.basename(results["hwc_path"]))
            if not os.path.exists(self.expected_local_output):
                print(f"[ ERROR ] HWC data generation failed, expected output does not exist: {self.expected_local_output}")
            else:
                print(f"[ INFO ] HWC data generated successfully! Stored locally in: {self.expected_local_output}")
            return desired_output_dir

    def errorHWCHandeling(self):
        """
        Give user pop up with possible actions if hwc fails
        """
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
            thread_helper = AdbThread()
            thread_helper.fileHandler(adb=self.replay_widget.adb, file=self.replay_widget.currentTrace, path="tmp", action="pull")
            self.cleanup_page()
            self.next_signal.emit(PageIndex.START)
        else:
            self.cleanup_page()
            self.next_signal.emit(PageIndex.START)
        return

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
        )
        desired_output_dir = self._hwcHelper(results)
        if self.expected_local_output is None:
            self.errorHWCHandeling()
            return
        if self.frames_amount:
            print(f"[ INFO ] Selecting {self.frames_amount} frames")
            self.frames = select_frames(self.expected_local_output, self.framerange_start, self.framerange_end, self.frames_amount)
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
        _pull_helper = AdbThread()
        _pull_helper.fileHandler(adb=self.replay_widget.adb, file=self.replay_widget.currentTrace, path=desired_output_dir, action="pull")
        self.location_label.setText(f"Location of trace and selected frame information: {os.getcwd()}/{desired_output_dir}")
        print("[ INFO ] Frame selection is completed.")
        self.frame_num_list = []
        for i in range(len(self.frames)):
            self.frame_num_list.append(self.frames[i]["frame"])

        self.generateConfirmationFrames()

        self.nestedStack.setCurrentIndex(self.PAGE_CONFIRM_FRAMES)

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
        self.frames = None
        self.know_frames.setChecked(False)
        self.frame_num_list = None
        self.frame_input.clear()
        self.cleanUpConfirmationFrames()


    def cleanUpConfirmationFrames(self):
        """
        Clean up widget which displays the frames waiting for confirmation
        """
        while self.frames_displayed.count():
            item = self.frames_displayed.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
            else:
                sub_layout = item.layout()
                if sub_layout is not None:
                    while sub_layout.count():
                        sub_item = sub_layout.takeAt(0)
                        sub_widget = sub_item.widget()
                        if sub_widget:
                            sub_widget.setParent(None)

    def continueToFastForward(self):
        """
        Emit signal to continue to fast forward page
        """
        self.goto_fastforward_signal.emit()
        self.next_signal.emit(PageIndex.FAST_FORWARD)

    def generateConfirmationFrames(self):
        """
        Generate screenshot(s) for confirming frame(s) by replaying and taking screenshots of wanted frames
        """
        self.waiting_label.setText("Getting relevant screenshots. Please wait...")
        if not self.frame_num_list:
            return False
        results = self.replay_widget.replay(
                screenshots = "selecting_frames",
                hwc=False,
                repeat=1,
                fastforward=False,
                from_frame=self.frame_num_list,
                to_frame=max(self.frame_num_list),
                extra_args=[],
        )
        for path in results['screenshot_path']:
            self.replay_widget.adb.pull(path, "tmp")
            path_file = f"tmp/{path.split('/')[-1]}"
            pixmap = QPixmap(path_file)
            if pixmap.isNull():
                print(f"[ INFO ] Unable to load image: {path_file}")
                continue
            if (pixmap.height() >= pixmap.width()):
                scaled_pixmap = pixmap.scaledToHeight(700)
            else:
                scaled_pixmap = pixmap.scaledToWidth(700)
            img = QLabel()
            img.setPixmap(scaled_pixmap)
            img.setAlignment(Qt.AlignCenter)

            label_frame = QLabel(f"Frame {path.split('_')[-1].split('.')[0]}")
            label_frame.setAlignment(Qt.AlignCenter)
            layout = QVBoxLayout()
            layout.addWidget(img)
            layout.addWidget(label_frame)

            total_widget = QWidget()
            total_widget.setLayout(layout)
            self.frames_displayed.addWidget(total_widget)
        _helper_string =  ", ".join([f"{f}" for f in self.frame_num_list])
        self.frame_label.setText(f"Selected frame(s): {_helper_string}")
