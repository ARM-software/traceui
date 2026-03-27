from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QPushButton)


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
        app = QApplication.instance()
        font_family = ""
        if app is not None:
            font_family = app.font().family()
        font_family_rule = f'font-family: "{font_family}";' if font_family else ""
        qcolor = QColor(color)
        if not qcolor.isValid():
            qcolor = QColor("#e9edf2")
        border_color = qcolor.darker(125).name()
        hover_color = qcolor.lighter(108).name()
        pressed_color = qcolor.darker(112).name()
        text_color = "#20242a"

        if selector == "QPushButton":
            style_str = """
                %(selector)s {
                    border: 1px solid %(border)s;
                    border-radius: 6px;
                    background-color: %(base)s;
                    color: %(text)s;
                    padding: 8px 16px;
                    %(font_family)s
                    font-size: %(font_size)s;
                }
                %(selector)s:hover {
                    background-color: %(hover)s;
                    border-color: %(border)s;
                }
                %(selector)s:pressed {
                    background-color: %(pressed)s;
                    border-color: %(border)s;
                    padding-top: 9px;
                    padding-bottom: 7px;
                }
                %(selector)s:disabled {
                    background-color: #e3e6ea;
                    color: #8c939c;
                    border-color: #c0c6cd;
                }
            """ % {
                "selector": selector,
                "border": border_color,
                "base": qcolor.name(),
                "text": text_color,
                "font_family": font_family_rule,
                "font_size": font_size,
                "hover": hover_color,
                "pressed": pressed_color,
            }
        else:
            style_str = f"border: 1px solid {border_color}; background-color: {qcolor.name()}; color: {text_color}; padding: 8px 16px; {font_family_rule} font-size: {font_size};"
        full = f"{selector} {{ {style_str} }}" if selector and selector != "QPushButton" else style_str
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
