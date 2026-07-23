"""유지보수 / 입출력 시험 페이지 (관리자, 목업 v0.4 / handoff §15).

좌: 진공/파기 hold-to-run 시험 + DO 시험.  우: 하중/통신 점검(교정·재연결·저장).
화면 이탈 시 모든 시험 출력을 OFF 한다(main_window 에서 on_leave 호출).
"""

import datetime
import os
import shutil

from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...core.states import State
from ...hardware.signals import DO1
from .. import theme
from ..keypad import edit_number

_IDLE = {State.AUTO_IDLE, State.MANUAL_IDLE, State.AUTO_COMPLETE}

_HOLD_BLUE = ("background:#e7effd; border:1px solid #4b86e8; color:#1c50ac;"
              "border-radius:9px; font-weight:800; padding:12px;")
_HOLD_YEL = ("background:#fdf1d8; border:1px solid #e0a83c; color:#8a5a12;"
             "border-radius:9px; font-weight:800; padding:12px;")


def _stat(title: str) -> tuple[QFrame, QLabel]:
    f = QFrame(); f.setObjectName("stat")
    v = QVBoxLayout(f); v.setContentsMargins(11, 8, 11, 8); v.setSpacing(2)
    t = QLabel(title); t.setObjectName("statLabel")
    val = QLabel("-"); val.setObjectName("statValue")
    v.addWidget(t); v.addWidget(val)
    return f, val


