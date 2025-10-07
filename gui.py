#!/usr/bin/python3

import shutil
import os

from pathlib import Path
from core.adb_thread import AdbThread
from core.page_navigation import PageIndex
from core.widgets.connect_device import UIConnectDevice
from core.widgets.base import UiBaseWidget
from core.widgets.trace import UiTraceWidget
from core.widgets.replay_settings import UiReplaySettings
from core.widgets.replay import UiReplayWidget
from core.widgets.framerange import UiFrameRangeWidget
from core.widgets.trace_importer import UiTraceImportWidget
from core.widgets.fast_forward import UiFastForwardWidget
from core.widgets.frame_selection import UiFrameSelectionWidget
from core.config import ConfigSettings, ConfigGfxrWindow, ConfigPatraceWindow

from functools import partial
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QStackedWidget, QGroupBox, QStyle, QLabel, QVBoxLayout,
                               QMessageBox, QHBoxLayout, QPushButton, QSizePolicy)

from adblib import print_codes


class MainWindow(QMainWindow):
    def __init__(self, adb, plugins):
        """
        Initialize the class
        """
        super().__init__()
        # TODO implement error handling
        self.setWindowTitle("Android Tracing")
        icon = QWidget().style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon)
        self.setWindowIcon(icon)
        self.showMaximized()

        self.adb = adb
        self.plugins = plugins
        self.config = ConfigSettings()

        self.currentApp = ""
        self.currentTrace = ""
        self.skip_replay = False
        self.remove_unsupported_extensions_on_replay = True
        self.is_importing = False

        self.currentTool = None
        self.trace = None
        self.widget = QWidget()

        self.loadUiWidgets()
        self.setUpPageConnections()
        self.setUpProgressBar()
        self.setUpLayouts()

        self.loadMenubar()
        self.cleanupTmpReplayImgDir()

    def set_page(self, index):
        """
        Clean up functionality between pages

        Args:
            index = index of page wished to be loaded
        """
        current_index = self.stacked.currentIndex()
        self.stacked.setCurrentIndex(index)

        if index < current_index:
            # Always load import window at import page
            if index == PageIndex.TRACE_IMPORTER:
                self.pages[index].traceImport()
            # clean up all advanced pages
            pages_to_clean = {i for i in self.visited_pages if i > index}
            for i in pages_to_clean:
                self.pages[i].cleanup_page()

            self.visited_pages = {i for i in self.visited_pages if i < index}
        self.visited_pages.add(index)

        for i, btn in enumerate(self.step_buttons):
            btn.setChecked(i == index)
            btn.setEnabled(i in self.visited_pages or i == index)
            btn.setProperty("current", i in self.visited_pages and i == index)
            btn.setProperty("future", i not in self.visited_pages and i != index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def loadUiWidgets(self):
        """
        Initialise the different pages and add it to a dictionary
        """
        self.stacked = QStackedWidget()
        self.step_buttons = []
        self.visited_pages = set()
        self.widget_connect = UIConnectDevice(self.adb)
        self.widget_base = UiBaseWidget(self.adb, self.trace)
        self.widget_trace = UiTraceWidget(self.adb, self.plugins)
        self.widget_replay = UiReplayWidget(self.adb, self.plugins)
        self.widget_framerange = UiFrameRangeWidget()
        self.widget_loading = self.loadingWidget()
        self.widget_import = UiTraceImportWidget(self.adb, self.trace, self.plugins)
        self.widget_frameselection = UiFrameSelectionWidget()
        self.widget_fastforward = UiFastForwardWidget()

        self.pages_dict = {
            "Connect Device": self.widget_connect,  # index 0
            "Import or Generate": self.widget_base,  # index 1
            "Import Trace": self.widget_import,  # index 2
            "Generate Trace": self.widget_trace,  # index 3
            "Verify Trace": self.widget_replay,  # index 4
            "FrameRange": self.widget_framerange,  # index 5
            "FrameSelection": self.widget_frameselection, # index 6
            "FastForward": self.widget_fastforward, # index 7
        }

    def setUpPageConnections(self):
        """
        Add pages to the stack and set up connections between different pages
        """

        self.pages = []

        for i, page in enumerate(self.pages_dict.values()):
            self.pages.append(page)
            self.stacked.addWidget(page)
            if i > 0:
                page.back_signal.connect(partial(self.set_page, i - 1))
            if i < len(self.pages_dict) - 1:
                page.next_signal.connect(self.set_page)

        # ConnectDevice
        self.pages[PageIndex.CONNECT].device_selected.connect(self.move_to_start_widget)

        # base
        self.pages[PageIndex.START].trace_start_signal.connect(self.move_to_trace_widget)
        self.pages[PageIndex.START].trace_import_signal.connect(self.move_to_trace_import_widget)
        # trace
        self.pages[PageIndex.TRACE].goback_signal.connect(lambda: self.set_page(PageIndex.START))
        self.pages[PageIndex.TRACE].loading_signal.connect(lambda: self.stacked.setCurrentIndex(PageIndex.LOADING))
        self.pages[PageIndex.TRACE].returnfromloading_signal.connect(lambda: self.stacked.setCurrentIndex(PageIndex.TRACE))
        self.pages[PageIndex.TRACE].replay_signal.connect(self.move_to_replay_widget)

        self.pages[PageIndex.TRACE_IMPORTER].export_trace_and_plugin_signal.connect(self.readStateFromImporter)
        self.pages[PageIndex.TRACE_IMPORTER].request_replay_signal.connect(self.move_to_replay_widget_on_import)
        self.pages[PageIndex.TRACE_IMPORTER].skip_replay_signal.connect(self.gotoFramerangeSelection)
        self.pages[PageIndex.TRACE_IMPORTER].goback_signal.connect(lambda: self.set_page(PageIndex.START))

        self.pages[PageIndex.REPLAY].frame_range_signal.connect(self.gotoFramerangeSelection)
        self.pages[PageIndex.FRAME_SELECTION].goto_fastforward_signal.connect(self.goToFastForward)

        self.pages[PageIndex.FRAMERANGE].gotoframeselection_signal.connect(self.finishRangeSelection)

    def setUpProgressBar(self):
        """
        Set up progress bar shown at the bottom
        """
        self.progress_bar = QHBoxLayout()
        for index, title in enumerate(self.pages_dict.keys()):
            btn = QPushButton(title)
            btn.setObjectName("progressBtn")
            btn.setChecked(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(partial(self.set_page, index))
            self.step_buttons.append(btn)
            self.progress_bar.addWidget(btn)


    def setUpLayouts(self):
        """
        Set up main layout, including the stack of pages
        """
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.stacked)
        progress_group = QGroupBox("Progress")
        progress_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                margin-top: 20px;
                background-color: #f0f0f0;
                padding: 10px;
                font-size: 16px;
            }
            QGroupBox QPushButton {
                border: 2px solid #aaa;
                background-color: #eee;
                padding: 5px;
                font-size: 18px;
            }
            QGroupBox QPushButton[current="true"] {
                background-color: #eee;
                border: 2px solid #676767;
                font
            }
            QGroupBox QPushButton[future="true"] {
                background-color: #ddd;
                color: #999;
                border-style: dashed;
            }
        """)

        progress_group.setLayout(self.progress_bar)
        main_layout.addWidget(progress_group)
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        self.set_page(PageIndex.CONNECT)

    def goToFastForward(self):
        """
        Go to fast forward from frame selection
        """
        self.widget_fastforward.replay_widget = self.widget_frameselection.replay_widget
        self.widget_fastforward.frames = self.widget_frameselection.frame_num_list
        self.widget_fastforward.framerange_start = self.widget_frameselection.framerange_start
        self.widget_fastforward.framerange_end = self.widget_frameselection.framerange_end
        self.stacked.setCurrentIndex(PageIndex.FAST_FORWARD)

    def gotoFramerangeSelection(self):
        """
        Go to Frame Range Selection from importer or replay
        """
        self.widget_framerange.getImages()
        self.widget_framerange.replay_widget = self.widget_replay
        self.stacked.setCurrentIndex(PageIndex.FRAMERANGE)

    def finishRangeSelection(self):
        """
        Go to frame selection from frame range
        """
        self.widget_frameselection.framerange_start = self.widget_framerange.current_range_start
        self.widget_frameselection.framerange_end = self.widget_framerange.current_range_end
        self.widget_frameselection.replay_widget = self.widget_replay
        self.stacked.setCurrentIndex(PageIndex.FRAME_SELECTION)

    def readStateFromImporter(self):
        """
        Update variables based on checked boxes and call function to configure replay widget
        """
        self.stacked.setCurrentIndex(PageIndex.REPLAY)
        self.currentTool = self.widget_import.target_plugin_name
        self.currentTrace = Path(self.widget_import.trace)
        self.skip_replay = self.widget_import.skip_replay
        self.remove_unsupported_extensions_on_replay = self.widget_import.remove_unsupported_extensions_on_replay
        self.is_importing = True

        # TODO: Set this properly
        target_path = Path("/sdcard/devlib-target/")
        self.adb.clear_logcat()
        self.adb.command(["mkdir", "-p", target_path], True)
        stdout, _ = self.adb.command(['ls', target_path / self.currentTrace.name], run_with_sudo=False, errors_handled_externally=True)

        if stdout:
            trace_exists_on_device = True
        else:
            trace_exists_on_device = False

        if (not trace_exists_on_device) or self.widget_import.override_trace_if_existing:
            self.helper_thread = AdbThread()
            self.helper_thread.fileHandler(adb=self.adb, file=self.currentTrace, path=target_path, track=self.widget_import.delete_trace_on_shutdown, action="push")
        elif trace_exists_on_device:
            print(f"[ INFO ] Skipping upload of trace file: {self.currentTrace} to device folder {target_path} because it already exists on the target device")
        self.currentTrace = target_path / os.path.basename(self.currentTrace)

        print(f"[ INFO ] Trace path on device is: {self.currentTrace}")

        self.configureReplayWidget()

    def loadMenubar(self):
        """ Loads the menu bar """
        # Adds menubar with items at the top of the main window
        # TODO: Only allow imports after device is selected
        # TODO Add application-specific settings in future, i.e various appearance settings
        settingsMenu = self.menuBar().addMenu("&Settings")
        # Menu for configuring various paths
        configMenu = settingsMenu.addMenu("&Config")
        configPatrace = QAction("Configure &PAtrace...", self, triggered=lambda: self.get_config("pat"))
        configGfxr = QAction("Configure &GFXReconstruct...", self, triggered=lambda: self.get_config("gfxr"))
        configMenu.addAction(configPatrace)
        configMenu.addAction(configGfxr)

        # TODO Add documentation and help guide
        helpMenu = self.menuBar().addMenu("&Help")
        aboutQt = QAction("About &Qt", self, triggered=QApplication.aboutQt)
        helpMenu.addAction(aboutQt)

    def get_config(self, tool):
        # Read config values from config.ini
        tool_paths = self.config.get_config().get('Paths')
        self.patpath = tool_paths.get('pat_path')
        self.gfxrpath = tool_paths.get('gfxr_path')
        if tool == 'pat':
            self.configWindow = ConfigPatraceWindow(self.patpath)
        elif tool == 'gfxr':
            self.configWindow = ConfigGfxrWindow(self.gfxrpath)

    def configureReplayWidget(self):
        """ Configure replay widget """
        self.widget_replay.setCurrentTool(self.plugins[self.currentTool])
        self.widget_replay.setCurrentTrace(self.currentTrace)

    def showLoadingScreen(self):
        """ Shows a loading screen """
        # Show the loading screen
        self.stacked.setCurrentIndex(PageIndex.LOADING)
        # Makes sure the loading screen is actually displayed
        QApplication.processEvents()

    def move_to_start_widget(self):
        """ Catches a signal (trace_start_signal) and moves to the tracing widget"""
        self.adb = self.widget_connect.adb
        self.widget_replay.adb = self.adb
        self.widget_base.adb = self.adb
        self.widget_trace.adb = self.adb
        self.widget_import.adb = self.adb
        self.showLoadingScreen()
        self.stacked.setCurrentIndex(PageIndex.START)

    def move_to_trace_widget(self):
        """ Catches a signal (trace_start_signal) and moves to the tracing widget"""
        self.showLoadingScreen()
        self.pages[PageIndex.TRACE].update_content()
        self.stacked.setCurrentIndex(PageIndex.TRACE)

    def move_to_trace_import_widget(self):
        """ Catches a signal (trace_import_signal) and moves to the trace import widget"""
        self.showLoadingScreen()
        self.widget_import.traceImport()
        self.stacked.setCurrentIndex(PageIndex.TRACE_IMPORTER)

    def move_to_replay_widget(self):
        """ Catches a signal (replay_signal) and moves to the replay widget """
        self.showLoadingScreen()
        self.currentTool = self.pages[PageIndex.TRACE].currentTool
        self.currentTrace = self.pages[PageIndex.TRACE].currentTrace
        self.is_importing = False
        self.skip_replay = False
        self.move_to_replay_widget_on_import()

    def move_to_replay_widget_on_import(self):
        """ Catches a signal (replay_signal) and moves to the replay widget but assume current tool and trace have been set on import """
        self.cleanupTmpReplayImgDir()
        if not self.is_importing:
            _pull_helper = AdbThread()
            _pull_helper.fileHandler(adb=self.adb, file=self.currentTrace, path="tmp", action="pull")
        if self.skip_replay:
            return

        self.stacked.setCurrentIndex(PageIndex.REPLAY)
        self.showLoadingScreen()
        self.configureReplayWidget()
        extra_args = []
        if self.remove_unsupported_extensions_on_replay and self.currentTool == 'gfxreconstruct':
            extra_args = ["--remove-unsupported"]
        QApplication.processEvents()
        self.replaySettings = UiReplaySettings()
        if self.replaySettings.exec():
            interval = self.replaySettings.getInterval()
            print("[ INFO ] Generating screenshots..")
            out_path = self.config.get_config()['Paths']['img_path']
            # Go to replay widget
            # self.stacked.setCurrentIndex(PageIndex.REPLAY)
            self.widget_replay.replay(screenshots="interval", extra_args=extra_args, local_dir=out_path, interval=interval)

        self.showLoadingScreen()
        if self.widget_replay.errorsLastReplay:
            print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Replay for was not clean, errors occurred!")
            msg = QMessageBox.question(self, '', "Replay for was not clean, errors occurred! Do you wish to retry replay?", QMessageBox.Yes | QMessageBox.No)
            ret = msg
            if ret == QMessageBox.Yes:
                self.set_page(PageIndex.REPLAY)
                self.move_to_replay_widget_on_import()
            else:
                self.set_page(PageIndex.START)
                self.move_to_start_widget()
                return
        self.widget_replay.gotoframe_range_signal()



    def loadingWidget(self):
        """ Sets up the loading widget """
        loading_widget = QWidget()
        loading_layout = QVBoxLayout()
        loading_label = QLabel("Loading...")

        loading_layout.addWidget(loading_label)
        loading_layout.setAlignment(Qt.AlignCenter)

        loading_widget.setLayout(loading_layout)
        return loading_widget

    def cleanupTmpReplayImgDir(self):
        """
        Cleans up all files in the tmp/replay_imgs folder
        """
        path = Path(self.config.get_config()['Paths']['img_path'])
        if path.exists():
            print("[ INFO ] Deleting local image directory...")
            shutil.rmtree(self.config.get_config()['Paths']['img_path'])
