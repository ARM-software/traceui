import os
import shutil

from core.config import ConfigSettings
from core.traceimport import ImportWindow

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QMessageBox
from core.page_navigation import PageNavigation, PageIndex

from adblib import print_codes


class UiTraceImportWidget(PageNavigation):

    export_trace_and_plugin_signal = Signal()
    request_replay_signal = Signal()
    skip_replay_signal = Signal()
    goback_signal = Signal()

    def __init__(self, adb, trace, plugins):
        """
        Initializes the trace import widget

        Args:
            adb (obj): connected device
            trace (str): path to trace
            plugins (dict): possible plugins
        """
        super().__init__()
        self.adb = adb
        self.trace = trace

        self.device_window = None
        self.plugins = plugins
        self.target_plugin_name = None
        self.target_plugin = None
        self.setupWidgets()
        self.setupLayouts()

    def cleanup_page(self):
        """
        Clean up page and frees variables
        """
        self.trace = None
        self.target_plugin = None
        self.skip_replay = None
        self.importWindow.close()
        self.importWindow = None

    def cleanUpImages(self):
        if os.path.isdir("tmp/replay_imgs"):
            shutil.rmtree("tmp/replay_imgs")

    def setLabel(self, new_text):
        """ Set new label text

        Args:
            new_text (string): new text for the label
        """
        self.header_label.setText(new_text)

    def setupWidgets(self):
        """
        Set up main screen widgets
        """
        self.header_label = QLabel("Importing trace...")
        self.header_label.setAlignment(Qt.AlignCenter)

    def setupLayouts(self):
        """
        Set layout of the import widget
        """
        h_layout = QHBoxLayout()
        v_layout = QVBoxLayout()

        v_layout.addWidget(self.header_label)
        v_layout.addLayout(h_layout)
        v_layout.setAlignment(Qt.AlignCenter)

        self.setLayout(v_layout)

    def traceImport(self):
        """
        Open import window and respond to actions
        """
        self.importWindow = ImportWindow()
        self.importWindow.button.clicked.connect(self.update)
        self.importWindow.killed.connect(self.goback)

    def goback(self):
        """
        Emit signal to go back to previous page
        """
        self.goback_signal.emit()

    def update(self):
        """
        Set variables based on checkboxes and gets valid plugin name
        """
        self.cleanUpImages()
        self.trace = self.importWindow.getTrace()
        if not self.trace:
            print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Trace input empty, please provide a trace path")
            msg = QMessageBox()
            msg.setText("Please provide a file")
            msg.exec()
            self.cleanup_page()
            return
        elif not os.path.getsize(self.trace):
            print(f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] File is empty. Please select non-empty trace file")
            msg = QMessageBox()
            msg.setText("The provided file was empty. Please provide a non-empty trace file")
            msg.exec()
            self.cleanup_page()
            return

        self.override_trace_if_existing = self.importWindow.overrideIfExisting()
        self.skip_replay = self.importWindow.skipReplay()
        self.delete_trace_on_shutdown = self.importWindow.deleteTraceOnShutdown()
        self.remove_unsupported_extensions_on_replay = self.importWindow.removeUnsupportedExtensions()

        trace_suffix = self.trace.split("/")[-1].split(".")[-1]
        plugin = None
        for key, value in self.plugins.items():
            if trace_suffix == getattr(value, 'suffix', None):
                plugin = value
                break

        if plugin is None:
            print(f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] Failed to find valid plugin for trace with suffix: {trace_suffix}")
            raise ValueError(f"Failed to find valid plugin for trace with suffix: {trace_suffix}")

        ConfigSettings().update_config('Paths', f'{str(plugin.suffix)}_path', str(plugin.basepath))

        self.postDeviceSelected()

    def postDeviceSelected(self):
        """
        Set compatible plugin and go to FrameRange or Replay page
        """
        trace_suffix = os.path.splitext(self.trace)[-1].strip(".")
        for plugin_name, plugin in self.plugins.items():
            if trace_suffix == getattr(plugin, 'suffix', None):
                print(f"[ INFO ] Selected plugin: {plugin_name} which is compatible with the imported trace")
                self.target_plugin = plugin
                self.target_plugin_name = plugin_name
                break
        if not self.target_plugin:
            raise Exception(f"Failed to find a valid plugin for trace with name: {self.trace}")
        self.export_trace_and_plugin_signal.emit()
        if self.skip_replay:
            self.next_signal.emit(PageIndex.FRAMERANGE)
            self.skip_replay_signal.emit()
        else:
            self.next_signal.emit(PageIndex.REPLAY)
            self.request_replay_signal.emit()

    def connect_device(self):
        pass
