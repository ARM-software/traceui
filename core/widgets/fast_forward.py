from core.page_navigation import PageNavigation, PageIndex
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout

class UiFastForwardWidget(PageNavigation):

    def __init__(self):
        super().__init__()
        self.label = QLabel("Fast forwarding will be available in the next release of traceui.")
        self.label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.setAlignment(Qt.AlignCenter)
        self.setLayout(layout)

    def cleanup_page(self):
        pass
