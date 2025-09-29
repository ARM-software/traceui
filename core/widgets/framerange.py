from pathlib import Path
import os
from core.config import ConfigSettings
from PySide6.QtCore import Qt, Signal, QEventLoop, QThread, QObject
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QLineEdit, QPushButton, QFormLayout, QScrollArea, QAbstractButton, QMessageBox
from core.page_navigation import PageNavigation, PageIndex
from core.adb_thread import AdbThread

class PixMapHelper(QObject):
    results = Signal(object)
    finished = Signal()

    def __init__(self, images):
        super().__init__()
        self.images = images

    def makePictures(self):
        list_imgs = []
        for img in self.images:
            pixmap = QPixmap(img)
            if pixmap.isNull():
                print(f"[ INFO ] Unable to load image: {img}")
                continue
            list_imgs.append(pixmap)
        self.results.emit(list_imgs)
        self.finished.emit()



class ImgButton(QAbstractButton):

    def __init__(self, pixmap, parent=None):
        super(ImgButton, self).__init__(parent)
        self.pixmap = pixmap

    def paintEvent(self, event):
        """
        Draw image to button size and draw red border around button if checked
        """
        painter = QPainter(self)
        try:
            painter.drawPixmap(self.rect(), self.pixmap)

            if self.isChecked():
                pen = QPen(QColor("red"), 3)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        finally:
            painter.end()


    def sizeHint(self):
        """
        Return size of images
        """
        return self.pixmap.size()

    def img(self):
        """
        Return image
        """
        return self.pixmap


