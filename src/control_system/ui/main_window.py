"""정식 HMI (v1.12 §10·15) — 컨트롤러 연동.

QTimer 로 controller.scan() 을 주기 실행하고 상태를 화면에 그린다.
출력은 컨트롤러만 구동한다(HMI 는 명령 플래그만 전달). 진공은 HMI 토글 버튼
하나로 수동 제어한다(결정3). mock 모드에서는 하단에 입력 시뮬레이터를 붙인다.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QKeyEvent
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QVBoxLayout, QWidget,
)

from ..config import Config
from ..core.controller import Controller
from ..core.states import State
from ..hardware.signals import DI1
from .logging_csv import CsvLogger
from .sim_panel import SimPanel


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, controller: Controller, adam1, adam2, adam4017,
                 logger: CsvLogger) -> None:
        super().__init__()
        self.cfg = cfg
        self.ctrl = controller
        self.logger = logger
        self._prev_count = controller.count
        self.setWindowTitle("공압 가압 제어 시스템 (v1.12)")
        if not cfg.mock_hardware:
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

        self._build_ui(adam1, adam2, adam4017)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(cfg.poll_ms)

    # ------------------------------------------------------------------ UI
    def _build_ui(self, a1, a2, ai) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        top.addWidget(self._tower_box(), 0)
        top.addWidget(self._load_box(), 1)
        root.addLayout(top)

        root.addWidget(self._status_box())
        root.addWidget(self._button_box())

        if self.cfg.mock_hardware:
            root.addWidget(SimPanel(self.cfg, a1, a2, ai))

        self.setCentralWidget(central)

    def _tower_box(self) -> QGroupBox:
        box = QGroupBox("시그널 타워")
        lay = QVBoxLayout(box)
        self._tower = {}
        for key, on_color in (("red", "#e33"), ("yellow", "#ec3"), ("green", "#3c3")):
            lamp = QLabel()
            lamp.setFixedSize(60, 40)
            lamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tower[key] = (lamp, on_color)
            lay.addWidget(lamp, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._buzzer = QLabel("부저")
        self._buzzer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._buzzer)
        return box

    def _load_box(self) -> QGroupBox:
        box = QGroupBox("하중")
        lay = QVBoxLayout(box)
        self.load_label = QLabel("--- kgf")
        self.load_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.load_label.setStyleSheet("font-size: 48px; font-weight: bold;")
        lay.addWidget(self.load_label)
        self.max_label = QLabel("최대 --- kgf")
        self.max_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.max_label)
        return box

    def _status_box(self) -> QGroupBox:
        box = QGroupBox("상태")
        grid = QGridLayout(box)
        self._status: dict[str, QLabel] = {}
        fields = [
            ("mode", "모드"), ("state", "상태"), ("cyl", "실린더"),
            ("count", "카운트"), ("vacuum", "진공"), ("sol", "SOL_ENABLE"),
        ]
        for i, (key, title) in enumerate(fields):
            grid.addWidget(QLabel(f"{title}:"), i // 3, (i % 3) * 2)
            val = QLabel("-")
            val.setStyleSheet("font-weight: bold;")
            self._status[key] = val
            grid.addWidget(val, i // 3, (i % 3) * 2 + 1)
        self.alarm_label = QLabel("알람: 없음")
        self.alarm_label.setStyleSheet("color:#c00; font-weight:bold;")
        grid.addWidget(self.alarm_label, 2, 0, 1, 6)
        return box

    def _button_box(self) -> QGroupBox:
        box = QGroupBox("조작")
        lay = QHBoxLayout(box)

        for text, slot in (
            ("Safety Reset", self.ctrl.cmd_safety_reset),
            ("Alarm Clear", self.ctrl.cmd_alarm_clear),
            ("Count Reset", self.ctrl.cmd_count_reset),
            ("Load Zero", self.ctrl.cmd_load_zero),
        ):
            btn = QPushButton(text)
            btn.setMinimumHeight(60)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        self.vacuum_btn = QPushButton("진공 흡착")
        self.vacuum_btn.setCheckable(True)
        self.vacuum_btn.setMinimumHeight(60)
        self.vacuum_btn.toggled.connect(self.ctrl.set_vacuum)
        lay.addWidget(self.vacuum_btn)
        return box

    # -------------------------------------------------------------- 주기 갱신
    def _tick(self) -> None:
        self.ctrl.scan()
        self._update_status()
        self._maybe_log()

    def _update_status(self) -> None:
        c = self.ctrl
        self.load_label.setText(f"{c.load_kgf:.1f} kgf")
        self.max_label.setText(f"최대 {c.max_load_kgf:.1f} kgf")

        self._status["mode"].setText("Auto" if c.mode_auto else "Manual")
        self._status["state"].setText(c.state.value)
        self._status["cyl"].setText(self._cyl_text())
        self._status["count"].setText(f"{c.count} / {c.target_count}")
        self._status["vacuum"].setText("OK" if c.vacuum_ok else "Not OK")
        self._status["sol"].setText("ON" if c.sol_enable_ok else "OFF")

        alarms = ", ".join(sorted(a.value for a in c.alarms))
        self.alarm_label.setText(f"알람: {alarms}" if alarms else "알람: 없음")

        o = c.out
        self._set_lamp("red", o.tower_red)
        self._set_lamp("yellow", o.tower_yellow)
        self._set_lamp("green", o.tower_green)
        self._buzzer.setStyleSheet(
            "background:#e33;color:white;" if o.tower_buzzer else "color:#888;"
        )

    def _cyl_text(self) -> str:
        up = self.ctrl.io.di(DI1.CYL_UP_POS)
        down = self.ctrl.io.di(DI1.CYL_DOWN_POS)
        if up and not down:
            return "Up"
        if down and not up:
            return "Down"
        return "Unknown"

    def _set_lamp(self, key: str, on: bool) -> None:
        lamp, color = self._tower[key]
        lamp.setStyleSheet(
            f"background:{color if on else '#333'}; border-radius:8px;"
        )

    def _maybe_log(self) -> None:
        if self.ctrl.count > self._prev_count:
            self.logger.log_cycle(self.ctrl.count, self.ctrl.max_load_kgf, self.ctrl.alarms)
        self._prev_count = self.ctrl.count

    # -------------------------------------------------------------- events
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
