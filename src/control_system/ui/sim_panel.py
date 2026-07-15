"""입력 시뮬레이터 패널 (mock 전용).

실 하드웨어의 DI/아날로그 입력을 손으로 흉내 내어, 하드웨어 없이 노트북에서
상태머신을 끝까지 돌려볼 수 있게 한다. MOCK_HW=0 이면 표시하지 않는다.

- 유지형 입력(셀렉터/센서/SOL_ENABLE/VACUUM_OK) → 체크박스
- 순간 입력(Auto Start/Stop, Manual Up/Down 버튼) → 누르는 동안만 ON
- 로드셀 하중 → 슬라이더(0~full_scale kgf)로 AI-00 mA 를 만든다
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QGroupBox, QLabel, QPushButton, QSlider, QVBoxLayout,
)

from ..hardware.signals import DI1, DI2


# 유지형 / 순간형 입력 분류
_TOGGLE = [
    (DI1, DI1.MODE_AUTO), (DI1, DI1.CYL_UP_POS), (DI1, DI1.CYL_DOWN_POS),
    (DI1, DI1.SOL_ENABLE_OK), (DI2, DI2.VACUUM_OK), (DI2, DI2.AIR_PRESS_OK),
]
_MOMENTARY = [
    (DI1, DI1.AUTO_START_PB), (DI1, DI1.AUTO_STOP_PB),
    (DI1, DI1.MANUAL_UP_PB), (DI1, DI1.MANUAL_DOWN_PB),
]


class SimPanel(QGroupBox):
    def __init__(self, cfg, adam1, adam2, adam4017) -> None:
        super().__init__("입력 시뮬레이터 (MOCK — 실 하드웨어에서는 숨김)")
        self.cfg = cfg
        self.full_scale = cfg.loadcell_full_scale_kgf
        self._mod = {DI1: adam1, DI2: adam2}
        self._ai = adam4017

        root = QVBoxLayout(self)

        toggles = QGridLayout()
        for i, (cls, sig) in enumerate(_TOGGLE):
            cb = QCheckBox(sig.name)
            cb.toggled.connect(lambda on, c=cls, s=sig: self._mod[c].set_mock_di(int(s), on))
            toggles.addWidget(cb, i // 3, i % 3)
        root.addLayout(toggles)

        momentary = QGridLayout()
        for i, (cls, sig) in enumerate(_MOMENTARY):
            btn = QPushButton(sig.name)
            mod = self._mod[cls]
            ch = int(sig)
            btn.pressed.connect(lambda m=mod, c=ch: m.set_mock_di(c, True))
            btn.released.connect(lambda m=mod, c=ch: m.set_mock_di(c, False))
            momentary.addWidget(btn, i // 2, i % 2)
        root.addLayout(momentary)

        self._load_label = QLabel()
        root.addWidget(self._load_label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, int(self.full_scale))
        slider.valueChanged.connect(self._on_load)
        root.addWidget(slider)
        self._on_load(0)

    def _on_load(self, kgf: int) -> None:
        self._ai.set_mock_load_kgf(0, float(kgf), self.full_scale)
        self._load_label.setText(f"로드셀 하중 시뮬레이션: {kgf} kgf")
