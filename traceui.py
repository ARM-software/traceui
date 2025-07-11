#!/usr/bin/python3

import signal
import sys
import os
import adblib

from PySide6.QtWidgets import QApplication
from gui import MainWindow

plugins_path = "plugins"

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
        print("Loaded plugin: plugins/%s -- %s" % (f, plugins[fname].full_name))
    sys.path.pop(0)

    # Starts and runs the app
    app = QApplication()
    mainWindow = MainWindow(adb, plugins)
    mainWindow.show()
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Quits the app
    sys.exit(app.exec())
