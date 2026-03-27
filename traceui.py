#!/usr/bin/python3

import signal
import sys
import os
import adblib
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from core.logger_config import setup_logger
from gui import MainWindow

plugins_path = "plugins"
logger = setup_logger("traceui.py")
GLOBAL_FONT_POINT_SIZE = 12
GLOBAL_POPUP_FONT_POINT_SIZE = 14
GLOBAL_FONT_FAMILY_CANDIDATES = (
    "DejaVu Sans",
    "Noto Sans",
    "Liberation Sans",
    "Arial",
)


def choose_global_font_family():
    """
    Pick a stable sans-serif font family available in the current Qt runtime.
    """
    available_families = set(QFontDatabase.families())
    for family in GLOBAL_FONT_FAMILY_CANDIDATES:
        if family in available_families:
            return family
    return None


def build_global_stylesheet(font_family):
    font_family_rule = 'font-family: "%s";' % font_family if font_family else ""
    return """
        QWidget,
        QLabel,
        QLineEdit,
        QComboBox,
        QCheckBox,
        QTabWidget,
        QTabBar::tab {
            %s
            font-size: %dpt;
        }

        QDialog,
        QMessageBox,
        QMessageBox QLabel,
        QMessageBox QPushButton {
            %s
            font-size: %dpt;
        }

        QPushButton {
            %s
            font-size: %dpt;
            min-height: 36px;
            padding: 8px 16px;
            border: 1px solid #8e98a3;
            border-radius: 6px;
            background-color: #e9edf2;
            color: #20242a;
        }

        QPushButton:hover {
            background-color: #f5f7fa;
            border-color: #717b87;
        }

        QPushButton:pressed {
            background-color: #d9dee5;
            border-color: #5e6872;
            padding-top: 9px;
            padding-bottom: 7px;
        }

        QPushButton:checked {
            background-color: #d3dae3;
            border-color: #58616b;
        }

        QPushButton:disabled {
            background-color: #e3e6ea;
            color: #8c939c;
            border-color: #c0c6cd;
        }
    """ % (
        font_family_rule,
        GLOBAL_FONT_POINT_SIZE,
        font_family_rule,
        GLOBAL_POPUP_FONT_POINT_SIZE,
        font_family_rule,
        GLOBAL_FONT_POINT_SIZE,
    )


if __name__ == "__main__":
    # Initialize adblib
    adb = adblib.adb()

    # Load tool plugins
    plugins = {}
    sys.path.insert(0, plugins_path)
    for f in os.listdir(plugins_path):
        fname, ext = os.path.splitext(f)
        if ext != '.py':
            continue
        mod = __import__(fname)
        plugin = mod.tracetool(adb)
        plugin_name = plugin.plugin_name
        plugins[plugin_name] = plugin
        logger.debug(
            "Loaded plugin: plugins/%s -- %s" %
            (f, plugins[fname].full_name))
    sys.path.pop(0)

    # Starts and runs the app
    app = QApplication()
    app.setStyle("Fusion")
    app_font = QFont(app.font())
    selected_font_family = choose_global_font_family()
    if selected_font_family:
        app_font.setFamily(selected_font_family)
    app_font.setPointSize(GLOBAL_FONT_POINT_SIZE)
    app.setFont(app_font)
    popup_style = build_global_stylesheet(selected_font_family)
    current_style = app.styleSheet().strip()
    app.setStyleSheet((current_style + "\n" + popup_style)
                      if current_style else popup_style)

    mainWindow = MainWindow(adb, plugins)
    mainWindow.show()
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Quits the app
    sys.exit(app.exec())
