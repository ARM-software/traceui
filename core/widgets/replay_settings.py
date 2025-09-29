from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QDialog

class UiReplaySettings(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Set screenshot interval")
        self.interval = None
        self.setUpWidgetAndLayout()

    def setUpWidgetAndLayout(self):
        """
        Set up widget and layout
        """
        self.label = QLabel("Confirm screenshot interval.\n 0=No screenshots\n 1=Screenshots every frame\n n=Screenshots every nth frame")
        self.lineedit = QLineEdit("10")
        self.continue_button = QPushButton("Continue to replay")
        self.continue_button.clicked.connect(self.readInterval)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.lineedit)
        self.layout.addWidget(self.continue_button)
        self.setLayout(self.layout)

    def cleanup(self):
        """
        Clean up widget
        """
        self.lineedit.setText("10")
        self.interval = None

    def readInterval(self):
        """
        Check if value is an integer and set as integer. Set as interval if True.
        """
        written_interval = self.lineedit.text()
        try:
            self.interval = int(written_interval)
        except ValueError:
            err = QMessageBox()
            err.setText(f"Must be an integer. {written_interval} is not valid.")
            err.exec()
            return
        print(f"[ INFO ] The screenshotting interval was set to {self.interval}")
        self.accept()

    def getInterval(self):
        """
        Return interval
        """
        return self.interval
