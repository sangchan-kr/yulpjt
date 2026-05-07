from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Control System")
        self.resize(1024, 600)

        title = QLabel("Control System — booting...")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px;")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(title)
        self.setCentralWidget(central)
