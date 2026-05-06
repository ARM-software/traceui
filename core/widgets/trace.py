import subprocess
import time
import os
import shutil
from pathlib import Path
from core.config import ConfigSettings, ConfigGfxrWindow, ConfigPatraceWindow

from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer, QEventLoop
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QGridLayout, QGroupBox, QSizePolicy, QStackedWidget, QMessageBox, QScrollArea, QLineEdit, QCheckBox, QComboBox, QTabWidget, QDialog, QFormLayout
from shiboken6 import isValid
from core.page_navigation import PageNavigation, PageIndex
from core.adb_thread import AdbThread
from adblib import print_codes

from core.logger_config import setup_logger

logger = setup_logger("trace")

PAGE_APP_SELECTION = 0
PAGE_ANALYSING_APK = 1
PAGE_TOOLS_SELECTION = 2
PAGE_START_TRACING = 3
PAGE_END_TRACING = 4

class WorkerAdbProcess(QObject):
    """Runs check loop in a background thread via moveToThread."""
    finished = Signal(bool)
    result_ready = Signal(object)

    def __init__(self, adb, app: str, trace):
        super().__init__()
        self.proc_name = app
        self.adb = adb
        self._running = True
        self.currentTrace = trace

    def run_analyse_apk(self):
        logger.debug(f"Analysing Engine and API for '{self.proc_name}'")
        try:
            pkg_name, uses_vulkan, uses_gles, engine = self.adb.analyze_package(self.proc_name)
            self.result_ready.emit((pkg_name, uses_vulkan, uses_gles, engine))
            self.finished.emit(True)
        except Exception:
            logger.exception(f"Failed to analyse package '{self.proc_name}'")
            self.result_ready.emit((self.proc_name, None, None, None))
            self.finished.emit(False)

    def run_app_start_poll(self):
        # Poll for the process on the device
        logger.debug(f"Checking that app '{self.proc_name}' has started")
        while self._running:
            stdout = self.adb.command(["pidof", self.proc_name], run_with_sudo=True, print_command=False)[0]
            if stdout:
                logger.info(f"App started '{self.proc_name}' has started")
                self.finished.emit(True)
                return
            time.sleep(0.5)

        self.finished.emit(False)

    def stop(self):
        self._running = False


