from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QWidget
from PySide6.QtCore import Qt, Signal
from core.page_navigation import PageNavigation
import adblib


class UIConnectDevice(PageNavigation):
    device_selected = Signal()

    def cleanup_page(self):
        """
        Reset variables
        """
        self.device_window = None
        self.refresh()

    def __init__(self, adb):
        """
        Initialize the page for connecting devices

        Args:
            adb: android devices connected
        """
        super().__init__()
        self.adb = adb
        self.setUpWidgets()
        self.setUpLayout()
        self.refresh()
        self.setVisibility()

    def setUpWidgets(self):
        """
        Set up widgets
        """
        self.label_no_device = QLabel("No Android devices connected.\nConnect a device and ensure USB Preference is set to FileTransfer")
        self.label_connected = QLabel("Select Android Device")
        self.label_gap = QLabel("\n\n")
        self.refresh_button = QPushButton("Refresh devices")
        self.refresh_button.setFixedWidth(self.label_connected.sizeHint().width())
        self.refresh_button.clicked.connect(self.refresh)

    def setUpLayout(self):
        """
        Set layout of the page
        """
        self.h_layout = QHBoxLayout()
        self.all_widgets = QWidget()
        self.all_widgets.setLayout(self.h_layout)
        v_layout = QVBoxLayout()
        v_layout.addStretch()
        v_layout.addWidget(self.label_no_device, alignment=Qt.AlignCenter)
        v_layout.addWidget(self.label_connected, alignment=Qt.AlignCenter)
        v_layout.addWidget(self.all_widgets, alignment=Qt.AlignCenter)
        v_layout.addWidget(self.label_gap)
        v_layout.addWidget(self.refresh_button, alignment=Qt.AlignCenter)
        v_layout.addStretch()

        self.setLayout(v_layout)


    def setVisibility(self):
        """
        Set visibility based on decives connected
        """
        if len(self.adb.devices):
            self.label_no_device.hide()
            self.label_connected.show()
            self.all_widgets.show()

        else:
            self.label_no_device.show()
            self.label_connected.hide()
            self.all_widgets.hide()

    def _cleanupWidget(self):
        """
        Clean up layout containing different devices
        """
        while self.h_layout.count():
            item = self.h_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                child_layout = item.layout()
                if child_layout is not None:
                    while child_layout.count():
                        sub_item = child_layout.takeAt(0)
                        sub_widget = sub_item.widget()
                        if sub_widget:
                            sub_widget.setParent(None)
                            sub_widget.deleteLater()

    def refresh(self):
        """
        Refresh devices connected
        """
        self._cleanupWidget()
        self.adb = adblib.adb()
        self.adb.init()
        for device_index, device in enumerate(self.adb.devices):
            v2_layout = QVBoxLayout()
            config = self.adb.configs[device].copy()
            button = QPushButton(config['model'])
            # TODO - fix text description to contain wanted fields
            text = f"""
                abi: {config['abi']}
                android: {config['android']}
                sdk: {config['sdk']}
                soc: {config['soc']}
                manufacturer: {config['manufacturer']}
                gpu: {config['gpu']}
                """
            config_text = QLabel(text)
            button.setFixedWidth(config_text.sizeHint().width())
            button.setCheckable(False)
            button.clicked.connect(lambda *, device_index=device_index: self.device_button_clicked(self.adb.devices[device_index]))
            v2_layout.addWidget(button)
            v2_layout.addWidget(config_text)
            widget = QWidget()
            widget.setLayout(v2_layout)
            self.h_layout.addWidget(widget)
        self.setVisibility()

    def device_button_clicked(self, device):
        """
        Set device upon button click and emits signal

        Args:
            device (str): the device choses/clicked
        """
        self.adb.device = device
        self.device_selected.emit()
        self.next_signal.emit(1)
