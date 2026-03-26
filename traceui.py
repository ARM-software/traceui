#!/usr/bin/python3

import signal
import sys
import os
import adblib
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from core.logger_config import setup_logger
from gui import MainWindow

plugins_path = "plugins"
logger = setup_logger("traceui.py")
GLOBAL_FONT_POINT_SIZE = 13
GLOBAL_POPUP_FONT_POINT_SIZE = 14

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
        logger.debug("Loaded plugin: plugins/%s -- %s" % (f, plugins[fname].full_name))
    sys.path.pop(0)

    # Starts and runs the app
    app = QApplication()
    app_font = QFont(app.font())
    app_font.setPointSize(GLOBAL_FONT_POINT_SIZE)
    app.setFont(app_font)
    popup_style = """
        QDialog,
        QMessageBox,
        QMessageBox QLabel,
        QMessageBox QPushButton {
            font-size: %dpt;
        }
    """ % GLOBAL_POPUP_FONT_POINT_SIZE
    current_style = app.styleSheet().strip()
    app.setStyleSheet((current_style + "\n" + popup_style) if current_style else popup_style)

    mainWindow = MainWindow(adb, plugins)
    mainWindow.show()
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Quits the app
    sys.exit(app.exec())
