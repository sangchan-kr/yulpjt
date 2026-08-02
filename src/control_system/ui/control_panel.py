"""제어함 시뮬레이터 (mock/개발 전용, 별도 top-level 창).

실물 제어함(250×350mm)의 외부 스위치를 클릭으로 재현한다:
  Auto Run/Start(녹색·탭) · Auto Stop(적색·탭) · AUTO/MANUAL(셀렉터) ·
  Manual Up(백색·홀드) · Manual Down(흑색·홀드) · MAIN POWER(로커)

실물 제어함엔 없지만 자동 사이클 테스트에 필요한 신호(구동 허가/진공 확인/
실린더 위치)는 하단 '센서·인터록 시뮬' 에서 넣는다. '실린더 자동 응답' 을 켜면
밸브 출력에 맞춰 실린더 위치 센서가 자동으로 반응한다.
"""

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ..hardware.signals import AI, DI1, DI2
from . import theme

_TRAVEL_S = 0.4   # 실린더 이동 모사 시간(초)

# 둥근 푸시버튼 스타일 (색/글자색)
def _btn_qss(bg: str, fg: str, border: str) -> str:
    return (f"QPushButton{{background:{bg}; color:{fg}; border:3px solid {border};"
            f"border-radius:38px; font-weight:800; font-size:14px;}}"
            f"QPushButton:pressed{{background:{border};}}")


