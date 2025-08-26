import subprocess
import time
import os
import shutil
from core.config import ConfigSettings, ConfigGfxrWindow, ConfigPatraceWindow

from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer, QEventLoop
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QGridLayout, QGroupBox, QSizePolicy, QStackedWidget, QMessageBox, QScrollArea, QLineEdit
from core.page_navigation import PageNavigation, PageIndex
from core.adb_thread import AdbThread
from adblib import print_codes

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
        print(f"[ INFO ] Analysing Engine and API for '{self.proc_name}'")
        pkg_name, uses_vulkan, uses_gles, engine = self.adb.analyze_package(self.proc_name)

        self.result_ready.emit((pkg_name, uses_vulkan, uses_gles, engine))
        self.finished.emit(True)

    def run_app_start_poll(self):
        # Poll for the process on the device
        print(f"[ INFO ] Checking that app '{self.proc_name}' has started")
        while self._running:
            stdout = self.adb.command(["pidof", self.proc_name], run_with_sudo=True, print_command=False)[0]
            if stdout:
                print(f"[ INFO ] App started '{self.proc_name}' has started")
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

    def __init__(self, adb, plugins):
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

        self.adb = adb
        self.trace_result = None
        self.currentApp = None
        self.currentAppStarted = False
        self.lastTrace = None

        self.plugins = plugins
        self.currentTool = None

    def cleanUpImages(self):
        if os.path.isdir("tmp/replay_imgs"):
            shutil.rmtree("tmp/replay_imgs")

    def cleanup_page(self):
        """
        Clean up page and resets to app selection page
        """
        self.currentAppStarted = False
        self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)
        self.adb.clear_logcat()
        self.button_list = None
        self.searchbar.clear()

    def appSelectionPage(self):
        """
        Set up application selection page
        """
        # Back button
        if self.adb.device:
            self.applist = self.adb.apps()
            print(self.applist)
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
        self.setupAppLayouts(back_button, header, start_button)
        self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)

    def setupLoading(self):
        """
        Set up loading page for analysing packages
        """
        self.adb.cleanUpSDCard()
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
        apis_text = ", ".join(apis) if apis else "Unknown"
        print(f"[ INFO ] Detected Engine: {engine or 'Unknown'}\nUsed APIs: {apis_text}")
        self.trace_info_label.setText(
            f"Detected Engine: {engine or 'Unknown'}\nUsed APIs: {apis_text}\n\n Select Appropriate trace tool. \n Try gfxreconstruct first if available"
        )
        # show only relevant tools
        self.adbWorker.stop()
        self.setupToolsFiltered(uses_vulkan, uses_gles)

    def apkAnalyses_toolMatching(self):
        # Back button
        self.setupLoading()
        self.nestedStack.setCurrentIndex(PAGE_ANALYSING_APK)
        QApplication.processEvents()
        self.adbThread = QThread()
        self.adbWorker = WorkerAdbProcess(self.adb, self.currentApp, None)
        self.adbWorker.moveToThread(self.adbThread)

        #self.thread.started.connect(lambda: self.worker.run_analyse_apk(self.adb, self.currentApp))
        self.adbThread.started.connect(self.adbWorker.run_analyse_apk)
        self.adbWorker.result_ready.connect(self.handleWorkerResult)

        self.adbWorker.finished.connect(self.adbThread.quit)
        self.adbWorker.finished.connect(self.adbWorker.deleteLater)
        self.adbThread.finished.connect(self.adbThread.deleteLater)
        self.adbWorker.finished.connect(self.go_to_tracing_page)
        QTimer.singleShot(0, self.adbThread.start)
        self.adbThread.start()
        self.traceToolSelectionPage()

    def traceToolSelectionPage(self):
        """
        Set up page for trace tool selection
        """
        back_button = QPushButton("<-- Back")
        back_button.clicked.connect(self.go_to_app_selection)
        back_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Start tracing button
        start_button = QPushButton("START")
        start_button.setFixedWidth(200)
        self.widgetStyleSheet(start_button, color="limegreen", font_size="16px", selector="QPushButton")
        start_button.clicked.connect(self.appstart)
        self.tracing_page = QWidget()
        self.v_layout = QVBoxLayout(self.tracing_page)
        self.trace_info_label = QLabel(f"Select Appropriate tracer based on the Detected API(s)")
        self.trace_info_label.setAlignment(Qt.AlignCenter)
        self.widgetStyleSheet(self.trace_info_label, color="#f0f0f0", font_size="16px")
        button_group = QGroupBox()
        button_group.setFixedHeight(300)
        self.tool_layout = QHBoxLayout()
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
        self.nestedStack = QStackedWidget()
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

            # Set up device and start prosess
            self.plugins[self.currentTool].trace_setup_device(self.currentApp)
            print(f"[ INFO ] Device was set up for tracing '{self.currentApp}' using '{self.currentTool}")

            # Page #1: App start / tracing
            self.app_start_widget = QWidget()

            start_label_lines = [
                f"Please start application: {self.currentApp}",
                "Click 'Stop tracing' below to end tracing (don't cancel the tracing on the device manually)",
                "Stopping tracing will also parse logcat for errors, and can help with debugging if the app crashes."
            ]
            app_start_label = QLabel("\n\n".join(start_label_lines))

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
        label = self.app_start_widget.findChild(QLabel, "status")
        if label:
            label.setText("App started!")
        if not self.start_application_button.isHidden():
            self.start_application_button.hide()


    def startApplication(self):
        cmd = [f"monkey", "-p", self.currentApp, "-c" ,"android.intent.category.LAUNCHER", "1"]
        self.adb.command(cmd, errors_handled_externally=True)

    def endTrace(self):
        """
        Stop current running tracing and set up the post-trace page
        """
        # Stop tracing with trace tool and reset device
        self.adbWorker.stop()
        if self.plugins[self.currentTool].trace_setup_check(self.currentApp) and self.currentAppStarted:
            remote_path_to_trace = self.plugins[self.currentTool].trace_stop(self.currentApp)
            # Page nr 2: After trace stop page
            self.end_trace_widget = QWidget()

            self.currentTrace = remote_path_to_trace
            _, ls_error = self.adb.command(['ls', remote_path_to_trace], run_with_sudo=False)
            if ls_error:
                print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] No output trace file found at: {remote_path_to_trace}. Tracing probably failed.")
                self._handleFailed()
                return
            else:
                print(f"[ INFO ] Created trace file at: {remote_path_to_trace}")
                app_end_label = QLabel(f"Trace file created at: {self.currentTrace}")
                downloading_label = QLabel("")
                downloading_label.setObjectName("downloading")

            print(f"[ INFO ] Reset device after tracing with '{self.currentTool}'")
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

    def _handleFailed(self):
        """
        Report error to user and returns to the app selection page
        """
        print(f"[ INFO ] Reset device after tracing with '{self.currentTool}'")
        self.plugins[self.currentTool].trace_reset_device()
        print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] Generation of trace file was not successful, failed to start tracing process.")
        box_lines = ["WARNING: Tracing was not successful. Try a different tracing tool"]

        # Check for some basic errors
        if self.currentAppStarted is False:
            box_lines += [f"{self.currentApp} was not started."]
        else:
            box_lines += self.plugins[self.currentTool].parse_logcat(mode="trace", app=self.currentApp)
        msg = QMessageBox()
        msg.setText("\n".join(box_lines))
        msg.exec()
        if self.currentAppStarted is False:
            self.nestedStack.setCurrentIndex(PAGE_TOOLS_SELECTION)
        else:
            self.nestedStack.setCurrentIndex(PAGE_APP_SELECTION)

    def setupToolsFiltered(self, uses_vulkan, uses_gles):
        """
        Set up tool buttons for the used APIs. If no API is found, all plugins are shown

        Args:
            uses_vulkan (bool): True if the application uses Vulkan. False if not
            uses_gles (bool): True if the application uses OpenGl ES. False if not
        """
        # TODO: Pass engine info to plugins for custom retracer options
        # Show tools based on detected package APIs
        trace_tools = ["patrace", "gfxreconstruct"]
        for key, value in self.plugins.items():
            if value.plugin_name not in trace_tools:
                continue
            show_tool = False
            preselect_gfxr = False
            if not self.trace_result["uses_gles"] and not self.trace_result["uses_vulkan"]:
                # no api detected. Show all tools
                show_tool = True
            elif value.plugin_name == "patrace" and self.trace_result["uses_gles"]:
                show_tool = True
            elif value.plugin_name in ["gfxreconstruct"] and self.trace_result["uses_vulkan"]:
                show_tool = True
                preselect_gfxr = True

            if show_tool:
                tool_button = QPushButton(value.plugin_name)
                tool_button.setCheckable(True)
                if preselect_gfxr:
                    tool_button.setChecked(True)
                    self.setCurrentTool(value.plugin_name)
                tool_button.setAutoExclusive(True)
                tool_button.clicked.connect(lambda *, t=value.plugin_name: self.setCurrentTool(t))
                tool_button.setFixedWidth(200)
                tool_button.setStyleSheet("font-size: 18px;")
                self.tool_layout.addStretch()
                self.tool_layout.addWidget(tool_button)

        self.tool_layout.addStretch()

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
        _pull_helper.fileHandler(adb=self.adb, file=self.currentTrace, path="tmp", action="pull")

        name = str(self.currentTrace).split("/")[-1]
        msg = QMessageBox()
        msg.setText("\n".join(["INFO: Trace Downloaded to:", f"{os.getcwd()}/tmp/{name}"]))
        msg.exec()
        downloading_label.clear()

    def update_content(self):
        """
        Refresh the applist
        """
        QWidget().setLayout(self.layout())
        self.appSelectionPage()
