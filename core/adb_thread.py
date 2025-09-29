import adblib
from PySide6.QtCore import Qt, Signal, QObject, QThread, QEventLoop

class adbWorker(QObject):
    """
    Worker class to running adb commands.
    """
    finished = Signal(bool)

    def __init__(self, adb=None, file=None, path=None, track=None, action=None):
        super().__init__()
        self.adb = adb
        self.file = file
        self.path = path
        self.track = track
        self.action = action

    def push_pull(self):
        if self.action == "push":
            self.adb.push(file=self.file, path=self.path, device=None, track=self.track)
        elif self.action == "pull":
            self.adb.pull(file=self.file, path=self.path, device=None)

        self.finished.emit(True)


class AdbThread(QObject):
    """
    Helper class for simplifying the processes of using QThread on adb commands.
    """
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
                    print("[ INFO ] Waiting for previous adbThread to finish...")
                    self.thread.quit()
                    self.thread.wait()
            except RuntimeError:
                print("[ INFO ] adbThread was already deleted. Skipping wait.")
            self.thread = None

        print("[ INFO ] FileHandler started in background")
        self.worker = adbWorker(adb=adb, file=file, path=path, track=track,  action=action)
        self.thread = QThread()
        self.push_event_loop = QEventLoop()

        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.push_pull)
        self.worker.finished.connect(self.thread.quit)

        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.on_done)

        self.thread.start()
        self.push_event_loop.exec()


    def on_done(self):
        print("[ INFO ] FileHandler completed")
        if self.push_event_loop:
            self.push_event_loop.quit()

