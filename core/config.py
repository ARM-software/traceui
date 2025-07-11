import configparser

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QLineEdit, QFormLayout, QPushButton, QFileDialog


class ConfigSettings():
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_path = Path('./config.ini')
        self.img_path = Path('./tmp/replay_imgs')
        self.hwc_path = Path('./tmp/hwc')

        # Load config.ini if exists and is valid, otherwise create it
        try:
            self.config_data = self.load_config()
        except configparser.NoSectionError:
            if self.config_path.exists():
                old_config_path = Path('./old_config.ini')
                self.config_path.rename(old_config_path)
                print(f"[ INFO ] Cannot parse {self.config_path}\nOld config file moved to {old_config_path}\nRecreating config file...")
            else:
                print(f"[ INFO ] {self.config_path} not found. Creating config file...")
            self.create_config()
            self.config_data = self.load_config()

    def get_config(self):
        return self.config_data

    def create_config(self):
        # TODO add more helpful settings(debug mode, log level, user configs)
        self.config['Paths'] = {'pat_path': '', 'gfxr_path': '', 'img_path': self.img_path, 'hwc_path': self.hwc_path}

        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)

    def load_config(self):
        self.config.read(self.config_path)

        pat_path = self.config.get('Paths', 'pat_path')
        gfxr_path = self.config.get('Paths', 'gfxr_path')
        img_path = self.config.get('Paths', 'img_path')
        hwc_path = self.config.get('Paths', 'hwc_path')

        config_values = {
            'Paths': {
                'pat_path': pat_path,
                'gfxr_path': gfxr_path,
                'img_path': img_path,
                'hwc_path': hwc_path
            }
        }

        return config_values

    def update_config(self, section, key, value):
        self.config.set(section, key, value)
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)


class ConfigPatraceWindow(QWidget):

    def __init__(self, pat_path):
        super().__init__()
        self.path = pat_path
        self.key = "pat_path"
        get_label(self, "PATrace Configuration")


class ConfigGfxrWindow(QWidget):

    def __init__(self, gfxr_path):
        super().__init__()
        self.path = gfxr_path
        self.key = "gfxr_path"
        get_label(self, "GFXReconstruct Configuration")


class ClickableQLineEdit(QLineEdit):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(event)


def get_label(self, label):
    self.setWindowTitle(label)
    header_label = QLabel(label)
    path_label = QLabel("Binary path:")
    self.line_edit = ClickableQLineEdit(self.path)
    self.line_edit.setReadOnly(True)
    self.line_edit.clicked.connect(lambda: openFileExplorer(self.line_edit))
    b = QPushButton("Save")
    b.clicked.connect(lambda: update_paths(self, self.key))

    v_layout = QVBoxLayout()
    v_layout.addWidget(header_label)

    form_layout = QFormLayout()
    form_layout.addRow(path_label, self.line_edit)

    v_layout.addLayout(form_layout)
    v_layout.addWidget(b)
    self.setLayout(v_layout)
    self.show()


def openFileExplorer(line_edit, file=False):
    if file:
        trace, filter = QFileDialog.getOpenFileName(None, 'Import trace', 'C:\\', "Trace files (*.pat *.gfxr)")
        line_edit.setText(trace)
    else:
        dir = QFileDialog.getExistingDirectory(None, 'Select Binary Directory:', 'C:\\', QFileDialog.ShowDirsOnly)
        line_edit.setText(dir)


def update_paths(self, key):
    path = self.line_edit.text()
    ConfigSettings().update_config('Paths', key, path)
    self.close()


class TracerConfig():
    def __init__(self, pa_path, gfxr_path):
        self.pa_path = pa_path
        self.gfxr_path = gfxr_path
