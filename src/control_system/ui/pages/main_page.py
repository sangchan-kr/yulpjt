"""메인 운전 페이지 (목업 v0.4 §5).

좌: 현재 동작(상태/step/실린더/dwell)  ·  우: 현재 하중 + 진공 + 조작.
컨트롤러 상태를 update_view() 로 읽어 그리고, 버튼은 컨트롤러 명령으로 연결한다.
진공 경고는 논블로킹이라 진공 영역에만 표시(다른 표시에 영향 없음).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from ...core.states import State
from .. import theme
from ..trend import TrendWidget

_STAGE_KO = {
    State.BOOT: "초기화", State.AUTO_IDLE: "자동 대기", State.AUTO_PRECHECK: "사전 점검",
    State.AUTO_MOVE_DOWN: "하강 중", State.AUTO_DWELL_DOWN: "가압 유지 중",
    State.AUTO_MOVE_UP: "상승 중", State.AUTO_DWELL_UP: "상승 유지",
    State.AUTO_COUNT_UPDATE: "카운트", State.AUTO_EXCHANGE_UP: "교체 위치 이동 중",
    State.AUTO_COMPLETE: "운전 완료",
    State.MANUAL_IDLE: "수동 대기", State.MANUAL_MOVE_UP: "교체 위치 이동 중",
    State.SAFETY_STOP: "안전 정지", State.ERROR: "오류",
}


def _card(title: str):
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(10)
    head = QLabel(title)
    head.setObjectName("cardTitle")
    lay.addWidget(head)
    return frame, lay, head


def _stat(title: str) -> tuple[QFrame, QLabel]:
    """라이트 회색 스탯 박스: 상단 라벨(muted) + 하단 값(bold)."""
    f = QFrame()
    f.setObjectName("stat")
    v = QVBoxLayout(f)
    v.setContentsMargins(11, 8, 11, 8)
    v.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("statLabel")
    val = QLabel("-")
    val.setObjectName("statValue")
    v.addWidget(t)
    v.addWidget(val)
    return f, val


class MainPage(QWidget):
    def __init__(self, controller, trend) -> None:
        super().__init__()
        self.ctrl = controller
        self._trend = trend
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)
        root.addWidget(self._process_card(), 1)
        root.addWidget(self._monitor_card(), 1)

    # ---------------------------------------------------------------- 좌: 현재 동작
    def _process_card(self) -> QFrame:
        frame, lay, head = _card("현재 동작")
        # 우상단: 반복 횟수(크게)
        cap = QLabel("반복 횟수")
        cap.setObjectName("mini")
        cap.setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._count_big = QLabel("0 / 0")
        self._count_big.setStyleSheet(f"font-size:46px; font-weight:900; color:{theme.TITLE};")
        head_row = QHBoxLayout()
        head_row.addWidget(head)
        head_row.addStretch(1)
        head_row.addWidget(cap)
        head_row.addSpacing(8)
        head_row.addWidget(self._count_big)
        lay.takeAt(0)
        lay.insertLayout(0, head_row)

        self._stage = QLabel("-")
        self._stage.setStyleSheet(f"font-size:34px; font-weight:900; color:{theme.TITLE};")
        lay.addWidget(self._stage)
        # dwell 남은시간(초) — 크게 표시
        self._sub = QLabel("")
        self._sub.setStyleSheet(f"font-size:19px; font-weight:800; color:{theme.MUTED};")
        lay.addWidget(self._sub)

        self._arrow = QLabel("■")
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setStyleSheet(f"font-size:64px; font-weight:900; color:{theme.GREEN};")
        lay.addWidget(self._arrow, 1)

        row = QHBoxLayout()
        row.setSpacing(10)
        f1, self._down_dwell = _stat("하강 유지시간")
        f2, self._up_dwell = _stat("상승 유지시간")
        row.addWidget(f1)
        row.addWidget(f2)
        lay.addLayout(row)

        # 교체 위치: 실린더를 상승 센서까지 올려 시료 교체를 쉽게 (수동 대기에서만)
        self._btn_exchange = QPushButton("교체 위치")
        self._btn_exchange.setObjectName("primary")
        self._btn_exchange.setMinimumHeight(46)
        self._btn_exchange.clicked.connect(self.ctrl.cmd_exchange_position)
        lay.addWidget(self._btn_exchange)

        # 조작 버튼(오른쪽 하중 카드에서 이동 — 하중 표시 세로 공간 확보)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_reset = QPushButton("안전 복귀")
        self._btn_reset.setObjectName("danger")
        self._btn_reset.clicked.connect(self.ctrl.cmd_safety_reset)
        b_clear = QPushButton("알람 해제")
        b_clear.clicked.connect(self.ctrl.cmd_alarm_clear)
        b_count = QPushButton("횟수 초기화")
        b_count.clicked.connect(self.ctrl.cmd_count_reset)
        b_zero = QPushButton("하중 영점")
        b_zero.clicked.connect(self.ctrl.cmd_load_zero)
        for b in (self._btn_reset, b_clear, b_count, b_zero):
            b.setMinimumHeight(46)
            actions.addWidget(b)
        lay.addLayout(actions)
        return frame

    # ---------------------------------------------------------------- 우: 현재 하중
    def _monitor_card(self) -> QFrame:
        frame, lay, head = _card("현재 하중")
        self._src = QLabel("로드셀")
        self._src.setObjectName("mini")
        head_row = QHBoxLayout()
        head_row.addWidget(head)
        head_row.addStretch(1)
        head_row.addWidget(self._src)
        lay.takeAt(0)
        lay.insertLayout(0, head_row)

        self._load = QLabel("--- kgf")
        self._load.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load.setStyleSheet(f"font-size:52px; font-weight:900; color:{theme.TITLE};")
        lay.addWidget(self._load)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        f1, self._cyc_peak = _stat("현재 최대")
        f2, self._run_peak = _stat("운전 최대")
        f3, self._limit = _stat("하중 상한")
        stats.addWidget(f1)
        stats.addWidget(f2)
        stats.addWidget(f3)
        lay.addLayout(stats)

        self._trend_w = TrendWidget(self._trend, limit_getter=lambda: self.ctrl.settings.load_limit_kgf)
        lay.addWidget(self._trend_w)

        cnt_row = QHBoxLayout()
        prog_cap = QLabel("진행률")
        prog_cap.setObjectName("mini")
        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setStyleSheet(f"font-weight:800; color:{theme.MUTED};")
        cnt_row.addWidget(prog_cap)
        cnt_row.addStretch(1)
        cnt_row.addWidget(self._pct_lbl)
        lay.addLayout(cnt_row)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        lay.addWidget(self._progress)

        # 진공 영역 (완전 분리 — 명령/확인 별도 표시 + 큰 토글 + 경고)
        vac = QHBoxLayout()
        vac.setSpacing(10)
        fc, self._vac_cmd = _stat("진공 명령")
        fo, self._vac_ok = _stat("진공 확인")
        vac.addWidget(fc)
        vac.addWidget(fo)
        self._vac_btn = QPushButton("진공 켜기")
        self._vac_btn.setObjectName("primary")
        self._vac_btn.setCheckable(True)
        self._vac_btn.setMinimumHeight(52)
        self._vac_btn.toggled.connect(self.ctrl.set_vacuum)
        vac.addWidget(self._vac_btn, 1)
        lay.addLayout(vac)
        self._vac_warn = QLabel("")
        self._vac_warn.setStyleSheet(f"color:{theme.YELLOW}; font-weight:700;")
        lay.addWidget(self._vac_warn)
        return frame

    # ---------------------------------------------------------------- 갱신
    def update_view(self) -> None:
        c = self.ctrl
        step = c.auto_step()
        self._stage.setText(_STAGE_KO.get(c.state, c.state.value))
        rem = c.remaining_dwell_s()
        parts = []
        if step:
            parts.append(f"{step}/4 단계")
        if rem:
            parts.append(f"남은 시간 {rem:.1f}초")
        self._sub.setText("     ·     ".join(parts))

        if c.out.valve_down:
            self._arrow.setText("↓"); self._arrow.setStyleSheet(f"font-size:64px;font-weight:900;color:{theme.GREEN};")
        elif c.out.valve_up:
            self._arrow.setText("↑"); self._arrow.setStyleSheet(f"font-size:64px;font-weight:900;color:{theme.BLUE};")
        else:
            self._arrow.setText("■"); self._arrow.setStyleSheet(f"font-size:64px;font-weight:900;color:{theme.OFF};")

        self._down_dwell.setText(f"{c.settings.down_dwell_ms/1000:.2f}초")
        self._up_dwell.setText(f"{c.settings.up_dwell_ms/1000:.2f}초")

        self._load.setText(f"{c.load_kgf:.1f} kgf")
        self._cyc_peak.setText(f"{c.cycle_peak_load_kgf:.1f}")
        self._run_peak.setText(f"{c.run_peak_load_kgf:.1f}")
        self._limit.setText(f"{c.settings.load_limit_kgf:.1f}")

        pct = int(c.count / c.target_count * 100) if c.target_count else 0
        self._count_big.setText(f"{c.count} / {c.target_count}")
        self._pct_lbl.setText(f"{min(100, pct)}%")
        self._progress.setValue(min(100, pct))

        self._vac_cmd.setText("켜짐" if c.vacuum_command else "꺼짐")
        ok_color = theme.GREEN if c.vacuum_ok else theme.MUTED
        self._vac_ok.setText("정상" if c.vacuum_ok else "꺼짐")
        self._vac_ok.setStyleSheet(f"font-size:19px;font-weight:800;color:{ok_color};")
        if self._vac_btn.isChecked() != c.vacuum_command:
            self._vac_btn.blockSignals(True)
            self._vac_btn.setChecked(c.vacuum_command)
            self._vac_btn.blockSignals(False)
        self._vac_btn.setText("진공 끄기" if c.vacuum_command else "진공 켜기")
        warns = ", ".join(sorted(a.value for a in c.vacuum_warnings))
        self._vac_warn.setText(f"⚠ {warns}" if warns else "")

        self._btn_reset.setEnabled(c.state is State.SAFETY_STOP and c.sol_enable_ok)
        # 교체 위치: 수동 대기 + 구동 허가일 때만 시작 가능. 이동 중엔 표시만.
        if c.state is State.MANUAL_MOVE_UP:
            self._btn_exchange.setEnabled(False)
            self._btn_exchange.setText("교체 위치 이동 중…")
        else:
            self._btn_exchange.setEnabled(c.state is State.MANUAL_IDLE and c.sol_enable_ok)
            self._btn_exchange.setText("교체 위치")
        self._trend_w.update()
