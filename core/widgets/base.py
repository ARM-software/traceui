from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from core.page_navigation import PageNavigation, PageIndex
from core.widgets.connect_device import UIConnectDevice

import os
import shutil

class UiBaseWidget(PageNavigation):
    trace_start_signal = Signal()
    trace_import_signal = Signal()
    postproc_signal = Signal()

    def __init__(self, adb, trace):
        """
        Initialize the base

        Args:
            adb: Connected devices
            trace (str): Path to trace
        """
        super().__init__()
        self.adb = adb
        self.trace = trace
        self.device_window = None
        self.setupWidgets()
        self.setupLayouts()


    def cleanup_page(self):
        """
        Reset device window
        """
        self.device_window = None

    def setupWidgets(self):
        """
        Set up widgets on start page
        """
        self.header_label = QLabel("Select Action")
        self.header_label.setAlignment(Qt.AlignCenter)

        self.import_button = QPushButton("Import trace")
        self.tracing_button = QPushButton("Generate trace")
        self.tracing_button.clicked.connect(lambda: self.traceStart())
        self.import_button.clicked.connect(lambda: self.traceImport())

    def setupLayouts(self):
        """
        Set layout of start page
        """
        h_layout = QHBoxLayout()
        v_layout = QVBoxLayout()

        h_layout.addWidget(self.import_button)
        h_layout.addWidget(self.tracing_button)
        v_layout.addWidget(self.header_label)
        v_layout.addLayout(h_layout)
        v_layout.setAlignment(Qt.AlignCenter)

        self.setLayout(v_layout)

    def traceImport(self):
        """
        Emit signal to trace import page
        """
        self.trace_import_signal.emit()
        self.next_signal.emit(PageIndex.TRACE_IMPORTER)

    def traceStart(self):
        """
        Check if device is connected and open "connect device" page if not
        """
        if self.adb.device:
            self.trace_start_signal.emit()
            self.next_signal.emit(PageIndex.TRACE)
        else:
            self.connect_device()

    def connect_device(self):
        """
        Set device
        """
        self.device_window = UIConnectDevice(self.adb)
        self.device_window.device_selected.connect(self.traceStart)