class UiTraceWidget(PageNavigation):
    goback_signal = Signal()
    replay_signal = Signal()
    loading_signal = Signal()
    returnfromloading_signal = Signal()

    def __init__(self, adb, plugins, replay_working_dir=None):
        """
        Initialize the trace page

        Args:
            adb: connected and chosen device
            plugins (dict): Available plugins
        """
        super().__init__()
        # Read config values from config.ini
        config = ConfigSettings().get_config()
        tool_paths = config.get('Paths')
        self.patpath = tool_paths.get('pat_path')
        self.gfxrpath = tool_paths.get('gfxr_path')
        default_workdir = tool_paths.get('replay_working_dir', '/sdcard/devlib-target')
        self.replay_working_dir = Path(replay_working_dir or default_workdir)

        self.manual_tracing = False
        self.config_box = None
        self.gfxr_setprop_checkboxes = {}
        self.gfxr_setprop_inputs = {}
        self.gfxr_custom_setprop_inputs = {}
        self.gfxr_custom_setprop_remove_buttons = {}
        self.gfxr_grid = None
        self.add_custom_setprop_button = None

        self.adb = adb
        self.trace_result = None
        self.currentApp = None
        self.currentAppStarted = False
        self.lastTrace = None
        self.plugins = plugins
        self.currentTool = None
        self.app_start_widget = None
        self.start_application_button = None
        self.adbWorker = None
        self.adbThread = None

    def _is_qt_object_valid(self, obj):
        return obj is not None and isValid(obj)

    def _stop_adb_worker(self):
        if self._is_qt_object_valid(self.adbWorker):
            self.adbWorker.stop()

    def setManualTracing(self, state):
        """
        Callback and logic for toggling manual tracing
        """
        if state == Qt.Unchecked:
            self.manual_tracing = False
        elif state == Qt.Checked:
            self.manual_tracing = True

    def setGfxrTraceSetpropEnabled(self, prop, state):
        """
        Toggle one gfxreconstruct trace setup property.
        """
        gfxr_plugin = self.plugins.get("gfxreconstruct")
        if not gfxr_plugin or not hasattr(gfxr_plugin, "set_trace_setup_setprop_enabled"):
            return
        gfxr_plugin.set_trace_setup_setprop_enabled(prop, state == Qt.Checked)

    def setGfxrTraceSetpropValue(self, prop, value):
        """
        Update one gfxreconstruct trace setup property value.
        """
        gfxr_plugin = self.plugins.get("gfxreconstruct")
        if not gfxr_plugin or not hasattr(gfxr_plugin, "set_trace_setup_setprop_value"):
            return
        gfxr_plugin.set_trace_setup_setprop_value(prop, value.strip())

    def _clearLayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clearLayout(item.layout())

    def openAddGfxrSetpropDialog(self):
        """
        Open a dialog for adding a custom gfxreconstruct setprop.
        """
        gfxr_plugin = self.plugins.get("gfxreconstruct")
        if not gfxr_plugin or not hasattr(gfxr_plugin, "add_trace_setup_custom_setprop"):
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Add custom setprop")
        dialog.setMinimumWidth(640)

        prop_input = QLineEdit()
        prop_input.setPlaceholderText("debug.gfxrecon.some_property")
        value_input = QLineEdit()
        value_input.setPlaceholderText("Value (leave empty for empty string)")

        form = QFormLayout()
        form.addRow("Property", prop_input)
        form.addRow("Value", value_input)

        add_button = QPushButton("Add")
        cancel_button = QPushButton("Cancel")
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(add_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(button_layout)
        dialog.setLayout(layout)

        cancel_button.clicked.connect(dialog.reject)

        def on_add():
            prop = prop_input.text().strip()
            value = value_input.text().strip()
            if not prop:
                QMessageBox.warning(dialog, "Invalid setprop", "Property name cannot be empty.")
                return
            if prop in self.gfxr_setprop_checkboxes or prop in self.gfxr_setprop_inputs:
                QMessageBox.warning(
                    dialog,
                    "Setprop exists",
                    f"{prop} is already available in GFXR Config. Use the existing control.",
                )
                return
            gfxr_plugin.add_trace_setup_custom_setprop(prop, value)
            self._buildGfxrConfigGrid()
            dialog.accept()

        add_button.clicked.connect(on_add)
        dialog.exec()

    def removeGfxrCustomSetprop(self, prop):
        """
        Remove one custom gfxreconstruct setprop.
        """
        gfxr_plugin = self.plugins.get("gfxreconstruct")
        if not gfxr_plugin or not hasattr(gfxr_plugin, "remove_trace_setup_custom_setprop"):
            return
        if gfxr_plugin.remove_trace_setup_custom_setprop(prop):
            self._buildGfxrConfigGrid()

    def clearGfxrCustomSetprops(self):
        """
        Clear all custom gfxreconstruct setprops.
        """
        gfxr_plugin = self.plugins.get("gfxreconstruct")
        if not gfxr_plugin or not hasattr(gfxr_plugin, "clear_trace_setup_custom_setprops"):
            return
        ret = QMessageBox.question(
            self,
            "",
            "Delete all custom setprops?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        gfxr_plugin.clear_trace_setup_custom_setprops()
        self._buildGfxrConfigGrid()

    def resetGfxrSetpropsToDefaults(self):
        """
        Reset gfxreconstruct setprops to defaults and remove custom ones.
        """
        gfxr_plugin = self.plugins.get("gfxreconstruct")
        if not gfxr_plugin or not hasattr(gfxr_plugin, "reset_trace_setup_setprops_to_defaults"):
            return
        ret = QMessageBox.question(
            self,
            "",
            "Reset GFXR setprops to defaults and delete all custom setprops?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        gfxr_plugin.reset_trace_setup_setprops_to_defaults()
        self._buildGfxrConfigGrid()

    def _buildGfxrConfigGrid(self):
        """
        Build or rebuild the GFXR configuration controls.
        """
        if not self.gfxr_grid:
            return
        gfxr_plugin = self.plugins.get("gfxreconstruct")
        if not gfxr_plugin:
            return

        self._clearLayout(self.gfxr_grid)
        self.gfxr_setprop_checkboxes = {}
        self.gfxr_setprop_inputs = {}
        self.gfxr_custom_setprop_inputs = {}
        self.gfxr_custom_setprop_remove_buttons = {}

        row = 0
        check_box_manual_tracing = QCheckBox("Enable manual trace start")
        check_box_manual_tracing.setChecked(self.manual_tracing)
        check_box_manual_tracing.checkStateChanged.connect(self.setManualTracing)
        self.gfxr_grid.addWidget(check_box_manual_tracing, row, 0, 1, 3)
        row += 1

        if hasattr(gfxr_plugin, "get_trace_setup_setprops"):
            for setprop_item in gfxr_plugin.get_trace_setup_setprops():
                prop = setprop_item["prop"]
                value = setprop_item["value"]
                label = setprop_item.get("label", prop)
                ui_type = setprop_item.get("ui_type", "checkbox")
                if ui_type == "text":
                    input_label = QLabel(f"{label} ({prop})")
                    input_box = QLineEdit()
                    input_box.setPlaceholderText("Empty means capture all frames")
                    input_box.setText(value if value is not None else "")
                    input_box.textChanged.connect(
                        lambda text, prop_name=prop: self.setGfxrTraceSetpropValue(prop_name, text)
                    )
                    self.gfxr_grid.addWidget(input_label, row, 0)
                    self.gfxr_grid.addWidget(input_box, row, 1, 1, 2)
                    self.gfxr_setprop_inputs[prop] = input_box
                else:
                    checkbox = QCheckBox(f"{label} ({prop}={value})")
                    checkbox.setChecked(setprop_item.get("enabled", True))
                    checkbox.checkStateChanged.connect(
                        lambda state, prop_name=prop: self.setGfxrTraceSetpropEnabled(prop_name, state)
                    )
                    self.gfxr_grid.addWidget(checkbox, row, 0, 1, 3)
                    self.gfxr_setprop_checkboxes[prop] = checkbox
                row += 1

        custom_setprops = []
        if hasattr(gfxr_plugin, "get_trace_setup_custom_setprops"):
            custom_setprops = gfxr_plugin.get_trace_setup_custom_setprops()
        if custom_setprops:
            self.gfxr_grid.addWidget(QLabel("Custom setprops"), row, 0, 1, 3)
            row += 1
        for custom_item in custom_setprops:
            prop = custom_item.get("prop", "")
            value = custom_item.get("value", "")
            if not prop:
                continue
            input_label = QLabel(f"{prop}")
            input_box = QLineEdit()
            input_box.setText(value if value is not None else "")
            input_box.textChanged.connect(
                lambda text, prop_name=prop: self.setGfxrTraceSetpropValue(prop_name, text)
            )
            remove_button = QPushButton("Remove")
            remove_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            remove_button.clicked.connect(
                lambda _, prop_name=prop: self.removeGfxrCustomSetprop(prop_name)
            )
            self.gfxr_grid.addWidget(input_label, row, 0)
            self.gfxr_grid.addWidget(input_box, row, 1)
            self.gfxr_grid.addWidget(remove_button, row, 2)
            self.gfxr_custom_setprop_inputs[prop] = input_box
            self.gfxr_custom_setprop_remove_buttons[prop] = remove_button
            row += 1

        self.add_custom_setprop_button = QPushButton("Add custom setprop")
        self.add_custom_setprop_button.clicked.connect(self.openAddGfxrSetpropDialog)
        clear_custom_setprops_button = QPushButton("Clear custom setprops")
        clear_custom_setprops_button.clicked.connect(self.clearGfxrCustomSetprops)
        reset_to_defaults_button = QPushButton("Reset to defaults")
        reset_to_defaults_button.clicked.connect(self.resetGfxrSetpropsToDefaults)
        self.gfxr_grid.addWidget(self.add_custom_setprop_button, row, 0)
        self.gfxr_grid.addWidget(clear_custom_setprops_button, row, 1)
        self.gfxr_grid.addWidget(reset_to_defaults_button, row, 2)


    def cleanUpImages(self):
        if os.path.isdir("tmp/replay_imgs"):
            shutil.rmtree("tmp/replay_imgs")

    def setWorkingDir(self, path):
        self.replay_working_dir = Path(path)

    def cleanup_page(self):
        """
        Clean up page and resets to app selection page
        """
        self.currentAppStarted = False
        self._stop_adb_worker()
        self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)
        self.adb.clear_logcat()
        self.button_list = None
        self.searchbar.clear()
        if self._is_qt_object_valid(self.start_application_button) and self.start_application_button.isHidden():
            self.start_application_button.show()

    def appSelectionPage(self):
        """
        Set up application selection page
        """
        # Back button
        if self.adb.device:
            self.applist = self.adb.apps()
            applist = list(self.applist)
            logger.debug(f'Installed Apps: {[app.get("name") for app in applist]}')
        else:
            self.applist = []

        # TODO - properly load and configure plugins and paths and so on....
        self.tools = {
            "gfxreconstruct": ("Gfxreconstruct", self.gfxrpath, lambda: ConfigGfxrWindow(self.gfxrpath)),
            "patrace": ("Patrace", self.patpath, lambda: ConfigPatraceWindow(self.patpath))
        }
        back_button = QPushButton("<-- Back")
        back_button.clicked.connect(self.goback)
        back_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Start tracing button
        header = QLabel("Select Application to trace")
        header.setAlignment(Qt.AlignCenter)
        start_button = QPushButton("Next")
        start_button.clicked.connect(self.apkAnalyses_toolMatching)
        self.apk_analysis = QCheckBox("Extract Engine/API info from apk")
        self.setupAppLayouts(back_button, header, start_button)
        self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)

    def setupLoading(self):
        """
        Set up loading page for analysing packages
        """
        self.cleanUpImages()
        self.loading_page = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Analysing Package for Engine and API... please wait"))
        layout.setAlignment(Qt.AlignCenter)
        self.loading_page.setLayout(layout)
        self.nestedStack.insertWidget(PAGE_ANALYSING_APK, self.loading_page)

    def handleWorkerResult(self, result):
        """
        Use result to display used APIs and engine

        Args:
            result (tuple): Contain info about package name, whether it uses OpenGL ES or Vulkan and the engine
        """
        pkg_name, uses_vulkan, uses_gles, engine = result
        self.trace_result = {
            "pkg_name": pkg_name,
            "uses_vulkan": uses_vulkan,
            "uses_gles": uses_gles,
            "engine": engine,
        }

        apis = []
        if uses_vulkan:
            apis.append("Vulkan")
        if uses_gles:
            apis.append("OpenGLES")
        # show only relevant tools
        self.adbWorker.stop()
        self.setupToolsFiltered(uses_gles, uses_vulkan, apis, engine)

    def apkAnalyses_toolMatching(self):
        # Back button
        if self.apk_analysis.isChecked():
            self.setupLoading()
            self.nestedStack.setCurrentIndex(PAGE_ANALYSING_APK)
            QApplication.processEvents()
            self.adbThread = QThread()
            self.adbWorker = WorkerAdbProcess(self.adb, self.currentApp, None)
            self.adbWorker.moveToThread(self.adbThread)

            self.adbThread.started.connect(self.adbWorker.run_analyse_apk)
            self.adbWorker.result_ready.connect(self.handleWorkerResult)

            self.adbWorker.finished.connect(self.adbThread.quit)
            self.adbWorker.finished.connect(self.adbWorker.deleteLater)
            self.adbThread.finished.connect(self.adbThread.deleteLater)
            self.adbWorker.finished.connect(self.go_to_tracing_page)
            self.adbThread.start()
            self.traceToolSelectionPage()
        else:
            self.traceToolSelectionPage()
            self.trace_result = {"uses_vulkan": True, "uses_gles": True}
            self.setupToolsFiltered()
            self.go_to_tracing_page()


    def traceToolSelectionPage(self):
        """
        Set up page for trace tool selection
        """
        back_button = QPushButton("<-- Back")
        back_button.clicked.connect(self.go_to_app_selection)
        back_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Start tracing button
        start_button = QPushButton("Setup Tracer")
        start_button.setFixedWidth(200)
        self.widgetStyleSheet(start_button, color="limegreen", font_size="16px", selector="QPushButton")
        start_button.clicked.connect(self.appstart)
        self.tracing_page = QWidget()
        self.v_layout = QVBoxLayout(self.tracing_page)
        self.trace_info_label = QLabel(f"Select Appropriate tracer based on the Detected API(s)")
        self.trace_info_label.setAlignment(Qt.AlignCenter)
        self.trace_info_label.setWordWrap(True)
        self.trace_info_label.setMaximumHeight(78)
        self.widgetStyleSheet(self.trace_info_label, color="#f0f0f0", font_size="13px")
        button_group = QGroupBox()
        button_group.setFixedHeight(700)
        self.tool_layout = QGridLayout()
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(start_button)
        h_layout.addStretch()

        self.v_layout.addWidget(back_button)
        self.v_layout.addWidget(self.trace_info_label)
        button_group.setLayout(self.tool_layout)
        self.v_layout.addWidget(button_group)
        self.v_layout.addLayout(h_layout)
        self.tracing_page.setLayout(self.v_layout)
        self.nestedStack.insertWidget(PAGE_TOOLS_SELECTION, self.tracing_page)

    def setupAppLayouts(self, back, header, start):
        """
        Set up layout for application selection page

        Args:
            back: Widget for back button
            header: Widget for header
            start: Widget for start button
        """
        app_selection_page = QWidget()
        v_layout = QVBoxLayout(app_selection_page)
        button_group = QGroupBox()
        self.app_grid_widget = self.createAppGrid()
        self.searchbarInit()
        v_layout.addWidget(back)
        v_layout.addWidget(header)
        v_layout.addWidget(self.searchbar)
        v_layout.addWidget(self.app_grid_widget)
        v_layout.addWidget(button_group)
        v_layout.addWidget(self.apk_analysis)
        v_layout.addWidget(start)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.nestedStack)
        self.setLayout(main_layout)

        self.nestedStack.insertWidget(PAGE_APP_SELECTION, app_selection_page)

    def searchbarInit(self):
        self.searchbar = QLineEdit()
        self.searchbar.setPlaceholderText("Search for package name")
        self.searchbar.textChanged.connect(self.filteredPackages)


    def filteredPackages(self):
        query = self.searchbar.text().lower()
        all_buttons = self.app_grid_widget.widget().findChildren(QPushButton)
        for button in all_buttons:
            if query in button.objectName().lower():
                button.show()
            else:
                button.hide()

    def createAppGrid(self):
        """
        Create grid showcasing apps/packages

        Return:
            scroll_area: Scrollable area with all applications

        """
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container_widget = QWidget()
        scroll_area.setWidget(container_widget)
        app_grid = QGridLayout(container_widget)
        row = 0
        cols = 2  # Total numbers of colomns wanted
        self.applist = sorted(self.applist, key=lambda d: d['name'])
        for i, app in enumerate(self.applist):
            app_button = QPushButton(app['name'])
            app_button.setCheckable(True)
            app_button.setAutoExclusive(True)
            app_button.setObjectName(app['name'])
            app_button.clicked.connect(lambda *, a=app['name']: self.setCurrentApp(a))
            app_grid.addWidget(app_button, row, i % cols)
            if i % cols == (cols - 1):
                row += 1
        return scroll_area

    def setCurrentTool(self, tool):
        """
        Set current tool

        Args:
            tool (str): Name of tool
        """
        self.currentTool = tool

    def setCurrentApp(self, app):
        """
        Set current app

        Args:
            app (str): name of app package, for example com.arm.pa.paretrace
        """
        self.currentApp = app

    def installTool(self, tool_name):
        """
        Install given tool name

        Args:
            tool_name (str): name of tool
        """
        # TODO - ad a window/widged showing the update/install process
        self.plugins[tool_name].update()
        ConfigSettings().update_config('Paths', f'{str(self.plugins[tool_name].suffix)}_path', str(self.plugins[tool_name].basepath))

    def appstart(self):
        """
        Set up page displayed during tracing and sets it as three current page
        """
        if self.currentApp and self.currentTool:
            # Clear up the logcat before the run
            self.adb.clear_logcat()

            # Run a loading widget
            self.loading_signal.emit()
            QApplication.processEvents()

            self.plugins[self.currentTool].adb = self.adb
            # Set up device and start prosess
            self.plugins[self.currentTool].trace_setup_device(self.currentApp)
            logger.debug(f"Device was set up for tracing '{self.currentApp}' using '{self.currentTool}")
            if self.currentTool == "gfxreconstruct" and self.manual_tracing:
                # set prop "capture_android_trigger" based on tickbox
                self.adb.setprop('debug.gfxrecon.capture_android_trigger', 'false')
            logger.debug(f"Manual trace start set to {self.manual_tracing}")

            # Page #1: App start / tracing
            self.app_start_widget = QWidget()

            start_label_lines = [
                f"Please start application: {self.currentApp}",
                "Click 'Stop tracing' below to end tracing (don't cancel the tracing on the device manually)",
                "Stopping tracing will also parse logcat for errors, and can help with debugging if the app crashes."
            ]
            app_start_label = QLabel("\n\n".join(start_label_lines))
            app_start_label.setObjectName("start label")

            status_started = QLabel()
            status_started.setObjectName("status")
            self.app_start_layout = QVBoxLayout()
            self.app_start_layout.addWidget(app_start_label)
            self.app_start_layout.addWidget(status_started)
            self.app_start_layout.setAlignment(Qt.AlignCenter)


            # Stop Tracing button
            self.start_application_button = QPushButton("Launch application")
            self.start_application_button.clicked.connect(self.startApplication)
            self.start_application_button.setObjectName("launch_app")
            self.app_start_layout.addWidget(self.start_application_button)
            stop_tracing_button = QPushButton("Stop tracing")
            stop_tracing_button.clicked.connect(self.endTrace)
            stop_tracing_button.setObjectName("end trace")
            if self.manual_tracing and self.currentTool == "gfxreconstruct":
                start_tracing_button = QPushButton("Start tracing")
                start_tracing_button.clicked.connect(self.beginTrace)
                start_tracing_button.setObjectName("begin trace")
                self.app_start_layout.addWidget(start_tracing_button)
            self.app_start_layout.addWidget(stop_tracing_button)

            # Set widget layout and add to nested stack
            self.app_start_widget.setLayout(self.app_start_layout)
            self.nestedStack.insertWidget(PAGE_START_TRACING, self.app_start_widget)

            # Return from loading screen
            self.returnfromloading_signal.emit()
            self.nestedStack.setCurrentIndex(PAGE_START_TRACING)

            self.adbWorker = WorkerAdbProcess(self.adb, self.currentApp, None)
            self.adbThread = QThread(self)
            self.adbWorker.moveToThread(self.adbThread)
            self.adbThread.started.connect(self.adbWorker.run_app_start_poll)
            self.adbWorker.finished.connect(self._appStatus)
            self.adbWorker.finished.connect(self.adbThread.quit)
            self.adbWorker.finished.connect(self.adbWorker.deleteLater)
            self.adbThread.finished.connect(self.adbThread.deleteLater)
            # QTimer.singleShot(0, self.adbThread.start)
            self.adbThread.start()

        else:
            # Show a pop up saying that you are missing either app, tool or both
            msg = QMessageBox()
            msg_text = ""
            if self.currentApp is None and self.currentTool is None:
                msg_text = "You have to choose an application and a tool before starting tracing"
            elif self.currentApp is None and self.currentTool:
                msg_text = "Choose application before proceeding"
            else:
                msg_text = "Choose tool before proceeding"
            msg.setText(msg_text)
            msg.exec()

    def _appStatus(self, seen:bool):
        self.currentAppStarted = seen
        if not self._is_qt_object_valid(self.app_start_widget):
            return

        label = self.app_start_widget.findChild(QLabel, "status")
        if self._is_qt_object_valid(label):
            label.setText("App started!")
        if self._is_qt_object_valid(self.start_application_button) and not self.start_application_button.isHidden():
            self.start_application_button.hide()


    def startApplication(self):
        cmd = [f"monkey", "-p", self.currentApp, "-c" ,"android.intent.category.LAUNCHER", "1"]
        self.adb.command(cmd, errors_handled_externally=True)

    def updatePage(self):
        info_string = "Tracing has stopped. \n\n "
        if self.currentTool == "gfxreconstruct":
            info_string+= "Optimizing trace. Please wait..."
        status_label = self.app_start_widget.findChild(QLabel, "start label")
        status_label.setText(info_string)
        label = self.app_start_widget.findChild(QLabel, "status")
        label.clear()
        end_trace_button = self.app_start_widget.findChild(QPushButton, "end trace")
        begin_trace_button = self.app_start_widget.findChild(QPushButton, "begin trace")
        if end_trace_button.isVisible():
            end_trace_button.hide()
        if self.currentTool == "gfxreconstruct" and self.manual_tracing:
            begin_trace_button.hide()

    def beginTrace(self):
        """
        Start the tracing manually
        """
        self.adb.setprop('debug.gfxrecon.capture_android_trigger', 'true')

    def endTrace(self):
        """
        Stop current running tracing and set up the post-trace page
        """
        # Stop tracing with trace tool and reset device
        if self.currentTool == "gfxreconstruct":
            self.adb.setprop('debug.gfxrecon.capture_android_trigger', '')
        self._stop_adb_worker()
        if self.plugins[self.currentTool].trace_setup_check(self.currentApp) and self.currentAppStarted:
            self.updatePage()
            QApplication.processEvents()
            remote_path_to_trace = self.plugins[self.currentTool].trace_stop(self.currentApp)
            # Page nr 2: After trace stop page
            self.end_trace_widget = QWidget()

            self.currentTrace = remote_path_to_trace
            _, ls_error = self.adb.command(['ls', remote_path_to_trace], run_with_sudo=False)
            if ls_error:
                error_lower = ls_error.lower()
                if "permission denied" in error_lower:
                    logger.warning(f"Permission denied when accessing trace at: {remote_path_to_trace}")
                    extra_lines = [
                        "Trace created but failed to access the trace file on the device.",
                        f"Path: {remote_path_to_trace}",
                        "\n"
                        "Suggestions: Ensure the trace directory is readable or try fetching the trace manually"
                    ]
                    self._handleFailed(extra_lines=extra_lines)
                else:
                    logger.warning(f"No output trace file found at: {remote_path_to_trace}. Tracing probably failed. Error: {ls_error}")
                    self._handleFailed(extra_lines=[f"Could not find trace file at: {remote_path_to_trace}"])
                return
            else:
                logger.info(f"Created trace file at: {remote_path_to_trace}")
                app_end_label = QLabel(f"Trace file created at: {self.currentTrace}")
                downloading_label = QLabel("")
                downloading_label.setObjectName("downloading")

            logger.debug(f"Reset device after tracing with '{self.currentTool}'")
            self.plugins[self.currentTool].trace_reset_device()

            app_end_label.setAlignment(Qt.AlignCenter)
            downloading_label.setAlignment(Qt.AlignCenter)
            abort_tracing = QPushButton("Cancel")
            abort_tracing.setFixedWidth(400)
            self.widgetStyleSheet(abort_tracing, color="orangered", font_size="16px", selector="QPushButton")
            retry_tracing_button = QPushButton("Redo Capture")
            retry_tracing_button.setFixedWidth(400)
            self.widgetStyleSheet(retry_tracing_button, color="lightgray", font_size="16px", selector="QPushButton")
            download_trace_button = QPushButton("Download trace")
            download_trace_button.setFixedWidth(400)
            self.widgetStyleSheet(download_trace_button, color="lightgray", font_size="16px", selector="QPushButton")
            start_replay_button = QPushButton("Continue")
            start_replay_button.setFixedWidth(400)
            self.widgetStyleSheet(start_replay_button, color="limegreen", font_size="16px", selector="QPushButton")
            start_replay_button.clicked.connect(self.startReplay)
            retry_tracing_button.clicked.connect(self.appstart)
            abort_tracing.clicked.connect(self.goback)
            # TODO: Placeholder for downloading trace to local directory
            download_trace_button.clicked.connect(self.downloadTrace)
            top_button_layout = QHBoxLayout()
            top_button_layout.addStretch()
            top_button_layout.addWidget(retry_tracing_button)
            top_button_layout.addWidget(download_trace_button)
            top_button_layout.addStretch()

            bottom_button_layout = QHBoxLayout()
            bottom_button_layout.addStretch()
            bottom_button_layout.addWidget(abort_tracing)
            bottom_button_layout.addWidget(start_replay_button)
            bottom_button_layout.addStretch()

            button_layout = QVBoxLayout()
            button_layout.addLayout(top_button_layout)
            button_layout.addLayout(bottom_button_layout)

            self.endTrace_layout = QVBoxLayout()
            self.endTrace_layout.addWidget(app_end_label)
            self.endTrace_layout.addWidget(downloading_label)
            self.endTrace_layout.addLayout(button_layout)

            self.app_end_widget = QWidget()
            self.app_end_widget.setLayout(self.endTrace_layout)
            self.nestedStack.insertWidget(3, self.app_end_widget)
            self.nestedStack.setCurrentIndex(3)

        else:
            self._handleFailed()

    def _handleFailed(self, extra_lines=[]):
        """
        Report error to user and returns to the app selection page

        Args:
            extra_lines (list[str], optional): Additional lines to show in the warning dialog.
        """
        self.adb.command(["am", "force-stop", self.currentApp], run_with_sudo=True)
        logger.info(f"Reset device after tracing with '{self.currentTool}'")
        self.plugins[self.currentTool].trace_reset_device()
        logger.warning(f"Errors encounterd in tracing process")
        box_lines = []
        if extra_lines:
            box_lines.extend(extra_lines)
            box_lines += "\n"

        # Check for some basic errors
        if self.currentAppStarted is False:
            box_lines += [f"{self.currentApp} was not started."]
        if not extra_lines:
            box_lines += ["Tracing setup failed"]
            box_lines += ["Suggestions: Tracing on unrooted device is currently not supported"]
        elif "failed to access" not in extra_lines[0]:
            box_lines += ["Suggestions: Try a different tracing tool"]
            box_lines += self.plugins[self.currentTool].parse_logcat(mode="trace", app=self.currentApp)
        msg = QMessageBox()
        msg.setText("\n".join(box_lines))
        msg.exec()
        if self.currentAppStarted is False:
            self.nestedStack.setCurrentIndex(PAGE_TOOLS_SELECTION)
        else:
            self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)

    def setupToolsFiltered(self, uses_gles=True, uses_vulkan=True, apis=[], engine=""):
        """
        Set up tool buttons for the used APIs. If no API is found, all plugins are shown

        Args:
            uses_vulkan (bool): True if the application uses Vulkan. False if not
            uses_gles (bool): True if the application uses OpenGl ES. False if not
            apis (list): list of used APIs
            engine (str): Graphics engine used in application
        """
        # TODO: Pass engine info to plugins for custom retracer options
        # Show tools based on detected package APIs
        if self.tool_layout.count() >= 4:
            return
        apis_text = ", ".join(apis) if apis else "Unknown"
        logger.info(f"Detected Engine: {engine or 'Unknown'}\nUsed APIs: {apis_text}")
        self.trace_info_label.setText(
            f"Detected Engine: {engine or 'Unknown'}\nUsed APIs: {apis_text}\nSelect trace tool (prefer gfxreconstruct when available)."
        )

        tool_combo_box = QComboBox()
        tracer_label = QLabel("Tracer: ")
        tracer_label.setBuddy(tool_combo_box)
        tracer_label.setAlignment(Qt.AlignRight)
        self.tool_layout.addWidget(tracer_label, 0, 0)
        self.tool_layout.addWidget(tool_combo_box, 0, 1)

        self.config_box = QTabWidget()
        # GFXR config options
        self.gfxr_option_widget = QGroupBox("GFXR Config")
        self.gfxr_grid = QGridLayout()
        self.gfxr_option_widget.setLayout(self.gfxr_grid)
        self._buildGfxrConfigGrid()
        #PATRACE config options
        self.patrace_option_widget = QGroupBox("PaTrace Config")

        tab_dict = {}
        tab_dict["patrace"] = self.patrace_option_widget
        tab_dict["gfxreconstruct"] = self.gfxr_option_widget

        trace_tools = ["patrace", "gfxreconstruct"]
        preselect_gfxr = False
        tab_index_by_tool = {}
        for key, value in self.plugins.items():
            if value.plugin_name not in trace_tools:
                continue
            show_tool = False
            if not self.trace_result["uses_gles"] and not self.trace_result["uses_vulkan"]:
                # no api detected. Show all tools
                show_tool = True
            elif value.plugin_name == "patrace" and self.trace_result["uses_gles"]:
                show_tool = True
            elif value.plugin_name == "gfxreconstruct" and self.trace_result["uses_vulkan"]:
                show_tool = True
                preselect_gfxr = True

            if show_tool:
                new_tab_idx = self.config_box.addTab(tab_dict[value.plugin_name], value.plugin_name)
                tab_index_by_tool[value.plugin_name] = new_tab_idx
                tool_combo_box.addItem(value.plugin_name)

        selected_tool = tool_combo_box.currentText()
        if preselect_gfxr and "gfxreconstruct" in tab_index_by_tool:
            selected_tool = "gfxreconstruct"
            tool_combo_box.setCurrentText(selected_tool)

        selected_tab_idx = tab_index_by_tool.get(selected_tool)
        if selected_tab_idx is not None:
            self.config_box.setCurrentIndex(selected_tab_idx)
            logger.debug(f"Combo selection: {selected_tool}")
        if selected_tool:
            self.setCurrentTool(selected_tool)

        tool_combo_box.currentTextChanged.connect(self.changeToolConfigPage)
        # self.config_box.currentChanged.connect()
        self.config_box.tabBar().hide()
        self.tool_layout.addWidget(self.config_box, 1, 0, 1, 10)

    def changeToolConfigPage(self, tool):
        """
        Set the tracing tool to the selected one &
        change the settings page that is being displayed
        """
        self.setCurrentTool(tool)
        for i in range(self.config_box.count()):
            if self.config_box.tabText(i) == tool:
                self.config_box.setCurrentIndex(i)
                break
        logger.debug(f"Seleceted tool: {self.currentTool}")
        return


    def startReplay(self):
        """
        Emit signal to start replay
        """
        self.next_signal.emit(PageIndex.REPLAY)
        self.replay_signal.emit()

    def getCurrentTrace(self):
        """
        Return path to current trace
        """
        return self.currentTrace

    def go_to_app_selection(self):
        """
        Go to app selection page
        """
        self.currentApp = None
        self.currentTool = None
        self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)

    def goback(self):
        """
        Reset page and emit signal to go to previous page
        """
        self.currentApp = None
        self.currentTool = None
        self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)
        self.goback_signal.emit()


    def go_to_tracing_page(self):
        """
        Change page to either tool selection page or app selection
        """
        if self.currentApp is not None:
            self.nestedStack.setCurrentIndex(PAGE_TOOLS_SELECTION)
        else:
            msg = QMessageBox()
            msg_text = "Choose application before proceeding"
            msg.setText(msg_text)
            msg.exec()
            self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)

    def downloadTrace(self):
        """
        Download the trace to tmp/
        """
        downloading_label = self.app_end_widget.findChild(QLabel, "downloading")
        downloading_label.setText("Currently downloading. Please wait.")
        _pull_helper = AdbThread()
        cancelled, success = _pull_helper.run_with_progress(
            parent=self,
            title="Downloading trace...",
            adb=self.adb,
            file=self.currentTrace,
            path="tmp",
            action="pull",
            on_cancel=lambda: None,
        )
        if cancelled or not success:
            downloading_label.clear()
            if not cancelled:
                msg = QMessageBox()
                msg.setText("Trace download failed. Please retry.")
                msg.exec()
            return

        name = str(self.currentTrace).split("/")[-1]
        msg = QMessageBox()
        msg.setText("\n".join(["INFO: Trace Downloaded to:", f"{os.getcwd()}/tmp/{name}"]))
        msg.exec()
        downloading_label.clear()

    def update_content(self):
        """
        Refresh the applist
        """
        self.nestedStack = QStackedWidget()
        self.traceToolSelectionPage()
        QWidget().setLayout(self.layout())
        self.appSelectionPage()
