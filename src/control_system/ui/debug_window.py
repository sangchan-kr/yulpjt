"""I/O 디버그 창 (mock 전용, HMI 와 별도 top-level 창).

목적: 실 하드웨어 없이 두 ADAM-4055-C 의 모든 DI 를 손으로 주입하고,
모든 DO 를 실시간으로 보며, ADAM-4017+ 아날로그(로드셀)를 슬라이더로 넣는다.
비상정지(SOL_ENABLE_OK) 바이패스도 여기서 체크 한 번으로 가능하다.

- 왼쪽: DI 주입 (ADAM #1 / #2) — 체크박스(유지). 순간 버튼(Auto Start 등)은
  켰다 끄면 rising edge 로 인식된다.
- 가운데: 아날로그(로드셀 mA/kgf) 슬라이더 + 빠른 토글.
- 오른쪽: DO 출력 램프 (ADAM #1 / #2) — 컨트롤러가 실제로 쓴 값을 표시.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ..hardware.signals import AI, DI1, DI2, DO1, DO2
from . import theme


class DebugWindow(QWidget):
    def __init__(self, controller, adam1, adam2, adam4017) -> None:
        super().__init__()
        self.ctrl = controller
        self.a1, self.a2, self.ai = adam1, adam2, adam4017
        self.setWindowTitle("I/O 디버그 (mock)")
        self.setStyleSheet(theme.QSS + f"QWidget{{background:{theme.BG};}}")
        self.resize(760, 620)

        root = QVBoxLayout(self)
        hint = QLabel("mock I/O 주입/관찰용. 비상정지 해제는 ADAM#1 DI-07 SOL_ENABLE_OK 체크.")
        hint.setStyleSheet(f"color:{theme.YELLOW}; font-weight:700;")
        root.addWidget(hint)

        cols = QHBoxLayout()
        cols.addWidget(self._di_group("ADAM-4055-C #1  DI 입력", DI1, self.a1))
        cols.addWidget(self._di_group("ADAM-4055-C #2  DI 입력", DI2, self.a2))
        root.addLayout(cols)

        root.addWidget(self._analog_group())

        outs = QHBoxLayout()
        outs.addWidget(self._do_group("ADAM #1  DO 출력", DO1))
        outs.addWidget(self._do_group("ADAM #2  DO 출력", DO2))
        root.addLayout(outs)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(100)

    # ---------------------------------------------------------------- DI 주입
    def _di_group(self, title: str, enum_cls, module) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        self_checks = getattr(self, "_di_checks", None)
        if self_checks is None:
            self._di_checks = {}
        for i, sig in enumerate(enum_cls):
            cb = QCheckBox(f"{int(sig)} {sig.name}")
            cb.toggled.connect(lambda on, m=module, ch=int(sig): m.set_mock_di(ch, on))
            self._di_checks[(enum_cls.__name__, int(sig))] = cb
            grid.addWidget(cb, i, 0)
        return box

    # ---------------------------------------------------------------- 아날로그
    def _analog_group(self) -> QGroupBox:
        box = QGroupBox("ADAM-4017+  아날로그 입력 (로드셀 AI-00)")
        lay = QVBoxLayout(box)
        self._ai_label = QLabel("-")
        self._ai_label.setStyleSheet("font-weight:800;")
        lay.addWidget(self._ai_label)
        self._fs = self.ctrl.loadcell.full_scale_kgf
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, int(self._fs))
        self._slider.valueChanged.connect(self._on_load)
        lay.addWidget(self._slider)
        return box

    def _on_load(self, kgf: int) -> None:
        self.ai.set_mock_load_kgf(int(AI.LOADCELL_CURRENT), float(kgf), self._fs)

    # ---------------------------------------------------------------- DO 출력
    def _do_group(self, title: str, enum_cls) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        lamps = getattr(self, "_do_lamps", None)
        if lamps is None:
            self._do_lamps = {}
        for i, sig in enumerate(enum_cls):
            lamp = QLabel(f"{int(sig)} {sig.name}")
            lamp.setStyleSheet(self._lamp_style(False))
            self._do_lamps[(enum_cls.__name__, int(sig))] = lamp
            grid.addWidget(lamp, i, 0)
        return box

    @staticmethod
    def _lamp_style(on: bool) -> str:
        bg = theme.GREEN if on else "#243044"
        fg = "#0b1220" if on else theme.MUTED
        return f"background:{bg}; color:{fg}; padding:4px 8px; border-radius:5px; font-weight:700;"

    # ---------------------------------------------------------------- 갱신
    def _refresh(self) -> None:
        ma = self.ai.read_ma(int(AI.LOADCELL_CURRENT))
        self._ai_label.setText(
            f"{ma:.2f} mA  →  {self.ctrl.loadcell.read_kgf():.1f} kgf"
            f"   (상태: {self.ctrl.state.value})"
        )
        do1, do2 = self.a1.read_do(), self.a2.read_do()
        for i, sig in enumerate(DO1):
            self._do_lamps[("DO1", int(sig))].setStyleSheet(self._lamp_style(do1[i]))
        for i, sig in enumerate(DO2):
            self._do_lamps[("DO2", int(sig))].setStyleSheet(self._lamp_style(do2[i]))
