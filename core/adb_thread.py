import adblib
import threading
from PySide6.QtCore import Qt, Signal, QObject, QThread, QEventLoop
from PySide6.QtWidgets import QProgressDialog, QApplication
from core.logger_config import setup_logger

logger = setup_logger("adbThread")

class adbWorker(QObject):
    """
    Worker class to running adb commands.
    """
    finished = Signal(bool)
    progress = Signal(int, str)

    def __init__(self, adb=None, file=None, path=None, track=None, action=None):
        super().__init__()
        self.adb = adb
        self.file = file
        self.path = path
        self.track = track
        self.action = action
        self._last_logged_percent = -1
        self._cancel_event = threading.Event()

    def _report_progress(self, percent, message):
        """
        Emit progress updates and logs sparingly
        """
        if percent == 100 or percent - self._last_logged_percent >= 5:
            logger.info(message)
            self._last_logged_percent = percent
        self.progress.emit(percent, message)

    def cancel(self):
        """
        Request cancellation of the current transfer.
        """
        self._cancel_event.set()

    def push_pull(self):
        progress_callback = lambda percent, message: self._report_progress(percent, message)

        if self.action == "push":
            self._report_progress(0, f"Starting upload of {self.file}")
            result = self.adb.push(file=self.file, path=self.path, device=None, track=self.track, progress_callback=progress_callback, stop_event=self._cancel_event)
        elif self.action == "pull":
            self._report_progress(0, f"Starting download of {self.file}")
            result = self.adb.pull(file=self.file, path=self.path, device=None, progress_callback=progress_callback, stop_event=self._cancel_event)
        else:
            result = False

        self.finished.emit(bool(result))


class AdbThread(QObject):
    """
    Helper class for simplifying the processes of using QThread on adb commands.
    """
    progress_signal = Signal(int, str)
    operation_finished = Signal(bool)

    def __init__(self):
        super().__init__()
        self.thread = None


    def fileHandler(self, adb=None, file=None, path=None, track=False,  action=None):
        """
        Creates a thread to push files to device and prevent GUI glitching.
        """
        if hasattr(self, 'thread') and self.thread is not None:
            try:
                if self.thread.isRunning():
                    logger.debug("Waiting for previous adbThread to finish...")
                    self.thread.quit()
                    self.thread.wait()
            except RuntimeError:
                logger.debug("adbThread was already deleted. Skipping wait.")
            self.thread = None

        logger.info("FileHandler started in background")
        self.worker = adbWorker(adb=adb, file=file, path=path, track=track,  action=action)
        self.thread = QThread()
        self.push_event_loop = QEventLoop()

        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.push_pull)
        self.worker.finished.connect(self.thread.quit)
        self.worker.progress.connect(self.progress_signal.emit)

        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.on_done)
        self.worker.finished.connect(self.operation_finished.emit)

        self.thread.start()
        self.push_event_loop.exec()

    def cancel(self):
        if hasattr(self, "worker") and self.worker:
            self.worker.cancel()
        if hasattr(self, "thread") and self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()

    def run_with_progress(self, parent, title, adb, file, path, track=False, action=None, on_cancel=None):
        """
        Run an adb file transfer with a progress dialog.
        Returns a tuple: (cancelled: bool, success: bool)
        """
        progress_dialog = QProgressDialog(title, "Cancel", 0, 100, parent)
        progress_dialog.setWindowTitle(title)
        progress_dialog.setMinimumWidth(400)
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.show()
        cancelled = {"value": False}
        success = {"value": False}

        def on_progress(value, message):
            progress_dialog.setValue(value)
            progress_dialog.setLabelText(message)
            QApplication.processEvents()

        def on_finished(result):
            try:
                progress_dialog.canceled.disconnect(on_cancel_clicked)
            except Exception:
                pass
            success["value"] = bool(result)
            progress_dialog.setValue(100)
            progress_dialog.close()

        def on_cancel_clicked():
            cancelled["value"] = True
            self.cancel()
            progress_dialog.close()
            if on_cancel:
                on_cancel()

        progress_dialog.canceled.connect(on_cancel_clicked)
        self.progress_signal.connect(on_progress)
        self.operation_finished.connect(on_finished)
        self.fileHandler(adb=adb, file=file, path=path, track=track, action=action)
        return cancelled["value"], success["value"]

    def on_done(self):
        logger.info("FileHandler completed")
        if self.push_event_loop:
            self.push_event_loop.quit()
