"""Phase A 임시 HMI — 새 하드웨어 계층이 살아있는지 눈으로 보는 최소 화면.

정식 HMI(상태머신 연동, 모드/카운트/진공/알람/시그널타워/Safety Reset 등)는
Phase C 에서 재작성한다. 지금은:
  - 로드셀 하중(kgf)/전류(mA) 표시
  - DI1/DI2 램프 (신호 이름)
  - DO1/DO2 토글 버튼 (stage→flush)
  - mock 모드일 때 DI 를 손으로 토글하는 체크박스 (시뮬레이터 맛보기)
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QVBoxLayout, QWidget,
)

from ..config import Config
from ..hardware.signals import AI, DI1, DI2, DO1, DO2, IO


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, io: IO, loadcell, adam1, adam2, adam4017) -> None:
        super().__init__()
        self.cfg = cfg
        self.io = io
        self.loadcell = loadcell
        self.a1 = adam1
        self.a2 = adam2
        self.setWindowTitle("Control System (v1.12 — Phase A)")
        if not cfg.mock_hardware:
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

        self._di_lamps: dict = {}
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(cfg.poll_ms)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)

        self.load_label = QLabel("--- kgf")
        self.load_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.load_label.setStyleSheet("font-size: 40px; font-weight: bold;")
        outer.addWidget(self.load_label)

        self.ma_label = QLabel("--- mA")
        self.ma_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.ma_label)

        di_row = QHBoxLayout()
        di_row.addWidget(self._di_group("ADAM #1 DI", DI1))
        di_row.addWidget(self._di_group("ADAM #2 DI", DI2))
        outer.addLayout(di_row)

        do_row = QHBoxLayout()
        do_row.addWidget(self._do_group("ADAM #1 DO", DO1))
        do_row.addWidget(self._do_group("ADAM #2 DO", DO2))
        outer.addLayout(do_row)

        if self.cfg.mock_hardware:
            outer.addWidget(self._mock_group())

        self.setCentralWidget(central)

    def _di_group(self, title: str, enum_cls) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        for i, sig in enumerate(enum_cls):
            lamp = QLabel(sig.name)
            lamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lamp.setStyleSheet(self._lamp_style(False))
            self._di_lamps[sig] = lamp
            grid.addWidget(lamp, i // 2, i % 2)
        return box

    def _do_group(self, title: str, enum_cls) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        for i, sig in enumerate(enum_cls):
            btn = QPushButton(sig.name)
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.toggled.connect(lambda on, s=sig: self._on_do_toggle(s, on))
            grid.addWidget(btn, i // 2, i % 2)
        return box

    def _mock_group(self) -> QGroupBox:
        box = QGroupBox("MOCK 입력 (시뮬레이터 맛보기 — Phase C 에서 정식 패널)")
        grid = QGridLayout(box)
        col = 0
        for enum_cls, module in ((DI1, self.a1), (DI2, self.a2)):
            for i, sig in enumerate(enum_cls):
                cb = QCheckBox(sig.name)
                cb.toggled.connect(
                    lambda on, m=module, ch=int(sig): m.set_mock_di(ch, on)
                )
                grid.addWidget(cb, i, col)
            col += 1
        return box

    # -------------------------------------------------------------- events
    def _on_do_toggle(self, sig, on: bool) -> None:
        self.io.set(sig, on)
        self.io.flush_outputs()

    def _tick(self) -> None:
        self.io.refresh_inputs()
        kgf = self.loadcell.read_kgf()
        ma = self.io.ma(AI.LOADCELL_CURRENT)
        self.load_label.setText(f"{kgf:.1f} kgf")
        self.ma_label.setText(f"{ma:.2f} mA")
        for sig, lamp in self._di_lamps.items():
            lamp.setStyleSheet(self._lamp_style(self.io.di(sig)))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _lamp_style(on: bool) -> str:
        color = "#3c3" if on else "#444"
        return f"background:{color}; color:white; padding:6px; border-radius:5px;"