class UiFrameRangeWidget(PageNavigation):
    gotoframeselection_signal = Signal()

    def __init__(self):
        super().__init__()
        self.replay_widget = None
        self.current_focus_image_index = 0
        self.current_range_start = 0
        self.current_range_end = 0
        self.images = None
        self.frame_timeline = QHBoxLayout()
        self.v_layout = QVBoxLayout()
        self.timeline_widget = QWidget()
        self.timeline_widget.setLayout(self.frame_timeline)
        self.framerange_edit_label = QLabel()
        self.framerange_header = QLabel()
        self.framerange_label = QLabel()
        self.framerange_frame = QLabel()
        self.framerange_input = QLineEdit()
        self.start_select_button = QPushButton("Start")
        self.end_select_button = QPushButton("End")
        self.download_button = QPushButton("Download trace")
        self.continue_select_button = QPushButton("End")
        self.frame_focus = QLabel()
        self.missing_img = QLabel()
        self.download_status = QLabel()

        self.frame_scroll = QScrollArea()
        self.frame_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frame_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.frame_scroll.setWidgetResizable(True)
        self.frame_scroll.setWidget(self.timeline_widget)
        self.setupWidgets()

    def getImages(self):
        """
        Search for png/bmp and place in list of images
        """
        config = ConfigSettings().get_config()
        search_path = config.get('Paths').get('img_path')
        print(f"[ INFO ] Looking for images in: {search_path}")
        self.img_path = Path(search_path)
        self.images = list(self.img_path.glob('**/*.png'))
        if not self.images:
            print(f"[ INFO ] Found no images with mask: '**/*.png', trying again with **/*.bmp")
            self.images = list(self.img_path.glob('**/*.bmp'))

            if not self.images:
                print(f"[ INFO ] Found no images in {search_path}")
            else:
                print(f"[ INFO ] Found {len(self.images)} images in {search_path}!")

        self.image_indices = []
        for image_path in self.images:
            name = image_path.stem
            frame = name.split("frame_")[-1].split("_")[0]

            try:
                self.image_indices.append(int(frame))
            except ValueError:
                self.image_indices.append(-1)
                print(f"[ ERROR ] Invalid snapshot image name format for image: {image_path}")

        zip_sorted = sorted(zip(self.images, self.image_indices), key=lambda x: x[1])
        self.images = [x[0] for x in zip_sorted]
        self.image_indices = [x[1] for x in zip_sorted]

        print("[ INFO ] Loading images...")
        QApplication.processEvents()
        self.updatePictureWidgets()
        self.setupLayouts()
        self.resetVisibility()

    def setupWidgets(self):
        """
        Set up the widgets and pictures
        """
        self.framerange_header.setText("Select frame range")
        self.framerange_frame.setText("Frame: 0")
        self.framerange_label.setText("Current framerange: 0-0")
        self.framerange_edit_label.setText("Range override (<start>-<end>): ")

        self.start_select_button.setText("Set to start frame")
        self.start_select_button.clicked.connect(self.setStartFrame)
        self.end_select_button.setText("Set to end frame")
        self.end_select_button.clicked.connect(self.setEndFrame)

        self.download_button.clicked.connect(self.downloadTrace)
        self.continue_select_button.setText("Continue")
        self.continue_select_button.clicked.connect(self.frameSelect)

    def updatePictureWidgets(self):
        if self.images:
            self.frame_focus.setPixmap(QPixmap(self.images[0]).scaled(800, 450))
            self.frame_focus.setAlignment(Qt.AlignCenter)
            self.download_status.setAlignment(Qt.AlignCenter)
            self.framerange_edit_label.hide()
            self.framerange_input.hide()

        else:
            self.missing_img.setText(f"No images found in: {self.img_path}")
            self.frame_focus.hide()
            self.framerange_edit_label.show()
            self.framerange_input.show()
            self.start_select_button.hide()
            self.end_select_button.hide()

    def cleanupBoxLayout(self, boxlayout):
        """
        Clean up the box layout
        """
        if boxlayout is not None:
            while boxlayout.count():
                item = boxlayout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()

    def setupLayouts(self):
        """
        Set up frame range page layout
        """
        input_layout = QFormLayout()
        input_layout.addRow(self.framerange_edit_label, self.framerange_input)

        self.cleanupBoxLayout(self.frame_timeline)
        self.v_layout.addWidget(self.framerange_header)
        self.v_layout.addWidget(self.framerange_frame)
        self.v_layout.addWidget(self.framerange_label)

        # Clear existing timeline items
        if self.images:
            self.v_layout.addWidget(self.frame_focus)
            self.thread = QThread()
            self.eventloop = QEventLoop()
            self.worker = PixMapHelper(self.images)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.makePictures)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.worker.results.connect(self.thread_completed)
            self.thread.start()
            self.eventloop.exec()

            self.createScrollArea()
            self.v_layout.addWidget(self.frame_scroll)
        else:
            self.v_layout.addWidget(self.missing_img)
            self.v_layout.addLayout(input_layout)

        self.v_layout.addWidget(self.start_select_button)
        self.v_layout.addWidget(self.end_select_button)
        self.v_layout.addWidget(self.continue_select_button)
        self.v_layout.addWidget(self.download_button)
        self.v_layout.addWidget(self.download_status)

        self.setLayout(self.v_layout)

    def thread_completed(self, results):
        self.pixmaps = results
        print("[ INFO ] Image loading completed!")
        if self.eventloop:
            self.eventloop.quit()

    def createScrollArea(self):
        """
        Enable scrolling on frame pictures

        Return:
            frame_scroll: scrollable widget with frames as buttons
        """
        # Rebuild timeline
        for pixmap in self.pixmaps:
            b = ImgButton(pixmap.scaled(400, 225))
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.clicked.connect(self.updateFocus)
            self.frame_timeline.addWidget(b)

    def downloadTrace(self):
        self.download_status.setText("Currently downloading. Please wait...")
        _pull_helper = AdbThread()
        _pull_helper.fileHandler(adb=self.replay_widget.adb, file=self.replay_widget.currentTrace, path="tmp", action="pull")
        msg = QMessageBox()
        msg_text = f" The trace was downloaded here: {os.getcwd()}/tmp"
        msg.setText(msg_text)
        msg.exec()
        self.download_status.clear()

    def updateFocus(self, img):
        """
        Update focus to selected frame
        """
        for i in range(self.frame_timeline.count()):
            widget = self.frame_timeline.itemAt(i).widget()
            if isinstance(widget, ImgButton):
                if widget.isChecked():
                    img = self.images[i]
                    self.current_focus_image_index = self.image_indices[i]
                    self.framerange_frame.setText("Frame: {}".format(self.current_focus_image_index))

        self.frame_focus.setPixmap(QPixmap(img).scaled(800, 450))

    def setStartFrame(self):
        """
        Select start frame
        """
        self.current_range_start = self.current_focus_image_index
        self.framerange_label.setText(f"Current framerange: [{self.current_range_start}-{self.current_range_end})")

    def setEndFrame(self):
        """
        Select end frame
        """
        self.current_range_end = self.current_focus_image_index
        self.framerange_label.setText(f"Current framerange: [{self.current_range_start}-{self.current_range_end})")

    def validate_framerange(self):
        """
        Check validity of framerange. Print error message if not valid

        Return:
            bool: False if not valid range, true if valid range
        """
        if self.current_range_start > self.current_range_end:
            print(f"[ ERROR ] Selected range start frame is greater than end frame: [{self.current_range_start}-{self.current_range_end})")
            return False

        elif (self.current_range_end == 0 and self.current_range_start == 0):
            print(f"[ ERROR ] No frames selected.")
            return False

        elif self.current_range_start == self.current_range_end:
            print(f"[ ERROR ] Selected range start frame is the same as end frame: [{self.current_range_start}-{self.current_range_end})")
            return False

        elif self.current_range_start == -1:
            print(f"[ ERROR ] Selected range start frame is invalid: [{self.current_range_start}-{self.current_range_end})")
            return False

        elif self.current_range_end == -1:
            print(f"[ ERROR ] Selected range end frame is invalid: [{self.current_range_start}-{self.current_range_end})")
            return False

        return True

    def processLineFramerange(self):
        """
        Set frame range
        """
        line_framerange = self.framerange_input.text()
        if line_framerange:
            tokens = line_framerange.split("-")
            if len(tokens) == 2:
                try:
                    start_range = int(tokens[0])
                    end_range = int(tokens[1])
                except ValueError:
                    print("[ ERROR ] The textual framerange input is invalid, must have format: [<int>-<int>). Ignoring.")
                    return

                self.current_range_start = start_range
                self.current_range_end = end_range

    def frameSelect(self):
        """
        Emit signal to continue to Frame Selection if frame range is valid.
        Return:
            False: not valid frame range
        """
        self.processLineFramerange()

        if not self.validate_framerange():
            print(f"[ WARNING ] Chosen frame range invalid")
            msg = QMessageBox()
            msg_text = " Please select a valid frame range."
            msg.setText(msg_text)
            msg.exec()
            self.next_signal.emit(PageIndex.FRAMERANGE)
            return False
        print(f"[ INFO ] Frame range set to: [{self.current_range_start}-{self.current_range_end})")
        self.gotoframeselection_signal.emit()
        self.next_signal.emit(PageIndex.FRAME_SELECTION)

    def cleanup_page(self):
        """
        Reset variables
        """
        self.current_focus_image_index = 0
        self.current_range_start = 0
        self.current_range_end = 0
        self.framerange_input.clear()

        self.resetVisibility()

    def resetVisibility(self):
        """
        Hide or show widgtes on page either during cleanup or setup, respectively
        """
        if hasattr(self, "images") and self.images:
            self.framerange_edit_label.hide()
            self.framerange_input.hide()
            self.start_select_button.show()
            self.end_select_button.show()
            self.frame_focus.show()
            self.download_button.show()
            if hasattr(self, "missing_img"):
                self.missing_img.hide()
        else:
            self.framerange_edit_label.show()
            self.framerange_input.show()
            self.start_select_button.hide()
            self.end_select_button.hide()
            self.download_button.hide()
            if hasattr(self, "frame_focus"):
                self.frame_focus.hide()
            if hasattr(self, "missing_img"):
                self.missing_img.show()
