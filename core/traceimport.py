from core.config import ClickableQLineEdit, openFileExplorer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QDialog, QLineEdit, QFormLayout, QPushButton, QCheckBox
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QCloseEvent


class ImportWindow(QDialog):
    killed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import trace.")
        self.trace = ""
        self.frame_range = ""
        self._got_trace = False
        self._centering = False
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedWidth(720)

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

        self.override_existing_checkbox = QCheckBox("Override existing trace on device")
        self.skip_replay_checkbox = QCheckBox("Skip replay validation for imported trace")
        self.delete_trace_on_shutdown_checkbox = QCheckBox("Remove imported trace from device during cleanup")
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
        layout2.addWidget(self.delete_trace_on_shutdown_checkbox)

        label_trace = QLabel("Import trace:")
        layout.addRow(label_trace, self.lineEdit_trace)

        layout2.addLayout(layout)
        layout2.addWidget(self.button)

        self.setLayout(layout2)
        self.show()

    def _center_on_parent(self):
        parent = self.parentWidget()
        if not parent:
            return
        parent_rect = parent.frameGeometry()
        target_x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
        target_y = parent_rect.y() + (parent_rect.height() - self.height()) // 2
        self._centering = True
        self.move(target_x, target_y)
        self._centering = False

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_parent()

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self._centering:
            self._center_on_parent()

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

    def closeEvent(self, event: QCloseEvent):
        """
        Return to start if window is closed
        """
        if not self._got_trace:
            self.killed.emit()


class Trace():
    def __init__(self):
        self.path = None
