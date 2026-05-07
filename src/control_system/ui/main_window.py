from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QGridLayout,
    QPushButton, QWidget,
)

from ..config import Config
from ..hardware.loadcell import LoadCell
from ..hardware.adam_di import AdamDigitalInput
from ..hardware.adam_relay import AdamRelay


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.setWindowTitle("Control System")
        self.resize(1024, 600)

        self.loadcell = LoadCell(
            cfg.hx711_dt_pin, cfg.hx711_sck_pin, mock=cfg.mock_hardware
        )
        self.di = AdamDigitalInput(
            cfg.adam_serial_port, cfg.adam_baudrate, cfg.adam_di_address,
            mock=cfg.mock_hardware,
        )
        self.do = AdamRelay(
            cfg.adam_serial_port, cfg.adam_baudrate, cfg.adam_do_address,
            mock=cfg.mock_hardware,
        )

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)

        self.weight_label = QLabel("--- g")
        self.weight_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weight_label.setStyleSheet("font-size: 48px; font-weight: bold;")
        outer.addWidget(self.weight_label)

        di_grid = QGridLayout()
        self.di_lamps: list[QLabel] = []
        for i in range(AdamDigitalInput.NUM_CHANNELS):
            lamp = QLabel(f"DI{i + 1:02d}")
            lamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lamp.setStyleSheet(self._lamp_style(False))
            self.di_lamps.append(lamp)
            di_grid.addWidget(lamp, i // 4, i % 4)
        outer.addLayout(di_grid)

        do_grid = QGridLayout()
        self.do_buttons: list[QPushButton] = []
        for i in range(AdamRelay.NUM_CHANNELS):
            btn = QPushButton(f"Relay {i + 1}")
            btn.setCheckable(True)
            btn.toggled.connect(lambda on, ch=i: self.do.set_channel(ch, on))
            self.do_buttons.append(btn)
            do_grid.addWidget(btn, i // 4, i % 4)
        outer.addLayout(do_grid)

        self.setCentralWidget(central)

    @staticmethod
    def _lamp_style(on: bool) -> str:
        color = "#3c3" if on else "#444"
        return f"background:{color}; color:white; padding:8px; border-radius:6px;"

    def _tick(self) -> None:
        self.weight_label.setText(f"{self.loadcell.read_grams():.1f} g")
        for lamp, state in zip(self.di_lamps, self.di.read_all()):
            lamp.setStyleSheet(self._lamp_style(state))
