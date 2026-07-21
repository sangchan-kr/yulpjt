"""HMI 셸 (목업 v0.3) — 상단바 + 상태 스트립 + 페이지 스택 + 하단 네비 + Safety 오버레이.

QTimer 로 controller.scan() 을 주기 실행하고 공통 영역/현재 페이지를 갱신한다.
출력은 컨트롤러만 구동(HMI 는 명령 플래그 전달). mock 모드에선 SIM 페이지를 추가한다.
"""

import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..config import Config
from ..core.controller import Controller
from ..core.states import State
from . import theme
from .logging_csv import CsvLogger
from .pages.main_page import MainPage
from .pages.placeholders import PlaceholderPage
from .sim_panel import SimPanel

_AUTO_RUNNING = {
    State.AUTO_PRECHECK, State.AUTO_MOVE_DOWN, State.AUTO_DWELL_DOWN,
    State.AUTO_MOVE_UP, State.AUTO_DWELL_UP, State.AUTO_COUNT_UPDATE,
}


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, controller: Controller, adam1, adam2, adam4017,
                 logger: CsvLogger) -> None:
        super().__init__()
        self.cfg = cfg
        self.ctrl = controller
        self.logger = logger
        self._prev_count = controller.count
        self.setWindowTitle("반복 가압 측정기")
        if not cfg.mock_hardware:
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

        root = QWidget()
        root.setObjectName("root")
        self.setStyleSheet(theme.QSS)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_topbar())
        outer.addWidget(self._build_status_strip())
        outer.addWidget(self._build_stack(adam1, adam2, adam4017), 1)
        outer.addWidget(self._build_bottom_nav())
        self.setCentralWidget(root)

        self._overlay = self._build_safety_overlay(root)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(cfg.poll_ms)

    # ---------------------------------------------------------------- 상단바
    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topbar")
        bar.setFixedHeight(54)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        brand = QLabel("반복 가압 측정기")
        brand.setObjectName("brand")
        self._mode_badge = QLabel("MANUAL")
        self._state_badge = QLabel("IDLE")
        self._clock = QLabel("")
        self._clock.setObjectName("clock")
        gear = QLabel("⚙")
        gear.setStyleSheet("font-size:20px;")
        lay.addWidget(brand)
        lay.addSpacing(12)
        lay.addWidget(self._mode_badge)
        lay.addWidget(self._state_badge)
        lay.addStretch(1)
        lay.addWidget(self._clock)
        lay.addSpacing(10)
        lay.addWidget(gear)
        return bar

    # ---------------------------------------------------------------- 상태 스트립
    def _build_status_strip(self) -> QWidget:
        strip = QWidget()
        strip.setObjectName("statusStrip")
        strip.setFixedHeight(48)
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(14, 7, 14, 7)
        lay.setSpacing(8)
        self._pills = {}
        for key in ("sol", "cyl", "vacuum", "loadcell", "adam"):
            frame = QFrame()
            frame.setObjectName("card")
            row = QHBoxLayout(frame)
            row.setContentsMargins(10, 4, 10, 4)
            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(theme.dot_qss(theme.OFF))
            text = QLabel("-")
            text.setStyleSheet("font-weight:800; font-size:12px;")
            row.addWidget(dot)
            row.addWidget(text, 1, Qt.AlignmentFlag.AlignCenter)
            self._pills[key] = (dot, text)
            lay.addWidget(frame)
        return strip

    # ---------------------------------------------------------------- 페이지 스택
    def _build_stack(self, a1, a2, ai) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._main_page = MainPage(self.ctrl)
        self._pages = [
            ("운전", self._main_page),
            ("조건설정", PlaceholderPage("운전 조건 설정")),
            ("시스템상태", PlaceholderPage("시스템 상태")),
            ("로그", PlaceholderPage("로그 및 트렌드")),
            ("도움말", PlaceholderPage("도움말")),
        ]
        if self.cfg.mock_hardware:
            self._pages.append(("SIM", SimPanel(self.cfg, a1, a2, ai)))
        for _, w in self._pages:
            self._stack.addWidget(w)
        return self._stack

    # ---------------------------------------------------------------- 하단 네비
    def _build_bottom_nav(self) -> QWidget:
        nav = QWidget()
        nav.setObjectName("bottomNav")
        nav.setFixedHeight(58)
        lay = QHBoxLayout(nav)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(8)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for i, (label, _) in enumerate(self._pages):
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, idx=i: self._stack.setCurrentIndex(idx))
            self._nav_group.addButton(btn, i)
            lay.addWidget(btn)
        self._nav_group.button(0).setChecked(True)
        return nav

    # ---------------------------------------------------------------- Safety 오버레이
    def _build_safety_overlay(self, parent: QWidget) -> QFrame:
        ov = QFrame(parent)
        ov.setStyleSheet("background: rgba(5,9,17,190);")
        box = QFrame(ov)
        box.setStyleSheet(f"background:#35171b; border:2px solid {theme.RED}; border-radius:14px;")
        box.setFixedWidth(600)
        v = QVBoxLayout(box)
        v.setContentsMargins(22, 18, 22, 18)
        title = QLabel("SAFETY STOP")
        title.setStyleSheet("color:#ffc4c8; font-size:26px; font-weight:900;")
        msg = QLabel(
            "액추에이터 구동 허가가 차단되었습니다. 진공 출력도 강제 OFF 되었습니다.\n\n"
            "1. 비상정지 버튼을 해제하십시오.\n"
            "2. Area Sensor 감지영역을 비우십시오.\n"
            "3. SOL ENABLE 상태가 ON 으로 복귀했는지 확인하십시오.\n"
            "4. Safety Reset 후 진공은 자동 복원되지 않습니다."
        )
        msg.setStyleSheet("color:#f3d3d6;")
        msg.setWordWrap(True)
        btn = QPushButton("SAFETY RESET")
        btn.setObjectName("danger")
        btn.setMinimumHeight(46)
        btn.clicked.connect(self.ctrl.cmd_safety_reset)
        v.addWidget(title)
        v.addWidget(msg)
        v.addWidget(btn)
        self._overlay_box = box
        ov.hide()
        return ov

    def _layout_overlay(self) -> None:
        parent = self.centralWidget()
        if parent is None:
            return
        self._overlay.setGeometry(parent.rect())
        b = self._overlay_box
        b.adjustSize()
        b.move((self._overlay.width() - b.width()) // 2,
               (self._overlay.height() - b.height()) // 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_overlay()

    # ---------------------------------------------------------------- 주기 갱신
    def _tick(self) -> None:
        self.ctrl.scan()
        self._update_topbar()
        self._update_strip()
        page = self._stack.currentWidget()
        if hasattr(page, "update_view"):
            page.update_view()
        self._maybe_log()
        self._update_overlay()

    def _update_topbar(self) -> None:
        c = self.ctrl
        self._mode_badge.setText("AUTO" if c.mode_auto else "MANUAL")
        self._mode_badge.setStyleSheet(theme.badge_qss("auto" if c.mode_auto else "manual"))
        text, variant = self._state_badge_of(c.state)
        self._state_badge.setText(text)
        self._state_badge.setStyleSheet(theme.badge_qss(variant))
        self._clock.setText(datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    @staticmethod
    def _state_badge_of(state: State):
        if state is State.SAFETY_STOP:
            return "SAFETY STOP", "stop"
        if state is State.ERROR:
            return "ERROR", "stop"
        if state in _AUTO_RUNNING:
            return "AUTO RUNNING", "running"
        if state is State.AUTO_COMPLETE:
            return "AUTO COMPLETE", "running"
        if state is State.MANUAL_IDLE:
            return "MANUAL IDLE", "idle"
        return "IDLE", "idle"

    def _update_strip(self) -> None:
        c = self.ctrl
        self._set_pill("sol", theme.GREEN if c.sol_enable_ok else theme.RED,
                       "SOL ENABLED" if c.sol_enable_ok else "SOL DISABLED")
        cyl = c.io.di
        from ..hardware.signals import DI1
        if cyl(DI1.CYL_UP_POS) and not cyl(DI1.CYL_DOWN_POS):
            self._set_pill("cyl", theme.BLUE, "CYL UP")
        elif cyl(DI1.CYL_DOWN_POS) and not cyl(DI1.CYL_UP_POS):
            self._set_pill("cyl", theme.BLUE, "CYL DOWN")
        else:
            self._set_pill("cyl", theme.OFF, "CYL UNKNOWN")
        vs = c.vacuum_status()
        vac_color = {"OK": theme.GREEN, "BUILDING": theme.YELLOW,
                     "RESIDUAL": theme.YELLOW, "OFF": theme.OFF}[vs]
        self._set_pill("vacuum", vac_color, f"VACUUM {vs}")
        valid = c.loadcell.current_valid()
        self._set_pill("loadcell", theme.GREEN if valid else theme.RED,
                       "LOADCELL OK" if valid else "LOADCELL ERROR")
        self._set_pill("adam", theme.GREEN if c.adam2_connected else theme.RED,
                       "ADAM CONNECTED" if c.adam2_connected else "ADAM DISCONNECTED")

    def _set_pill(self, key: str, color: str, text: str) -> None:
        dot, label = self._pills[key]
        dot.setStyleSheet(theme.dot_qss(color))
        label.setText(text)

    def _update_overlay(self) -> None:
        show = self.ctrl.state is State.SAFETY_STOP
        if show and not self._overlay.isVisible():
            self._overlay.show()
            self._overlay.raise_()
            self._layout_overlay()
        elif not show and self._overlay.isVisible():
            self._overlay.hide()

    def _maybe_log(self) -> None:
        if self.ctrl.count > self._prev_count:
            self.logger.log_cycle(self.ctrl.count, self.ctrl.run_peak_load_kgf, self.ctrl.alarms)
        self._prev_count = self.ctrl.count

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
