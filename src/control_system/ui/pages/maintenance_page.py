"""유지보수 / I/O 시험 페이지 (관리자, handoff §15).

- 진공 / Blow-off hold-to-run 시험 (버튼 누르는 동안만 출력).
- Load Zero / Span 교정.
- DO 시험 (타워/부저 등 안전 채널만 강제 출력).
- Modbus 재연결, 로그 CSV 내보내기.
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


class MaintenancePage(QWidget):
    def __init__(self, controller, loadcell, hub, run_log_path: str) -> None:
        super().__init__()
        self.ctrl = controller
        self.loadcell = loadcell
        self.hub = hub
        self.run_log_path = run_log_path

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        title = QLabel("유지보수 / I/O 시험")
        title.setStyleSheet("font-size:20px; font-weight:900;")
        root.addWidget(title)
        warn = QLabel("시험 출력은 버튼을 누르는 동안만 동작합니다. 화면 이탈/통신 이상 시 즉시 OFF.")
        warn.setStyleSheet(f"color:{theme.YELLOW};")
        root.addWidget(warn)

        body = QHBoxLayout()
        body.addWidget(self._vacuum_card(), 1)
        body.addWidget(self._service_card(), 1)
        root.addLayout(body)
        root.addStretch(1)

    # ---------------------------------------------------------------- 진공/blow-off
    def _vacuum_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card)
        head = QLabel("진공 / Blow-off 시험"); head.setObjectName("cardTitle")
        lay.addWidget(head)

        self._vac_state = QLabel("-")
        self._vac_state.setStyleSheet("font-family:Consolas,monospace;")
        lay.addWidget(self._vac_state)

        self._b_vac = QPushButton("누르고 있는 동안 VACUUM ON")
        self._b_vac.setMinimumHeight(64)
        self._b_vac.pressed.connect(lambda: self.ctrl.set_vacuum(True))
        self._b_vac.released.connect(lambda: self.ctrl.set_vacuum(False))
        lay.addWidget(self._b_vac)

        self._b_blow = QPushButton("누르고 있는 동안 BLOW-OFF")
        self._b_blow.setMinimumHeight(64)
        self._b_blow.pressed.connect(lambda: self.ctrl.request_maintenance_blowoff(True))
        self._b_blow.released.connect(lambda: self.ctrl.request_maintenance_blowoff(False))
        lay.addWidget(self._b_blow)

        head2 = QLabel("DO 시험 (타워/부저)"); head2.setObjectName("cardTitle")
        lay.addWidget(head2)
        grid = QGridLayout()
        self._do_btns = {}
        for i, sig in enumerate((DO1.TOWER_GREEN, DO1.TOWER_YELLOW, DO1.TOWER_RED, DO1.TOWER_BUZZER)):
            b = QPushButton(sig.name)
            b.setCheckable(True)
            b.toggled.connect(lambda on, s=sig: self.ctrl.set_do_override(s, on))
            self._do_btns[sig] = b
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        return card

    # ---------------------------------------------------------------- 하중/통신
    def _service_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card)
        head = QLabel("하중 및 통신 서비스"); head.setObjectName("cardTitle")
        lay.addWidget(head)

        self._load_info = QLabel("-")
        self._load_info.setStyleSheet("font-family:Consolas,monospace;")
        lay.addWidget(self._load_info)

        grid = QGridLayout()
        b_zero = QPushButton("LOAD ZERO"); b_zero.clicked.connect(self._load_zero)
        b_span = QPushButton("SPAN 교정"); b_span.clicked.connect(self._span)
        b_reconn = QPushButton("MODBUS 재연결"); b_reconn.clicked.connect(self._reconnect)
        b_export = QPushButton("로그 내보내기"); b_export.clicked.connect(self._export)
        for i, b in enumerate((b_zero, b_span, b_reconn, b_export)):
            b.setMinimumHeight(44)
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)

        self._msg = QLabel("")
        self._msg.setStyleSheet(f"color:{theme.GREEN};")
        self._msg.setWordWrap(True)
        lay.addWidget(self._msg)
        lay.addStretch(1)
        return card

    # ---------------------------------------------------------------- actions
    def _load_zero(self) -> None:
        self.ctrl.cmd_load_zero()
        self._msg.setText("Load Zero 요청됨(무부하 상태에서 실행).")

    def _span(self) -> None:
        if self.ctrl.state not in _IDLE:
            self._msg.setText("Idle 상태에서만 교정할 수 있습니다.")
            return
        known = edit_number(self, "기준 하중(kgf)", 100.0, is_float=True)
        if known is None:
            return
        ok = self.loadcell.calibrate_span(float(known))
        self._msg.setText(f"Span 교정 {'완료' if ok else '실패(측정값 확인)'} — scale={self.loadcell.scale:.4f}")

    def _reconnect(self) -> None:
        try:
            self.hub.connect()
            self._msg.setText("Modbus 재연결 시도 완료.")
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
            self._msg.setText(f"내보냄: {dst}")
        except OSError as e:
            self._msg.setText(f"내보내기 실패: {e}")

    def on_leave(self) -> None:
        """페이지 이탈 시 모든 시험 출력 OFF."""
        self.ctrl.set_vacuum(False)
        self.ctrl.request_maintenance_blowoff(False)
        self.ctrl.clear_do_overrides()
        for b in self._do_btns.values():
            b.blockSignals(True); b.setChecked(False); b.blockSignals(False)

    def update_view(self) -> None:
        c = self.ctrl
        self._vac_state.setText(
            f"VACUUM COMMAND : {'ON' if c.vacuum_command else 'OFF'}\n"
            f"VACUUM_OK      : {'ON' if c.vacuum_ok else 'OFF'}\n"
            f"BLOW-OFF       : {'ON' if c.out.blow_off_on else 'OFF'}"
        )
        self._load_info.setText(
            f"RAW      : {self.loadcell.read_ma():.2f} mA\n"
            f"LOAD     : {self.loadcell.read_kgf():.1f} kgf\n"
            f"ZERO OFS : {self.loadcell.zero_offset:.1f}\n"
            f"SCALE    : {self.loadcell.scale:.4f}"
        )
