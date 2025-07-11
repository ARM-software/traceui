from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QPushButton)


class PageNavigation(QWidget):
    back_signal = Signal()
    next_signal = Signal(int)

    def __init__(self):
        super().__init__()

    def add_nav_button(self, layout, has_back=True, next_index=None):
        """
        Add navigation button

        Args:
            layout: Layout where nav button is added
            has_back: If it can go backwards
            next_index: If it can go forward
        """
        nav_layout = QHBoxLayout()
        if has_back:
            back_btn = QPushButton("Back")
            back_btn.clicked.connect(lambda: self.back_signal.emit())
            nav_layout.addWidget(back_btn)
        if next_index is not None:
            next_btn = QPushButton("Next")
            next_btn.clicked.connect(lambda: self.next_signal.emit(next_index))
            nav_layout.addWidget(next_btn)
        layout.addLayout(nav_layout)

    def widgetStyleSheet(self, widget, color: str, font_size: str, selector: str = ""):
        style_str = f"border: 1px solid #aaa; background-color: {color}; padding: 5px; font-size: {font_size};"
        full = f"{selector} {{ {style_str} }}" if selector else style_str
        widget.setStyleSheet(full)


class PageIndex():
    CONNECT = 0
    START = 1
    TRACE_IMPORTER = 2
    TRACE = 3
    REPLAY = 4
    FRAMERANGE = 5
    FRAME_SELECTION = 6
    FAST_FORWARD = 7
    POSTPROC = 8
    LOADING = 9