class MaintenancePage(QWidget):
    def __init__(self, controller, loadcell, hub, run_log_path: str) -> None:
        super().__init__()
        self.ctrl = controller
        self.loadcell = loadcell
        self.hub = hub
        self.run_log_path = run_log_path

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10); root.setSpacing(8)
        title = QLabel("유지보수 및 입출력 시험"); title.setObjectName("pageTitle")
        root.addWidget(title)

        body = QHBoxLayout(); body.setSpacing(12)
        body.addWidget(self._vacuum_card(), 1)
        body.addWidget(self._service_card(), 1)
        root.addLayout(body, 1)

    # ---------------------------------------------------------------- 진공/파기
    def _vacuum_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QLabel("진공 및 파기 시험"); head.setObjectName("cardTitle")
        lay.addWidget(head)

        warn = QLabel("시험 출력은 버튼을 누르는 동안만 동작합니다. 화면을 벗어나면 즉시 꺼집니다.")
        warn.setWordWrap(True)
        warn.setStyleSheet("background:#fdf1d8; border:1px solid #ecd39a; border-radius:8px;"
                           "color:#8a5a12; padding:9px 12px; font-weight:700;")
        lay.addWidget(warn)

        row = QHBoxLayout(); row.setSpacing(10)
        fc, self._vac_cmd = _stat("진공 명령")
        fo, self._vac_ok = _stat("진공 확인")
        row.addWidget(fc); row.addWidget(fo)
        lay.addLayout(row)

        self._b_vac = QPushButton("누르는 동안 진공 켜기")
        self._b_vac.setStyleSheet(_HOLD_BLUE); self._b_vac.setMinimumHeight(56)
        self._b_vac.pressed.connect(lambda: self.ctrl.set_vacuum(True))
        self._b_vac.released.connect(lambda: self.ctrl.set_vacuum(False))
        lay.addWidget(self._b_vac)

        self._b_blow = QPushButton("누르는 동안 파기 동작")
        self._b_blow.setStyleSheet(_HOLD_YEL); self._b_blow.setMinimumHeight(56)
        self._b_blow.pressed.connect(lambda: self.ctrl.request_maintenance_blowoff(True))
        self._b_blow.released.connect(lambda: self.ctrl.request_maintenance_blowoff(False))
        lay.addWidget(self._b_blow)

        head2 = QLabel("DO 시험 (타워/부저)"); head2.setObjectName("cardTitle")
        lay.addWidget(head2)
        grid = QGridLayout()
        self._do_btns = {}
        names = {DO1.TOWER_GREEN: "녹색등", DO1.TOWER_YELLOW: "황색등",
                 DO1.TOWER_RED: "적색등", DO1.TOWER_BUZZER: "부저"}
        for i, sig in enumerate((DO1.TOWER_GREEN, DO1.TOWER_YELLOW, DO1.TOWER_RED, DO1.TOWER_BUZZER)):
            b = QPushButton(names[sig]); b.setCheckable(True); b.setMinimumHeight(40)
            b.toggled.connect(lambda on, s=sig: self.ctrl.set_do_override(s, on))
            self._do_btns[sig] = b
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        return card

    # ---------------------------------------------------------------- 하중/통신
    def _service_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QLabel("하중 및 통신 점검"); head.setObjectName("cardTitle")
        lay.addWidget(head)

        g = QGridLayout(); g.setSpacing(10)
        f1, self._raw = _stat("로드셀 원신호")
        f2, self._load = _stat("보정 하중")
        f3, self._zero = _stat("영점 보정값")
        f4, self._scale = _stat("배율 보정값")
        g.addWidget(f1, 0, 0); g.addWidget(f2, 0, 1)
        g.addWidget(f3, 1, 0); g.addWidget(f4, 1, 1)
        lay.addLayout(g)

        grid = QGridLayout(); grid.setSpacing(8)
        b_zero = QPushButton("하중 영점"); b_zero.clicked.connect(self._load_zero)
        b_span = QPushButton("배율 교정"); b_span.clicked.connect(self._span)
        b_reconn = QPushButton("통신 재연결"); b_reconn.clicked.connect(self._reconnect)
        b_export = QPushButton("로그 저장"); b_export.clicked.connect(self._export)
        for i, b in enumerate((b_zero, b_span, b_reconn, b_export)):
            b.setMinimumHeight(46)
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)

        self._perm = QLabel("출력 허가: -")
        self._perm.setStyleSheet("font-weight:700; color:#3a4a5c;")
        lay.addWidget(self._perm)

        self._msg = QLabel("")
        self._msg.setStyleSheet(f"color:{theme.GREEN}; font-weight:700;")
        self._msg.setWordWrap(True)
        lay.addWidget(self._msg)
        lay.addStretch(1)
        return card

    # ---------------------------------------------------------------- actions
    def _load_zero(self) -> None:
        self.ctrl.cmd_load_zero()
        self._msg.setText("하중 영점 요청됨(무부하 상태에서 실행).")

    def _span(self) -> None:
        if self.ctrl.state not in _IDLE:
            self._msg.setText("대기 상태에서만 교정할 수 있습니다.")
            return
        known = edit_number(self, "기준 하중(kgf)", 100.0, is_float=True)
        if known is None:
            return
        ok = self.loadcell.calibrate_span(float(known))
        self._msg.setText(f"배율 교정 {'완료' if ok else '실패(측정값 확인)'} — 배율={self.loadcell.scale:.4f}")

    def _reconnect(self) -> None:
        try:
            self.hub.connect()
            self._msg.setText("통신 재연결 시도 완료.")
        except Exception as e:  # noqa: BLE001
            self._msg.setText(f"재연결 실패: {e}")

    def _export(self) -> None:
        if not os.path.exists(self.run_log_path):
            self._msg.setText("내보낼 운전 기록이 없습니다.")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(os.path.dirname(self.run_log_path) or ".", f"run_log_export_{ts}.csv")
        try:
            shutil.copyfile(self.run_log_path, dst)
            self._msg.setText(f"저장됨: {dst}")
        except OSError as e:
            self._msg.setText(f"저장 실패: {e}")

    def on_leave(self) -> None:
        """페이지 이탈 시 모든 시험 출력 OFF."""
        self.ctrl.set_vacuum(False)
        self.ctrl.request_maintenance_blowoff(False)
        self.ctrl.clear_do_overrides()
        for b in self._do_btns.values():
            b.blockSignals(True); b.setChecked(False); b.blockSignals(False)

    def update_view(self) -> None:
        c = self.ctrl
        self._vac_cmd.setText("켜짐" if c.vacuum_command else "꺼짐")
        self._vac_ok.setText("정상" if c.vacuum_ok else "꺼짐")
        self._raw.setText(f"{self.loadcell.read_ma():.2f} mA")
        self._load.setText(f"{self.loadcell.read_kgf():.1f} kgf")
        self._zero.setText(f"{self.loadcell.zero_offset:.1f} kgf")
        self._scale.setText(f"{self.loadcell.scale:.3f}")
        allowed, _reason = c.vacuum_permission()
        self._perm.setText(f"출력 허가: {'허용' if allowed else '차단'}")
