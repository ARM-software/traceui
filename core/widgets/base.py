from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QDialog, QFormLayout, QLineEdit, QCheckBox, QMessageBox
from core.page_navigation import PageNavigation, PageIndex
from core.widgets.connect_device import UIConnectDevice
from core.logger_config import setup_logger

logger = setup_logger("base")


class DeviceCleanupWorker(QObject):
    finished = Signal(bool)

    def __init__(self, adb, working_dir, files):
        super().__init__()
        self.adb = adb
        self.working_dir = str(working_dir)
        self.files = [str(file_path) for file_path in files]

    def run(self):
        success = True
        try:
            self.adb.cleanUpSDCard(self.working_dir, delete=True, files=self.files)
        except Exception:
            logger.exception("Failed to clean up stale device files")
            success = False
        self.finished.emit(success)


class UiBaseWidget(PageNavigation):
    DEFAULT_REPLAY_WORKING_DIR = "/sdcard/devlib-target"
    DEFAULT_CAPTURE_ROOT_BASE = "/data"

    trace_start_signal = Signal()
    trace_import_signal = Signal()
    postproc_signal = Signal()
    replay_dir_changed = Signal(str)
    capture_base_changed = Signal(str)

    def __init__(self, adb, trace, replay_working_dir, capture_root_base="/data"):
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
        self.cleanup_working_dir_enabled = True
        self.device_window = None
        self._cleanup_thread = None
        self._cleanup_worker = None
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
        cleanup_checkbox = QCheckBox("Check device working directory files older than 30 days")
        cleanup_checkbox.setChecked(self.cleanup_working_dir_enabled)

        form = QFormLayout()
        form.addRow(replay_label, replay_input)
        form.addRow(capture_label, capture_input)
        form.addRow("", cleanup_checkbox)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(dialog.accept)
        reset_btn = QPushButton("Reset")
        def reset_defaults():
            replay_input.setText(self.DEFAULT_REPLAY_WORKING_DIR)
            capture_input.setText(self.DEFAULT_CAPTURE_ROOT_BASE)
            cleanup_checkbox.setChecked(True)
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
            self.cleanup_working_dir_enabled = cleanup_checkbox.isChecked()
            if new_dir and new_dir != self.replay_working_dir:
                self.replay_working_dir = new_dir
                self.replay_dir_changed.emit(new_dir)
            if capture_base and capture_base != self.capture_root_base:
                self.capture_root_base = capture_base
                self.capture_base_changed.emit(capture_base)

    def traceImport(self):
        """
        Emit signal to trace import page
        """
        self._cleanup_device_sdcard()
        self.trace_import_signal.emit()
        self.next_signal.emit(PageIndex.TRACE_IMPORTER)

    def traceStart(self):
        """
        Check if device is connected and open "connect device" page if not
        """
        if self.adb.device:
            self._cleanup_device_sdcard()
            self.trace_start_signal.emit()
            self.next_signal.emit(PageIndex.TRACE)
        else:
            self.connect_device()

    def _cleanup_device_sdcard(self):
        if self.adb.device and self.cleanup_working_dir_enabled:
            stale_files = self.adb.cleanUpSDCard(str(self.replay_working_dir))
            if stale_files and self._confirm_stale_device_files(stale_files):
                self._start_cleanup_device_sdcard(stale_files)

    def _start_cleanup_device_sdcard(self, stale_files):
        if self._cleanup_thread and self._cleanup_thread.isRunning():
            logger.info("Device cleanup already in progress, skipping duplicate cleanup request")
            return

        logger.info(f"Starting background cleanup of {len(stale_files)} stale device files")
        self._cleanup_worker = DeviceCleanupWorker(self.adb, self.replay_working_dir, stale_files)
        self._cleanup_thread = QThread()
        self._cleanup_worker.moveToThread(self._cleanup_thread)
        self._cleanup_thread.started.connect(self._cleanup_worker.run)
        self._cleanup_worker.finished.connect(self._on_cleanup_device_sdcard_finished)
        self._cleanup_worker.finished.connect(self._cleanup_thread.quit)
        self._cleanup_worker.finished.connect(self._cleanup_worker.deleteLater)
        self._cleanup_thread.finished.connect(self._cleanup_thread.deleteLater)
        self._cleanup_thread.finished.connect(self._reset_cleanup_device_sdcard_state)
        self._cleanup_thread.start()

    def _on_cleanup_device_sdcard_finished(self, success):
        if success:
            logger.info("Background device cleanup completed")
        else:
            logger.warning("Background device cleanup completed with errors")

    def _reset_cleanup_device_sdcard_state(self):
        self._cleanup_worker = None
        self._cleanup_thread = None

    def _confirm_stale_device_files(self, stale_files):
        msg = QMessageBox(self)
        msg.setWindowTitle("Old Device Files Found")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            f"Found {len(stale_files)} file(s) older than 30 days in {self.replay_working_dir}."
        )
        msg.setDetailedText("\n".join(stale_files))
        cleanup_button = msg.addButton("Cleanup", QMessageBox.AcceptRole)
        skip_button = msg.addButton("Skip delete", QMessageBox.RejectRole)
        msg.setDefaultButton(cleanup_button)
        msg.exec()
        return msg.clickedButton() == cleanup_button

    def connect_device(self):
        """
        Set device
        """
        self.device_window = UIConnectDevice(self.adb)
        self.device_window.device_selected.connect(self.traceStart)