class ControlPanel(QWidget):
    def __init__(self, controller, adam1, adam2, adam4017) -> None:
        super().__init__()
        self.ctrl = controller
        self.a1, self.a2, self.ai = adam1, adam2, adam4017
        self.setWindowTitle("제어함 (외부 스위치 시뮬)")
        self.setStyleSheet(theme.QSS + "QWidget{background:#e9edf2;}"
                           "QGroupBox{font-weight:800; border:1px solid #cfd8e2;"
                           "border-radius:10px; margin-top:10px; padding:8px;}"
                           "QGroupBox::title{subcontrol-origin:margin; left:12px; padding:0 4px;}")
        self.resize(560, 640)

        # 실린더 자동응답 상태
        self._prev_vd = self._prev_vu = False
        self._cyl_target = None
        self._cyl_t0 = 0.0

        root = QVBoxLayout(self)
        title = QLabel("반복 가압 측정기 — 제어함")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size:20px; font-weight:900; color:{theme.TITLE};")
        root.addWidget(title)

        root.addWidget(self._switch_panel())
        root.addWidget(self._sensor_panel())
        root.addWidget(self._output_panel())

        # 초기 주입값
        self.a1.set_mock_di(int(DI1.MODE_AUTO), False)   # 시작은 MANUAL

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(80)

    # ------------------------------------------------------------- 외부 스위치
    def _switch_panel(self) -> QGroupBox:
        box = QGroupBox("외부 스위치 (제어함 전면)")
        grid = QGridLayout(box)
        grid.setSpacing(14)

        # Auto Run/Start — 녹색 탭
        self._b_start = self._round("Auto\nStart", "#2fae5f", "#ffffff", "#1f8a49")
        self._b_start.clicked.connect(lambda: self._pulse(self.a1, int(DI1.AUTO_START_PB)))
        # Auto Stop — 적색 탭
        self._b_stop = self._round("Auto\nStop", "#d1352b", "#ffffff", "#a3251d")
        self._b_stop.clicked.connect(lambda: self._pulse(self.a1, int(DI1.AUTO_STOP_PB)))
        # Manual Up — 백색 홀드
        self._b_up = self._round("Manual\nUp", "#f4f6f9", "#2c3a4b", "#b8c2ce")
        self._b_up.pressed.connect(lambda: self.a1.set_mock_di(int(DI1.MANUAL_UP_PB), True))
        self._b_up.released.connect(lambda: self.a1.set_mock_di(int(DI1.MANUAL_UP_PB), False))
        # Manual Down — 흑색 홀드
        self._b_down = self._round("Manual\nDown", "#2b3138", "#ffffff", "#11151a")
        self._b_down.pressed.connect(lambda: self.a1.set_mock_di(int(DI1.MANUAL_DOWN_PB), True))
        self._b_down.released.connect(lambda: self.a1.set_mock_di(int(DI1.MANUAL_DOWN_PB), False))

        # AUTO / MANUAL 셀렉터 (토글)
        self._sel = QPushButton("MANUAL"); self._sel.setCheckable(True)
        self._sel.setMinimumSize(120, 46)
        self._sel.toggled.connect(self._on_selector)
        self._sel.setStyleSheet("QPushButton{background:#eef2f7;border:1px solid #cfd8e2;"
                                "border-radius:9px;font-weight:800;}"
                                "QPushButton:checked{background:#0c4a6e;color:#fff;border-color:#0b3b57;}")
        sel_wrap = QVBoxLayout()
        sl = QLabel("AUTO / MANUAL"); sl.setAlignment(Qt.AlignmentFlag.AlignCenter); sl.setObjectName("mini")
        sel_wrap.addWidget(sl); sel_wrap.addWidget(self._sel)

        # MAIN POWER (로커, 시각용)
        self._pwr = QPushButton("ON"); self._pwr.setCheckable(True); self._pwr.setChecked(True)
        self._pwr.setMinimumSize(120, 46)
        self._pwr.toggled.connect(lambda on: self._pwr.setText("ON" if on else "OFF"))
        self._pwr.setStyleSheet("QPushButton{background:#2b3138;color:#8a96a3;border:2px solid #11151a;"
                                "border-radius:8px;font-weight:900;}"
                                "QPushButton:checked{background:#d1352b;color:#fff;}")
        pwr_wrap = QVBoxLayout()
        pl = QLabel("MAIN POWER"); pl.setAlignment(Qt.AlignmentFlag.AlignCenter); pl.setObjectName("mini")
        pwr_wrap.addWidget(pl); pwr_wrap.addWidget(self._pwr)

        # 배치: 실물 제어함처럼 (좌: Start/Stop, 중: 셀렉터/파워, 우: Up/Down)
        grid.addWidget(self._labeled(self._b_start, "Auto Run/Start"), 0, 0)
        grid.addLayout(sel_wrap, 0, 1)
        grid.addWidget(self._labeled(self._b_up, "Manual Up"), 0, 2)
        grid.addWidget(self._labeled(self._b_stop, "Auto Stop"), 1, 0)
        grid.addLayout(pwr_wrap, 1, 1)
        grid.addWidget(self._labeled(self._b_down, "Manual Down"), 1, 2)
        return box

    def _round(self, text, bg, fg, border) -> QPushButton:
        b = QPushButton(text); b.setFixedSize(76, 76)
        b.setStyleSheet(_btn_qss(bg, fg, border))
        return b

    def _labeled(self, widget, label) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(4)
        lb = QLabel(label); lb.setAlignment(Qt.AlignmentFlag.AlignCenter); lb.setObjectName("mini")
        v.addWidget(lb); v.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
        return w

    # ------------------------------------------------------------- 센서/인터록
    def _sensor_panel(self) -> QGroupBox:
        box = QGroupBox("센서 · 인터록 시뮬 (제어함 외부 신호)")
        g = QGridLayout(box)
        self._cb_sol = QCheckBox("구동 허가 (SOL_ENABLE_OK)")
        self._cb_sol.toggled.connect(lambda on: self.a1.set_mock_di(int(DI1.SOL_ENABLE_OK), on))
        self._cb_vac = QCheckBox("진공 확인 (VACUUM_OK)")
        self._cb_vac.toggled.connect(lambda on: self.a2.set_mock_di(int(DI2.VACUUM_OK), on))
        self._cb_autocyl = QCheckBox("실린더 자동 응답 (밸브에 맞춰 위치센서 자동)")
        self._cb_autocyl.setChecked(True)
        self._cb_autocyl.toggled.connect(self._on_autocyl)
        self._cb_cyl_up = QCheckBox("실린더 상승 위치 (CYL_UP_POS)")
        self._cb_cyl_up.toggled.connect(lambda on: self.a1.set_mock_di(int(DI1.CYL_UP_POS), on))
        self._cb_cyl_dn = QCheckBox("실린더 하강 위치 (CYL_DOWN_POS)")
        self._cb_cyl_dn.toggled.connect(lambda on: self.a1.set_mock_di(int(DI1.CYL_DOWN_POS), on))
        g.addWidget(self._cb_sol, 0, 0)
        g.addWidget(self._cb_vac, 0, 1)
        g.addWidget(self._cb_autocyl, 1, 0, 1, 2)
        g.addWidget(self._cb_cyl_up, 2, 0)
        g.addWidget(self._cb_cyl_dn, 2, 1)

        lc = QHBoxLayout()
        self._load_lbl = QLabel("하중 0 kgf")
        self._fs = self.ctrl.loadcell.full_scale_kgf
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, int(self._fs))
        self._slider.valueChanged.connect(
            lambda v: self.ai.set_mock_load_kgf(int(AI.LOADCELL_CURRENT), float(v), self._fs))
        lc.addWidget(QLabel("로드셀"))
        lc.addWidget(self._slider, 1)
        lc.addWidget(self._load_lbl)
        g.addLayout(lc, 3, 0, 1, 2)
        self._on_autocyl(True)
        return box

    def _on_autocyl(self, on: bool) -> None:
        # 자동 응답 시 수동 실린더 체크박스는 비활성(자동으로 갱신).
        self._cb_cyl_up.setEnabled(not on)
        self._cb_cyl_dn.setEnabled(not on)

    # ------------------------------------------------------------- 출력 표시
    def _output_panel(self) -> QGroupBox:
        box = QGroupBox("출력 · 상태")
        g = QGridLayout(box)
        self._state_lbl = QLabel("-")
        self._state_lbl.setStyleSheet("font-weight:900;")
        g.addWidget(self._state_lbl, 0, 0, 1, 4)
        self._lamps = {}
        specs = [("하강밸브", "vd"), ("상승밸브", "vu"), ("진공", "vac"), ("부저", "bz"),
                 ("시작램프", "ls"), ("정지램프", "lp"), ("상승램프", "lu"), ("하강램프", "ld")]
        for i, (label, key) in enumerate(specs):
            lamp = QLabel(label)
            lamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lamp.setStyleSheet(self._lamp(False))
            self._lamps[key] = lamp
            g.addWidget(lamp, 1 + i // 4, i % 4)
        return box

    @staticmethod
    def _lamp(on: bool, color: str = theme.GREEN) -> str:
        bg = color if on else "#dbe2ea"
        fg = "#ffffff" if on else "#7a8896"
        return f"background:{bg}; color:{fg}; padding:6px 4px; border-radius:6px; font-weight:800;"

    # ------------------------------------------------------------- 동작
    def _pulse(self, module, ch: int) -> None:
        module.set_mock_di(ch, True)
        QTimer.singleShot(250, lambda: module.set_mock_di(ch, False))

    def _on_selector(self, auto: bool) -> None:
        self._sel.setText("AUTO" if auto else "MANUAL")
        self.a1.set_mock_di(int(DI1.MODE_AUTO), auto)

    def _tick(self) -> None:
        # 실린더 자동 응답: 밸브 출력에 맞춰 위치 센서 반응
        if self._cb_autocyl.isChecked():
            o = self.ctrl.out
            now = time.monotonic()
            if o.valve_down and not self._prev_vd:
                self._cyl_target, self._cyl_t0 = "down", now
                self.a1.set_mock_di(int(DI1.CYL_UP_POS), False)
                self.a1.set_mock_di(int(DI1.CYL_DOWN_POS), False)
            if o.valve_up and not self._prev_vu:
                self._cyl_target, self._cyl_t0 = "up", now
                self.a1.set_mock_di(int(DI1.CYL_DOWN_POS), False)
                self.a1.set_mock_di(int(DI1.CYL_UP_POS), False)
            if self._cyl_target and now - self._cyl_t0 >= _TRAVEL_S:
                if self._cyl_target == "down":
                    self.a1.set_mock_di(int(DI1.CYL_DOWN_POS), True)
                else:
                    self.a1.set_mock_di(int(DI1.CYL_UP_POS), True)
                self._cyl_target = None
            self._prev_vd, self._prev_vu = o.valve_down, o.valve_up
            # 수동 체크박스 표시 동기화
            self._sync_cb(self._cb_cyl_up, self.a1.read_di()[int(DI1.CYL_UP_POS)])
            self._sync_cb(self._cb_cyl_dn, self.a1.read_di()[int(DI1.CYL_DOWN_POS)])

        self._load_lbl.setText(f"하중 {self.ctrl.loadcell.read_kgf():.0f} kgf")
        o = self.ctrl.out
        self._state_lbl.setText(f"상태: {self.ctrl.state.value}    카운트: {self.ctrl.count}/{self.ctrl.target_count}")
        self._lamps["vd"].setStyleSheet(self._lamp(o.valve_down, theme.BLUE))
        self._lamps["vu"].setStyleSheet(self._lamp(o.valve_up, theme.BLUE))
        self._lamps["vac"].setStyleSheet(self._lamp(o.vacuum_on, theme.GREEN))
        self._lamps["bz"].setStyleSheet(self._lamp(o.buzzer, "#8a5a12"))
        self._lamps["ls"].setStyleSheet(self._lamp(o.lamp_auto_start, theme.GREEN))
        self._lamps["lp"].setStyleSheet(self._lamp(o.lamp_auto_stop, theme.YELLOW))
        self._lamps["lu"].setStyleSheet(self._lamp(o.lamp_manual_up, theme.BLUE))
        self._lamps["ld"].setStyleSheet(self._lamp(o.lamp_manual_down, theme.BLUE))

    @staticmethod
    def _sync_cb(cb: QCheckBox, val: bool) -> None:
        if cb.isChecked() != val:
            cb.blockSignals(True); cb.setChecked(val); cb.blockSignals(False)
