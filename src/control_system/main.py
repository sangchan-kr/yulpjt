import sys
from PySide6.QtWidgets import QApplication
from .config import Config
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Control System")
    cfg = Config()
    window = MainWindow(cfg)
    window.show()
    return app.exec()
