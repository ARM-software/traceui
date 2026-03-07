from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QDialog, QFormLayout
from core.logger_config import setup_logger

logger = setup_logger("replay_settings")


class UiReplaySettings(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Replay settings")
        self.interval = None
        self.end_frame = None
        self.setUpWidgetAndLayout()

    def setUpWidgetAndLayout(self):
        """
        Set up widget and layout
        """
        self.label = QLabel()
        self.interval_input = QLineEdit("10")
        self.end_frame_input = QLineEdit("")
        self.end_frame_input.setPlaceholderText("Optional, e.g. 1200")

        self.interval_hint = QLabel("Interval: 0=no screenshots, 1=every frame, n=every nth frame")
        self.end_frame_hint = QLabel("End frame (optional): last frame to replay")

        form = QFormLayout()
        form.addRow(self.interval_hint)
        form.addRow("Screenshot interval", self.interval_input)
        form.addRow(QLabel(""))
        form.addRow(self.end_frame_hint)
        form.addRow("End frame", self.end_frame_input)


        self.continue_button = QPushButton("Continue to replay")
        self.continue_button.clicked.connect(self.readSettings)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addLayout(form)
        layout.addWidget(self.continue_button)
        self.setLayout(layout)

    def cleanup(self):
        """
        Clean up widget
        """
        self.interval_input.setText("10")
        self.end_frame_input.clear()
        self.interval = None
        self.end_frame = None


    def readSettings(self):
        """
        Validate inputs and store interval/end_frame.
        """
        try:
            self.interval = self._parse_int(self.interval_input.text(), "Interval")
            end_frame_text = self.end_frame_input.text().strip()
            self.end_frame = self._parse_int(end_frame_text, "End frame") if end_frame_text else None
        except ValueError as exc:
            err = QMessageBox(self)
            err.setText(str(exc))
            err.exec()
            return

        logger.info(f"The screenshot interval was set to {self.interval}, end frame: {self.end_frame}")
        self.accept()

    def _parse_int(self, value: str, label: str) -> int:
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{label} must be an integer. '{value}' is not valid.")

    def getInterval(self):
        """
        Return interval
        """
        return self.interval

    def getEndFrame(self):
        """
        Return end frame (or None if unset)
        """
        return self.end_frame
