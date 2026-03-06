from pathlib import Path
import os
from core.config import ConfigSettings
from PySide6.QtCore import Qt, Signal, QEventLoop, QThread, QObject, QRect
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QLineEdit, QPushButton, QFormLayout, QScrollArea, QAbstractButton, QMessageBox, QSizePolicy
from core.page_navigation import PageNavigation, PageIndex
from core.adb_thread import AdbThread
import subprocess
from core.logger_config import setup_logger

logger = setup_logger("framerange")


class PixMapHelper(QObject):
    results = Signal(object)
    finished = Signal()

    def __init__(self, images, remove_alpha=False, thumb_px=400):
        super().__init__()
        self.images = images
        self.remove_alpha = remove_alpha
        self.thumb_px = thumb_px

    def makePictures(self):
        list_imgs = []
        if not len(self.images):
            self.finished.emit()
            return
        if self.remove_alpha:
            base_path = str(Path(self.images[0]).parent)
            cmd = ["mogrify", "-alpha", "off", f"{base_path}/*.png"]
            process = subprocess.run(
                " ".join(cmd), shell=True, capture_output=True)
        for img in self.images:
            pixmap = QPixmap(img)
            if pixmap.isNull():
                logger.info(f"Unable to load image: {img}")
                continue
            scaled_pixmap = pixmap.scaled(
                self.thumb_px, self.thumb_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            list_imgs.append(scaled_pixmap)
        self.results.emit(list_imgs)
        self.finished.emit()


class ImgButton(QAbstractButton):
    def __init__(self, pixmap=None, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap(pixmap)
        self.setCheckable(True)

    def pixmap(self):
        return QPixmap(self._pixmap)

    def img(self):
        return self.pixmap()

    def sizeHint(self):
        return self._pixmap.size()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            if not self._pixmap.isNull():
                target_size = self._pixmap.size().scaled(self.size(), Qt.KeepAspectRatio)
                x = (self.width() - target_size.width()) // 2
                y = (self.height() - target_size.height()) // 2
                target_rect = QRect(
                    x, y, target_size.width(),
                    target_size.height())
                painter.drawPixmap(target_rect, self._pixmap)

            if self.isChecked():
                pen = QPen(QColor("red"), 3)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        finally:
            painter.end()


class UiFrameRangeWidget(PageNavigation):
    gotoframeselection_signal = Signal()

    def __init__(self):
        super().__init__()
        self.replay_widget = None
        self.current_focus_image_index = 0
        self.current_range_start = 0
        self.current_range_end = 0
        self.current_focus_image_path = None
        self.current_focus_pixmap = None
        self._thumb_px = 200
        self.images = None
        self.frame_timeline = QHBoxLayout()
        self.v_layout = QVBoxLayout()
        self.timeline_widget = QWidget()
        self.timeline_widget.setLayout(self.frame_timeline)
        self.framerange_edit_label = QLabel()
        #self.framerange_header = QLabel()
        self.framerange_label = QLabel()
        self.page_info = QLabel()
        self.framerange_frame = QLabel()
        self.framerange_input = QLineEdit()
        self.start_select_button = QPushButton("Set to start frame")
        self.end_select_button = QPushButton("Set to end frame")
        self.download_button = QPushButton("Download trace")
        self.continue_select_button = QPushButton("End")
        self.remove_alpha = QPushButton(
            "Transparent images? Remove alpha channels")
        self.frame_focus = QLabel()
        self.missing_img = QLabel()
        self.status = QLabel()

        self.frame_scroll = QScrollArea()
        self.frame_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frame_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.frame_scroll.setWidgetResizable(True)
        self.frame_scroll.setWidget(self.timeline_widget)
        self.frame_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.frame_scroll.setMinimumHeight(200)

        # Page naviagtion variables
        self.images_per_page = 20
        self.current_page = 0
        self.total_pages = 0

        self.setupWidgets()

    def _apply_focus_pixmap(self):
        """
        Scale the current focus pixmap to the label while preserving aspect ratio.
        """
        if not self.current_focus_pixmap:
            return
        if self.frame_focus.width() == 0 or self.frame_focus.height() == 0:
            return
        scaled = self.current_focus_pixmap.scaled(
            self.frame_focus.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.frame_focus.setPixmap(scaled)

    def _set_focus_image(self, img_path):
        if not img_path:
            return
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return
        self.current_focus_pixmap = pixmap
        self._apply_focus_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_focus_pixmap()

    def updatePageNavButtons(self):
        """
        Enable or disable navigation buttons based on the current page.
        """
        # Disable "First Page" and "Previous Page" buttons on the first page
        if self.current_page == 0:
            self.first_page_button.setEnabled(False)
            self.prev_page_button.setEnabled(False)
        else:
            self.first_page_button.setEnabled(True)
            self.prev_page_button.setEnabled(True)
        # Disable "Next Page" and "Last Page" buttons on the last page
        if self.current_page == self.total_pages - 1:
            self.next_page_button.setEnabled(False)
            self.last_page_button.setEnabled(False)
        else:
            self.next_page_button.setEnabled(True)
            self.last_page_button.setEnabled(True)

    def getImages(self):
        """
        Search for png/bmp and place in list of images
        """
        config = ConfigSettings().get_config()
        search_path = config.get('Paths').get('img_path')
        logger.info(f"Looking for images in: {search_path}")
        self.img_path = Path(search_path)
        self.images = list(self.img_path.glob('**/*.png'))
        if not self.images:
            logger.debug(
                f"Found no images with mask: '**/*.png', trying again with **/*.bmp")
            self.images = list(self.img_path.glob('**/*.bmp'))

            if not self.images:
                logger.debug(f"Found no images in {search_path}")
            else:
                logger.info(
                    f"Found {len(self.images)} images in {search_path}!")

        self.image_indices = []
        for image_path in self.images:
            name = image_path.stem
            frame = name.split("frame_")[-1].split("_")[0]

            try:
                self.image_indices.append(int(frame))
            except ValueError:
                self.image_indices.append(-1)
                logger.error(
                    f"Invalid snapshot image name format for image: {image_path}")

        zip_sorted = sorted(
            zip(self.images, self.image_indices),
            key=lambda x: x[1])
        self.images = [x[0] for x in zip_sorted]
        self.image_indices = [x[1] for x in zip_sorted]
        self.total_pages = (len(
            self.image_indices) + self.images_per_page - 1) // self.images_per_page if self.image_indices else 0

        logger.info("Loading images...")
        QApplication.processEvents()
        self.updatePictureWidgets()
        self.setupLayouts()
        self.resetVisibility()

    def setupWidgets(self):
        """
        Set up the widgets and pictures
        """
        self.page_info.setText("Page: 1/1")
        #self.framerange_header.setText("Chosen Frame & Range:")
        self.framerange_frame.setText("Current Frame: 0")
        self.framerange_label.setText("Selected framerange: 0-0")
        self.framerange_edit_label.setText("Range override (<start>-<end>): ")

        self.remove_alpha.clicked.connect(self.removeAlpha)
        self.start_select_button.setText("Set to start frame")
        self.start_select_button.clicked.connect(self.setStartFrame)
        self.end_select_button.setText("Set to end frame")
        self.end_select_button.clicked.connect(self.setEndFrame)

        self.download_button.clicked.connect(self.downloadTrace)
        self.continue_select_button.setText("Continue")
        self.continue_select_button.clicked.connect(self.frameSelect)

    def removeAlpha(self):
        self.reloadImages(remove_alpha=True)

    def reloadImages(self, remove_alpha=False):
        """Reloads images in the scroll area without rebuilding other widgets."""
        self.status.setText("Loading images. Please wait...")
        if remove_alpha:
            self.status.setText(
                "Removing alpha channel and reloading images. Please wait...")
            logger.info("[ INFO ] Reloading images without alpha channels")
        QApplication.processEvents()

        self.cleanupBoxLayout(self.frame_timeline)
        # Load a section of images using currant_page and images per page
        start_index = self.current_page * self.images_per_page
        end_index = start_index + self.images_per_page
        page_nav_images = self.images[start_index:end_index]

        if not page_nav_images:
            logger.debug("No pixmaps to display on this page.")
            return

        self.thread = QThread()
        self.eventloop = QEventLoop()
        self.worker = PixMapHelper(page_nav_images, remove_alpha=remove_alpha)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.makePictures)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.results.connect(self.thread_completed)
        self.thread.start()
        self.eventloop.exec()

        self.createScrollArea()

        self.status.clear()

    def updatePictureWidgets(self):
        if self.images:
            self.frame_focus = QLabel()
            self.current_focus_image_path = self.images[0]
            self.frame_focus.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.frame_focus.setMinimumHeight(300)
            self._set_focus_image(self.current_focus_image_path)
            self.frame_focus.setAlignment(Qt.AlignCenter)
            self.status.setAlignment(Qt.AlignCenter)
            self.framerange_edit_label.hide()
            self.framerange_input.hide()

        else:
            self.missing_img.setText(f"No images found in: {self.img_path}")
            self.frame_focus.hide()
            self.page_info.hide()
            self.framerange_edit_label.show()
            self.framerange_frame.hide()
            self.framerange_label.hide()
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
        Set up frame range page layout with page nav buttons.
        """
        input_layout = QFormLayout()
        input_layout.addRow(self.framerange_edit_label, self.framerange_input)

        self.cleanupBoxLayout(self.frame_timeline)
        self.v_layout.addWidget(self.page_info)
        #self.v_layout.addWidget(self.framerange_header)
        self.v_layout.addWidget(self.framerange_frame)
        self.v_layout.addWidget(self.framerange_label)

        # Clear existing timeline items
        if self.images:
            self.v_layout.addWidget(self.frame_focus, 2)
            self.thread = QThread()
            self.eventloop = QEventLoop()
            self.worker = PixMapHelper(self.images, thumb_px=self._thumb_px)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.makePictures)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.worker.results.connect(self.thread_completed)
            self.thread.start()
            self.eventloop.exec()
            reload_layout = QHBoxLayout()
            reload_layout.addWidget(self.status, 1)
            reload_layout.addWidget(self.remove_alpha, 0 , Qt.AlignRight)
            self.v_layout.addLayout(reload_layout)
            self.createScrollArea()
            self.v_layout.addWidget(self.frame_scroll, 1)

        else:
            self.v_layout.addWidget(self.missing_img)
            self.v_layout.addLayout(input_layout)

        self.v_layout.addWidget(self.download_button)
        frame_range_layout = QHBoxLayout()
        frame_range_layout.addWidget(self.start_select_button)
        frame_range_layout.addWidget(self.end_select_button)
        frame_range_layout.addWidget(self.continue_select_button)
        self.v_layout.addLayout(frame_range_layout)

        self.setLayout(self.v_layout)

    def thread_completed(self, results):
        self.pixmaps = results
        logger.info("Image loading completed!")
        if self.eventloop:
            self.eventloop.quit()

    def navigatePage(self, action):
        """
        Navigate to a specific page based on the action.

        Args:
            action (str): The navigation action. Can be one of:
                        'first', 'last', 'prev', 'next'.
        """
        if action == "first":
            self.current_page = 0
        elif action == "last":
            self.current_page = self.total_pages - 1
        elif action == "prev" and self.current_page > 0:
            self.current_page -= 1
        elif action == "next" and self.current_page < self.total_pages - 1:
            self.current_page += 1
        else:
            return

        self.reloadImages()

    def createScrollArea(self):
        """
        Enable scrolling on frame pictures with navigation arrows.

        Return:
            frame_scroll: scrollable widget with frames as buttons
        """
        self.cleanupBoxLayout(self.frame_timeline)

        start_index = self.current_page * self.images_per_page
        page_nav_pixmaps = self.pixmaps[:self.images_per_page]
        logger.debug(f"Current page: {self.current_page}")
        logger.debug(f"Pixmaps on this page: {len(page_nav_pixmaps)}")

        if page_nav_pixmaps:
            self.current_focus_image_index = self.image_indices[start_index]
            self.page_info.setText(
                "Page: {}/{}".format(self.current_page + 1, self.total_pages))
            self.framerange_frame.setText(
                "Frame: {}".format(
                    self.current_focus_image_index))

        # Add "First Page" button (double left arrow)
        self.first_page_button = QPushButton("«")
        self.first_page_button.setFixedSize(40, 40)
        self.first_page_button.clicked.connect(
            lambda: self.navigatePage("first"))
        self.frame_timeline.addWidget(self.first_page_button)

        # Add "Previous Page" button (left arrow)
        self.prev_page_button = QPushButton("←")
        self.prev_page_button.setFixedSize(40, 40)
        self.prev_page_button.clicked.connect(
            lambda: self.navigatePage("prev"))
        self.frame_timeline.addWidget(self.prev_page_button)

        # Add image buttons
        for pm in page_nav_pixmaps:
            btn = ImgButton(pm)
            btn.setFixedSize(self._thumb_px, self._thumb_px)
            btn.setAutoExclusive(True)
            btn.clicked.connect(self.updateFocus)
            self.frame_timeline.addWidget(btn)

        # Add "Next Page" button (right arrow)
        self.next_page_button = QPushButton("→")
        self.next_page_button.setFixedSize(40, 40)
        self.next_page_button.clicked.connect(
            lambda: self.navigatePage("next"))
        self.frame_timeline.addWidget(self.next_page_button)

        # Add "Last Page" button (double right arrow)
        self.last_page_button = QPushButton("»")
        self.last_page_button.setFixedSize(40, 40)
        self.last_page_button.clicked.connect(
            lambda: self.navigatePage("last"))
        self.frame_timeline.addWidget(self.last_page_button)

        self.updatePageNavButtons()

    def downloadTrace(self):
        self.status.setText("Currently downloading. Please wait...")
        _pull_helper = AdbThread()
        cancelled = _pull_helper.run_with_progress(
            parent=self,
            title="Downloading trace...",
            adb=self.replay_widget.adb,
            file=self.replay_widget.currentTrace,
            path="tmp",
            action="pull",
            on_cancel=lambda: None,
        )
        if cancelled:
            self.status.clear()
            return
        msg = QMessageBox()
        msg_text = f" The trace was downloaded here: {os.getcwd()}/tmp"
        msg.setText(msg_text)
        msg.exec()
        self.status.clear()

    def updateFocus(self, img):
        """
        Update focus to selected frame
        """
        nav_buttons_offset = 2
        for i in range(
                nav_buttons_offset, self.frame_timeline.count() -
                nav_buttons_offset):
            widget = self.frame_timeline.itemAt(i).widget()
            if isinstance(widget, ImgButton):
                if widget.isChecked():
                    global_index = self.current_page * self.images_per_page + i - nav_buttons_offset
                    img = self.images[global_index]
                    self.current_focus_image_index = self.image_indices[global_index]
                    self.framerange_frame.setText(
                        "Frame: {}".format(
                            self.current_focus_image_index))
                    self.page_info.setText(
                        "Page: {}/{}".format(self.current_page + 1, self.total_pages))

        self.current_focus_image_path = img
        self._set_focus_image(self.current_focus_image_path)

    def setStartFrame(self):
        """
        Select start frame
        """
        self.current_range_start = self.current_focus_image_index
        self.framerange_label.setText(
            f"Current framerange: [{self.current_range_start}-{self.current_range_end})")

    def setEndFrame(self):
        """
        Select end frame
        """
        self.current_range_end = self.current_focus_image_index
        self.framerange_label.setText(
            f"Current framerange: [{self.current_range_start}-{self.current_range_end})")

    def validate_framerange(self):
        """
        Check validity of framerange. Logs error message if not valid

        Return:
            bool: False if not valid range, true if valid range
        """
        if self.current_range_start > self.current_range_end:
            logger.error(
                f"Selected range start frame is greater than end frame: [{self.current_range_start}-{self.current_range_end})")
            return False

        elif (self.current_range_end == 0 and self.current_range_start == 0):
            logger.error(f"No frames selected.")
            return False

        elif self.current_range_start == self.current_range_end:
            logger.error(
                f"Selected range start frame is the same as end frame: [{self.current_range_start}-{self.current_range_end})")
            return False

        elif self.current_range_start == -1:
            logger.error(
                f"Selected range start frame is invalid: [{self.current_range_start}-{self.current_range_end})")
            return False

        elif self.current_range_end == -1:
            logger.error(
                f"Selected range end frame is invalid: [{self.current_range_start}-{self.current_range_end})")
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
                    logger.error(
                        "The textual framerange input is invalid, must have format: [<int>-<int>). Ignoring.")
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
            logger.warning(f"Chosen frame range invalid")
            msg = QMessageBox()
            msg_text = " Please select a valid frame range."
            msg.setText(msg_text)
            msg.exec()
            self.next_signal.emit(PageIndex.FRAMERANGE)
            return False
        logger.info(
            f"Frame range set to: [{self.current_range_start}-{self.current_range_end})")
        self.gotoframeselection_signal.emit()
        self.next_signal.emit(PageIndex.FRAME_SELECTION)

    def cleanup_page(self):
        """
        Reset variables
        """
        self.current_focus_image_index = 0
        self.current_range_start = 0
        self.current_range_end = 0
        self.current_page = 0
        self.page_info.setText(
            "Page: 0/0")
        self.framerange_frame.setText("Frame: 0")
        self.framerange_label.setText("Current framerange: 0-0")
        self.framerange_input.clear()
        if self.frame_focus is not None:
            self.frame_focus.clear()
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
            self.remove_alpha.show()
            if hasattr(self, "frame_focus"):
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
            self.remove_alpha.hide()
            if hasattr(self, "frame_focus"):
                self.frame_focus.hide()
            if hasattr(self, "missing_img"):
                self.missing_img.show()
