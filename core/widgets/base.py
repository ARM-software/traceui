from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QDialog, QFormLayout, QLineEdit
from core.page_navigation import PageNavigation, PageIndex
from core.widgets.connect_device import UIConnectDevice

class UiBaseWidget(PageNavigation):
    DEFAULT_REPLAY_WORKING_DIR = "/sdcard/devlib-target"
    DEFAULT_CAPTURE_ROOT_BASE = "/data"
    DEFAULT_DEVICE_LAYER_BASE = "/data/local/debug"

    trace_start_signal = Signal()
    trace_import_signal = Signal()
    postproc_signal = Signal()
    replay_dir_changed = Signal(str)
    capture_base_changed = Signal(str)
    layer_base_changed = Signal(str)

    def __init__(self, adb, trace, replay_working_dir, capture_root_base="/data", device_layer_base="/data/local/debug"):
        """
        Initialize the base

        Args:
            adb: Connected devices
            trace (str): Path to trace
        """
        super().__init__()
        self.adb = adb
        self.trace = trace
        self.replay_working_dir = replay_working_dir
        self.capture_root_base = capture_root_base
        self.device_layer_base = device_layer_base
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
        app_font = QApplication.font()
        self.header_label = QLabel("Select Action")
        header_font = QFont(app_font)
        header_font.setBold(True)
        self.header_label.setFont(header_font)
        self.header_label.setAlignment(Qt.AlignCenter)

        self.button_font = QFont(app_font)

        self.import_button = QPushButton("Import trace")
        self.tracing_button = QPushButton("Generate trace")
        for btn in (self.import_button, self.tracing_button):
            self._configure_primary_button(btn)
        self.tracing_button.clicked.connect(lambda: self.traceStart())
        self.import_button.clicked.connect(lambda: self.traceImport())
        self.replay_dir_button = QPushButton("Configure device working directory")
        self._configure_primary_button(self.replay_dir_button, minimum_width=260)
        self.replay_dir_button.clicked.connect(self._handle_replay_dir_change)

    def setupLayouts(self):
        """
        Set layout of start page
        """
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.replay_dir_button, alignment=Qt.AlignLeft)
        top_layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.tracing_button)

        v_layout = QVBoxLayout()
        v_layout.addLayout(top_layout)
        v_layout.addStretch()
        v_layout.addWidget(self.header_label, alignment=Qt.AlignCenter)
        v_layout.addLayout(button_layout)
        v_layout.addStretch()

        self.setLayout(v_layout)

    def _configure_primary_button(self, button: QPushButton, minimum_width: int = 0):
        button.setFont(self.button_font)
        button.setMinimumHeight(44)
        if minimum_width:
            button.setMinimumWidth(minimum_width)
        policy = button.sizePolicy()
        policy.setHorizontalStretch(0)
        button.setSizePolicy(policy)

    def _handle_replay_dir_change(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure device working directory paths")
        dialog.setMinimumWidth(700)

        replay_label = QLabel("Trace replay working directory")
        replay_input = QLineEdit(self.replay_working_dir)
        capture_label = QLabel("Trace capture directory")
        capture_input = QLineEdit(self.capture_root_base)
        layer_label = QLabel("Trace layer directory")
        layer_input = QLineEdit(self.device_layer_base)

        form = QFormLayout()
        form.addRow(replay_label, replay_input)
        form.addRow(capture_label, capture_input)
        form.addRow(layer_label, layer_input)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(dialog.accept)
        reset_btn = QPushButton("Reset")
        def reset_defaults():
            replay_input.setText(self.DEFAULT_REPLAY_WORKING_DIR)
            capture_input.setText(self.DEFAULT_CAPTURE_ROOT_BASE)
            layer_input.setText(self.DEFAULT_DEVICE_LAYER_BASE)
        reset_btn.clicked.connect(reset_defaults)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(reset_btn)
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(btns)
        dialog.setLayout(layout)

        if dialog.exec():
            new_dir = replay_input.text().strip()
            capture_base = capture_input.text().strip()
            layer_base = layer_input.text().strip()
            if new_dir and new_dir != self.replay_working_dir:
                self.replay_working_dir = new_dir
                self.replay_dir_changed.emit(new_dir)
            if capture_base and capture_base != self.capture_root_base:
                self.capture_root_base = capture_base
                self.capture_base_changed.emit(capture_base)
            if layer_base and layer_base != self.device_layer_base:
                self.device_layer_base = layer_base
                self.layer_base_changed.emit(layer_base)

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
