"""시스템 상태 페이지 (목업 v0.3 / handoff §11).

좌: 컨트롤러/통신/프로세스 요약. 우: ADAM I/O (탭 전환) + 진공 출력 허가 상세
(Command / Permission / Actual / Reason).
"""

import shutil
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from ...hardware.signals import AI, DI1, DI2, DO1, DO2
from .. import theme


def _box(title: str) -> tuple[QFrame, QLabel]:
    f = QFrame(); f.setObjectName("card")
    v = QVBoxLayout(f); v.setContentsMargins(9, 6, 9, 6)
    t = QLabel(title); t.setObjectName("mini")
    val = QLabel("-"); val.setStyleSheet("font-size:15px; font-weight:800;")
    v.addWidget(t); v.addWidget(val)
    return f, val


class StatusPage(QWidget):
    def __init__(self, controller, adam1, adam2, adam4017, start_monotonic: float) -> None:
        super().__init__()
        self.ctrl = controller
        self.a1, self.a2, self.ai = adam1, adam2, adam4017
        self._start = start_monotonic
        self._tab = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        title = QLabel("시스템 상태"); title.setStyleSheet("font-size:20px; font-weight:900;")
        root.addWidget(title)

        body = QHBoxLayout()
        body.addWidget(self._summary_card(), 1)
        body.addWidget(self._io_card(), 1)
        root.addLayout(body)

    # ---------------------------------------------------------------- 좌: 요약
    def _summary_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card)
        head = QLabel("Controller / Communication"); head.setObjectName("cardTitle")
        lay.addWidget(head)
        grid = QGridLayout()
        self._b = {}
        specs = [
            ("app", "APPLICATION"), ("uptime", "UPTIME"),
            ("storage", "STORAGE FREE"), ("poll", "POLL / RETRY"),
            ("adam1", "ADAM-4055 #1"), ("adam2", "ADAM-4055 #2"),
            ("adam3", "ADAM-4017"), ("mA", "LOADCELL RAW"),
            ("vcmd", "VACUUM COMMAND"), ("vok", "VACUUM_OK"),
        ]
        for i, (k, label) in enumerate(specs):
            f, val = _box(label)
            self._b[k] = val
            grid.addWidget(f, i // 2, i % 2)
        lay.addLayout(grid)

        head2 = QLabel("진공 출력 허가"); head2.setObjectName("cardTitle")
        lay.addWidget(head2)
        self._perm = QLabel("-")
        self._perm.setStyleSheet("font-family:Consolas,monospace; font-size:12px;")
        lay.addWidget(self._perm)
        lay.addStretch(1)
        return card

    # ---------------------------------------------------------------- 우: I/O
    def _io_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card)
        tabs = QHBoxLayout()
        self._tabgroup = QButtonGroup(self); self._tabgroup.setExclusive(True)
        for i, name in enumerate(("ADAM #1 I/O", "ADAM #2 I/O", "Analog")):
            b = QPushButton(name); b.setObjectName("navBtn"); b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self._set_tab(idx))
            self._tabgroup.addButton(b, i)
            tabs.addWidget(b)
        self._tabgroup.button(0).setChecked(True)
        lay.addLayout(tabs)
        self._io = QLabel("")
        self._io.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._io.setStyleSheet("font-family:Consolas,monospace; font-size:13px; line-height:150%;")
        lay.addWidget(self._io, 1)
        return card

    def _set_tab(self, idx: int) -> None:
        self._tab = idx

    # ---------------------------------------------------------------- 갱신
    def update_view(self) -> None:
        c = self.ctrl
        up = int(time.monotonic() - self._start)
        self._b["app"].setText("RUNNING")
        self._b["uptime"].setText(f"{up // 3600:02d}:{up % 3600 // 60:02d}:{up % 60:02d}")
        try:
            free = shutil.disk_usage(".").free / 1e9
            self._b["storage"].setText(f"{free:.1f} GB")
        except OSError:
            self._b["storage"].setText("-")
        self._b["poll"].setText(f"{c.cfg.poll_ms} ms / {c.cfg.retries}")
        conn = "CONNECTED" if c.adam2_connected else "DISCONNECTED"
        self._b["adam1"].setText(conn)
        self._b["adam2"].setText(conn)
        self._b["adam3"].setText(conn)
        self._b["mA"].setText(f"{c.io.ma(AI.LOADCELL_CURRENT):.2f} mA")
        self._b["vcmd"].setText("ON" if c.vacuum_command else "OFF")
        self._b["vok"].setText("ON" if c.vacuum_ok else "OFF")

        allowed, reason = c.vacuum_permission()
        self._perm.setText(
            f"K_VACUUM_ON\n"
            f"  Command    : {'ON' if c.vacuum_command else 'OFF'}\n"
            f"  Permission : {'ALLOWED' if allowed else 'BLOCKED'}\n"
            f"  Actual     : {'ON' if c.out.vacuum_on else 'OFF'}\n"
            f"  Reason     : {reason or '-'}"
        )

        self._io.setText(self._io_text())

    def _io_text(self) -> str:
        if self._tab == 2:
            lines = ["채널   신호명              mA"]
            for sig in AI:
                lines.append(f"AI-{int(sig):02d}  {sig.name:<18} {self.ai.read_ma(int(sig)):5.2f}")
            return "\n".join(lines)
        module, di_enum, do_enum = (
            (self.a1, DI1, DO1) if self._tab == 0 else (self.a2, DI2, DO2)
        )
        di = module.read_di(); do = module.read_do()
        lines = ["채널   DI 신호            상태   채널   DO 신호            상태"]
        for i in range(8):
            di_name = di_enum(i).name
            do_name = do_enum(i).name
            di_s = "ON " if di[i] else "off"
            do_s = "ON " if do[i] else "off"
            lines.append(f"DI-{i:02d}  {di_name:<16} {di_s}   DO-{i:02d}  {do_name:<16} {do_s}")
        return "\n".join(lines)
