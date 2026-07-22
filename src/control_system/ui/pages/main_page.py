"""메인 운전 페이지 (목업 v0.3 §5).

좌: 현재 공정(상태/step/실린더/dwell)  ·  우: 하중 모니터 + 진공 + 조작.
컨트롤러 상태를 update() 로 읽어 그리고, 버튼은 컨트롤러 명령으로 연결한다.
진공 경고는 논블로킹이라 진공 영역에만 표시(다른 표시에 영향 없음).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from ...core.states import State
from .. import theme

_STAGE_KO = {
    State.BOOT: "초기화", State.AUTO_IDLE: "자동 대기", State.AUTO_PRECHECK: "사전 점검",
    State.AUTO_MOVE_DOWN: "하강 중", State.AUTO_DWELL_DOWN: "가압 유지 중",
    State.AUTO_MOVE_UP: "상승 중", State.AUTO_DWELL_UP: "상승 유지",
    State.AUTO_COUNT_UPDATE: "카운트", State.AUTO_COMPLETE: "운전 완료",
    State.MANUAL_IDLE: "수동 대기", State.SAFETY_STOP: "안전 정지", State.ERROR: "오류",
}


def _card(title: str):
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 10)
    head = QLabel(title)
    head.setObjectName("cardTitle")
    lay.addWidget(head)
    return frame, lay, head


def _mini(title: str) -> tuple[QFrame, QLabel]:
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(9, 7, 9, 7)
    t = QLabel(title)
    t.setObjectName("mini")
    val = QLabel("-")
    val.setStyleSheet("font-size:17px; font-weight:800;")
    v.addWidget(t)
    v.addWidget(val)
    return f, val


class MainPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.ctrl = controller
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)
        root.addWidget(self._process_card(), 1)
        root.addWidget(self._monitor_card(), 1)

    # ---------------------------------------------------------------- 좌: 공정
    def _process_card(self) -> QFrame:
        frame, lay, head = _card("현재 공정")
        self._step = QLabel("-")
        self._step.setObjectName("mini")
        head_row = QHBoxLayout()
        head_row.addWidget(head)
        head_row.addStretch(1)
        head_row.addWidget(self._step)
        lay.takeAt(0)
        lay.insertLayout(0, head_row)

        self._stage = QLabel("-")
        self._stage.setStyleSheet("font-size:30px; font-weight:900;")
        lay.addWidget(self._stage)
        self._sub = QLabel("-")
        self._sub.setObjectName("mini")
        lay.addWidget(self._sub)

        self._arrow = QLabel("■")
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setStyleSheet(f"font-size:56px; font-weight:900; color:{theme.GREEN};")
        lay.addWidget(self._arrow, 1)

        row = QHBoxLayout()
        f1, self._down_dwell = _mini("DOWN DWELL")
        f2, self._up_dwell = _mini("UP DWELL")
        row.addWidget(f1)
        row.addWidget(f2)
        lay.addLayout(row)
        return frame

    # ---------------------------------------------------------------- 우: 모니터
    def _monitor_card(self) -> QFrame:
        frame, lay, head = _card("하중 모니터")
        self._load = QLabel("--- kgf")
        self._load.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load.setStyleSheet("font-size:46px; font-weight:900;")
        lay.addWidget(self._load)

        stats = QHBoxLayout()
        f1, self._cyc_peak = _mini("사이클 최대")
        f2, self._run_peak = _mini("운전 최대")
        f3, self._limit = _mini("상한")
        stats.addWidget(f1)
        stats.addWidget(f2)
        stats.addWidget(f3)
        lay.addLayout(stats)

        self._count_lbl = QLabel("반복 횟수 0 / 0")
        self._count_lbl.setStyleSheet("font-weight:800;")
        lay.addWidget(self._count_lbl)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        lay.addWidget(self._progress)

        # 진공 영역 (완전 분리 — Command/OK 별도 표시 + 큰 토글 + 경고)
        vac = QHBoxLayout()
        fc, self._vac_cmd = _mini("VACUUM COMMAND")
        fo, self._vac_ok = _mini("VACUUM_OK")
        vac.addWidget(fc)
        vac.addWidget(fo)
        self._vac_btn = QPushButton("VACUUM ON")
        self._vac_btn.setCheckable(True)
        self._vac_btn.setMinimumHeight(46)
        self._vac_btn.toggled.connect(self.ctrl.set_vacuum)
        vac.addWidget(self._vac_btn, 1)
        lay.addLayout(vac)
        self._vac_warn = QLabel("")
        self._vac_warn.setStyleSheet(f"color:{theme.YELLOW}; font-weight:700;")
        lay.addWidget(self._vac_warn)

        actions = QHBoxLayout()
        self._btn_reset = QPushButton("Safety Reset")
        self._btn_reset.setObjectName("danger")
        self._btn_reset.clicked.connect(self.ctrl.cmd_safety_reset)
        b_clear = QPushButton("Alarm Clear")
        b_clear.clicked.connect(self.ctrl.cmd_alarm_clear)
        b_count = QPushButton("Count Reset")
        b_count.clicked.connect(self.ctrl.cmd_count_reset)
        b_zero = QPushButton("Load Zero")
        b_zero.clicked.connect(self.ctrl.cmd_load_zero)
        for b in (self._btn_reset, b_clear, b_count, b_zero):
            b.setMinimumHeight(42)
            actions.addWidget(b)
        lay.addLayout(actions)
        return frame

    # ---------------------------------------------------------------- 갱신
    def update_view(self) -> None:
        c = self.ctrl
        step = c.auto_step()
        self._step.setText(f"Step {step} / 4" if step else "-")
        self._stage.setText(_STAGE_KO.get(c.state, c.state.value))
        rem = c.remaining_dwell_s()
        sub = c.state.value + (f" · 남은 시간 {rem:.1f}초" if rem else "")
        self._sub.setText(sub)

        if c.out.valve_down:
            self._arrow.setText("↓"); self._arrow.setStyleSheet(f"font-size:56px;font-weight:900;color:{theme.GREEN};")
        elif c.out.valve_up:
            self._arrow.setText("↑"); self._arrow.setStyleSheet(f"font-size:56px;font-weight:900;color:{theme.BLUE};")
        else:
            self._arrow.setText("■"); self._arrow.setStyleSheet(f"font-size:56px;font-weight:900;color:{theme.OFF};")

        self._down_dwell.setText(f"{c.settings.down_dwell_ms/1000:.2f} s")
        self._up_dwell.setText(f"{c.settings.up_dwell_ms/1000:.2f} s")

        self._load.setText(f"{c.load_kgf:.1f} kgf")
        self._cyc_peak.setText(f"{c.cycle_peak_load_kgf:.1f}")
        self._run_peak.setText(f"{c.run_peak_load_kgf:.1f}")
        self._limit.setText(f"{c.settings.load_limit_kgf:.1f}")

        pct = int(c.count / c.target_count * 100) if c.target_count else 0
        self._count_lbl.setText(f"반복 횟수 {c.count} / {c.target_count}")
        self._progress.setValue(min(100, pct))

        status = c.vacuum_status()
        self._vac_cmd.setText("ON" if c.vacuum_command else "OFF")
        ok_color = theme.GREEN if c.vacuum_ok else theme.MUTED
        self._vac_ok.setText("ON" if c.vacuum_ok else "OFF")
        self._vac_ok.setStyleSheet(f"font-size:17px;font-weight:800;color:{ok_color};")
        if self._vac_btn.isChecked() != c.vacuum_command:
            self._vac_btn.blockSignals(True)
            self._vac_btn.setChecked(c.vacuum_command)
            self._vac_btn.blockSignals(False)
        self._vac_btn.setText("VACUUM OFF" if c.vacuum_command else "VACUUM ON")
        warns = ", ".join(sorted(a.value for a in c.vacuum_warnings))
        self._vac_warn.setText(f"⚠ {warns}" if warns else "")

        self._btn_reset.setEnabled(c.state is State.SAFETY_STOP and c.sol_enable_ok)
