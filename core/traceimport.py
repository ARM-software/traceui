from core.config import ClickableQLineEdit, openFileExplorer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QLineEdit, QFormLayout, QPushButton, QCheckBox, QMessageBox
from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent


class ImportWindow(QWidget):
    killed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Import trace.")
        self.trace = ""
        self.frame_range = ""
        self._got_trace = False

        self.setUpWidgets()
        self.setUpLayout()

    def setUpWidgets(self):
        """
        Set up widgets
        """
        self.lineEdit_trace = ClickableQLineEdit()
        self.lineEdit_trace.setReadOnly(True)
        self.lineEdit_trace.clicked.connect(lambda: openFileExplorer(self.lineEdit_trace, file=True))

        self.lineEdit_range = QLineEdit()

        self.override_existing_checkbox = QCheckBox(f"Override existing trace on device")
        self.skip_replay_checkbox = QCheckBox("Skip trace replay and use pre-decided framerange (no replay, no screenshots)")
        self.skip_screenshot_checkbox = QCheckBox(f"Use pre-decided frame range (will replay, no screenshots) ")
        self.delete_trace_on_shutdown_checkbox = QCheckBox(f"Remove imported trace from device during cleanup")
        self.remove_unsupported_extensions_on_replay = QCheckBox(f"Remove unsupported extensions")

        self.button = QPushButton("Start")
        self.button.clicked.connect(self.updateTrace)


    def setUpLayout(self):
        """
        Set up layout of the timport window
        """
        layout = QFormLayout()
        layout2 = QVBoxLayout()
        layout2.addWidget(self.override_existing_checkbox)
        layout2.addWidget(self.skip_replay_checkbox)
        layout2.addWidget(self.skip_screenshot_checkbox)
        layout2.addWidget(self.delete_trace_on_shutdown_checkbox)
        layout2.addWidget(self.remove_unsupported_extensions_on_replay)
        self.remove_unsupported_extensions_on_replay.setChecked(True)

        label_trace = QLabel("Import trace:")
        layout.addRow(label_trace, self.lineEdit_trace)

        layout2.addLayout(layout)
        layout2.addWidget(self.button)

        self.setLayout(layout2)
        self.show()

    def updateTrace(self):
        """
        Update trace path based on path
        """
        self.trace = self.lineEdit_trace.text()
        if not self.trace:
            return

        self.frame_range = self.lineEdit_range.text()
        self._got_trace = True
        self.close()

    def getTrace(self):
        """
        Return trace
        """
        return self.trace

    def overrideIfExisting(self):
        """
        Return bool based on "override"-checkbox
        """
        return self.override_existing_checkbox.isChecked()

    def skipGetScreenshot(self):
        """
        Return bool based on "skip screenshot"-checkbox
        """
        return self.skip_screenshot_checkbox.isChecked()

    def skipReplay(self):
        """
        Return bool based on "skip replay"-checkbox
        """
        return self.skip_replay_checkbox.isChecked()

    def deleteTraceOnShutdown(self):
        """
        Return bool based in "delete trace on shutdown"-checkbox
        """
        return self.delete_trace_on_shutdown_checkbox.isChecked()

    def removeUnsupportedExtensions(self):
        """
        Return bool based on "remove unsupported extension"-checkbox
        """
        return self.remove_unsupported_extensions_on_replay.isChecked()

    def closeEvent(self, event: QCloseEvent):
        """
        Return to start if window is closed
        """
        if not self._got_trace:
            self.killed.emit()


class Trace():
    def __init__(self):
        self.path = None
