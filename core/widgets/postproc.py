import json
import os
from pathlib import Path
from core.frame_selection import select_frames

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QCheckBox, QScrollArea, QStyle, QMessageBox

from core.page_navigation import PageNavigation, PageIndex


class ProcOption():
    def __init__(self, dict):
        self.id = dict.get('id')
        self.title = dict.get('title')
        self.isDefault = dict.get('default')
        self.tools = dict.get('tools')
        self.desc = dict.get('desc')
        self.required = dict.get('required')


class UiPostProcWidget(PageNavigation):
    goback_signal = Signal()
    abort_postproc_signal = Signal()

    def __init__(self, replay_widget):
        super().__init__()
        # This makes a hard dependency, but is probably the best way to solve it?
        self.replay_widget = replay_widget
        self.error = None
        self.checkbox_map = {}

        self.framerange_start = 0
        self.framerange_end = 0

        self.selected_frames = []

        self.setupWidgets()
        self.setupLayouts()

    def cleanup_page(self):
        self.framerange_start = 0
        self.framerange_end = 0

    def options_list(self):
        option_list = list()
        file_path = Path(__file__).parents[1].resolve() / "proc_options.json"
        with open(file_path, "r") as input:
            options = json.load(input)
            for option in options['postprocess_options']:
                option_list.append(ProcOption(option))

        return option_list

    def setupWidgets(self):
        self.option_widget = QWidget()
        self.header_label = QLabel("Select post-process option(s)")
        self.error_label = QLabel("Error:")
        self.cont_button = QPushButton("Continue")
        self.abort_button = QPushButton("Abort")
        self.cont_button.clicked.connect(self.run_postproc)
        self.abort_button.clicked.connect(self.abort_postproc)

        self.back_button = QPushButton()
        pixmapi = QStyle.StandardPixmap.SP_ArrowBack
        icon = QWidget().style().standardIcon(pixmapi)
        self.back_button.setIcon(icon)
        self.back_button.setFlat(True)
        self.back_button.clicked.connect(self.go_back)

    def setupLayouts(self):
        # TODO handle different states depending on trace/tool/previous page

        button_layout = QHBoxLayout()
        v_layout = QVBoxLayout()

        button_layout.addWidget(self.abort_button)
        button_layout.addWidget(self.cont_button)
        v_layout.addWidget(self.back_button)

        if self.error:
            v_layout.addWidget(self.error_label)
        v_layout.addWidget(self.header_label)
        v_layout.addWidget(self.createScrollArea())
        v_layout.addLayout(button_layout)
        self.setLayout(v_layout)

    def createScrollArea(self):
        option_layout = QVBoxLayout()
        option_scroll = QScrollArea()
        option_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        option_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        options = self.options_list()
        for option in options:
            checkbox = QCheckBox(f"{option.title}\n{option.desc}")
            option_layout.addWidget(checkbox)
            self.checkbox_map[option.id] = checkbox

        self.option_widget.setLayout(option_layout)
        option_scroll.setWidget(self.option_widget)
        option_scroll.setWidgetResizable(True)

        return option_scroll

    def run_postproc(self):

        # print(f"[ INFO ] Copying trace with path '{self.currentTrace}' to 'results' folder")
        # if not os.path.exists("results"):
        #    os.makedirs("results")
        # self.plugins[self.currentTool].trace_get_output(files=[self.currentTrace], output_dir="results")

        # Frame selection
        if self.checkbox_map["frameselect"].isChecked():
            results = self.replay_widget.replay(
                screenshots=False,
                hwc=True,
                repeat=1,
                fastforward=False,
                from_frame=self.framerange_start,
                to_frame=self.framerange_end
            )
            desired_output_dir = self.replay_widget.currentTool.local_output_dir / "results/frame_selection"
            if not os.path.exists(desired_output_dir):
                os.makedirs(desired_output_dir)

            print(f"[ INFO ] Storing frame selection results in: {str(desired_output_dir)}")

            if not results.get("hwc_path"):
                print(f"[ ERROR ] Frame selection post processing failed. No HWC results found after replay.")
            else:
                self.replay_widget.currentTool.trace_get_output(files=results["hwc_path"], output_dir=desired_output_dir)

                expected_local_output = os.path.join(desired_output_dir, os.path.basename(results["hwc_path"]))
                if not os.path.exists(expected_local_output):
                    print(f"[ ERROR ] HWC data generation failed, expected output does not exist: {expected_local_output}")
                else:
                    print(f"[ INFO ] HWC data generated successfully! Stored locally in: {expected_local_output}")

                selected_frame_data_single_frame, selected_frame_data_three_frames = select_frames(
                    expected_local_output,
                    self.framerange_start,
                    self.framerange_end
                )

                frame_selection_json_path_single = desired_output_dir / "selected_frames_single.json"
                frame_selection_json_path_triple = desired_output_dir / "selected_frames_triple.json"

                with open(frame_selection_json_path_single, 'w') as outfile:
                    json.dump(selected_frame_data_single_frame, outfile, indent=2)

                with open(frame_selection_json_path_triple, 'w') as outfile:
                    json.dump(selected_frame_data_three_frames, outfile, indent=2)

                print(f"[ INFO ] Successfully selected single frame:")
                print(json.dumps(selected_frame_data_single_frame, indent=2))
                print("\n\n[ INFO ] And three frame set: ")
                print(json.dumps(selected_frame_data_three_frames, indent=2))

                print(f"[ INFO ] Results stored in: {str(desired_output_dir)}/selected_frames_*.json")
                self.selected_frames = selected_frame_data_single_frame

        # Fastforward
        if self.checkbox_map["fastforward"].isChecked():
            # TODO: move to separate page and show progress
            msg = QMessageBox()
            msg_text = " Generating FF traces is currently Disabled."
            msg.setText(msg_text)
            msg.exec()
            return

            if self.checkbox_map["frameselect"].isChecked():
                print("[ INFO ] Starting fastforwarding from frame selection...")
                selected_frames = []
                with open(frame_selection_json_path_single, 'r') as file:
                    data_single = json.load(file)
                selected_frames.extend([i['frame'] for i in data_single])
                with open(frame_selection_json_path_triple, 'r') as file:
                    data_triple = json.load(file)
                selected_frames.extend([i['frame'] for i in data_triple if i not in selected_frames])

                results = {}
                for frame in selected_frames:
                    results = self.replay_widget.replay(
                        screenshots=False,
                        repeat=1,
                        fastforward=True,
                        from_frame=frame,
                        to_frame=frame + 9999,
                        prev_results=results
                    )
                    print(f"[ INFO ] Successfully generated ff trace at: tmp/{results['ff_trace'].name}")
                    if results.get('ff_hwc_diffs')['diffs']:
                        with open(f'tmp/hwc/ff_hwc_diff_ff{frame}.json', 'w') as outfile:
                            json.dump(results.get('ff_hwc_diffs'), outfile, indent=2)
                        print(f"[ INFO ] HWC Diff results stored in: tmp/hwc/ff_hwc_diff_ff{frame}.json")
                    else:
                        print(f"[ INFO ] No HWC diffs detected!")
                print(f"[ INFO ] Successfully generated ff traces for selected frames: \"{selected_frames}\"")
                return
            else:
                print("[ INFO ] Starting fastforwarding from frame range...")
                results = self.replay_widget.replay(
                    screenshots=False,
                    repeat=1,
                    fastforward=True,
                    from_frame=self.framerange_start,
                    to_frame=self.framerange_end
                )
                print(results['ff_trace'])
                print(f"[ INFO ] Successfully generated ff trace at: tmp/{results['ff_trace'].name}")
                if results.get('ff_hwc_diffs')['diffs']:
                    with open('tmp/hwc/ff_hwc_diffs.json', 'w') as outfile:
                        json.dump(results.get('ff_hwc_diffs'), outfile, indent=2)
                    print(f"[ INFO ] HWC Diff results stored in: tmp/hwc/ff_hwc_diffs.json")
                else:
                    print(f"[ INFO ] No HWC diffs detected!")
                return

        # TODO add functions for each post-processing option
        self.postproc_widget = QWidget()
        # TODO remove demo label
        demo_label = QLabel("This is a demo. Wait 5 seconds for page to change.")
        run_label = QLabel("Running post-processing steps...")
        button = QPushButton("Ok")
        button.clicked.connect(self.abort_postproc)
        v_layout = QVBoxLayout()
        v_layout.addWidget(demo_label)
        v_layout.addWidget(run_label)
        v_layout.addWidget(button)
        v_layout.setAlignment(Qt.AlignCenter)
        button.hide()

        self.setLayout(v_layout)

        # TODO remove demo timer, add function to handle result output(s)
        run_label.setText("Post-processing complete!\nResult output: <path>")
        demo_label.hide()
        button.show()

    def abort_postproc(self):
        self.next_signal.emit(PageIndex.START)
        self.abort_postproc_signal.emit()

    def go_back(self):
        self.next_signal.emit(PageIndex.FRAMERANGE)
        self.goback_signal.emit()
