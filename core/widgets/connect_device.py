from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt, Signal
from core.page_navigation import PageNavigation


class UIConnectDevice(PageNavigation):
    device_selected = Signal()

    def cleanup_page(self):
        """
        Reset variables
        """
        self.device_window = None

    def __init__(self, adb):
        """
        Initialize the page for connecting devices

        Args:
            adb: android devices connected
        """
        super().__init__()
        # TODO split into functions and add proper device handling
        self.adb = adb
        self.adb.init()  # In case a device has been connected / disconnected

        h_layout = QHBoxLayout()
        v_layout = QVBoxLayout()

        if len(self.adb.devices) == 0:
            label = QLabel("No Android devices connected. \n Connect a device and ensure USB Preference is set to FileTransfer")
            label.setAlignment(Qt.AlignCenter)

            v2_layout = QVBoxLayout()
            config_text = QLabel(" ")
            h_layout.addLayout(v2_layout)

        else:
            label = QLabel("Select Android Device...")
            label.setAlignment(Qt.AlignCenter)

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
                button.setCheckable(False)
                button.clicked.connect(lambda *, device_index=device_index: self.device_button_clicked(self.adb.devices[device_index]))
                v2_layout.addWidget(button)
                v2_layout.addWidget(config_text)

                h_layout.addLayout(v2_layout)

        v_layout.addWidget(label)
        v_layout.addLayout(h_layout)
        v_layout.setAlignment(Qt.AlignCenter)

        self.setLayout(v_layout)

    def device_button_clicked(self, device):
        """
        Set device upon button click and emits signal

        Args:
            device (str): the device choses/clicked
        """
        self.adb.device = device
        self.device_selected.emit()
        self.next_signal.emit(1)


