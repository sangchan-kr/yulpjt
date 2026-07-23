"""로그 페이지 (목업 v0.3 / handoff §12).

탭: 운전 기록(사이클 CSV) · 알람/이벤트(메모리 이벤트 로그) · 하중 트렌드(C5).
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class LogsPage(QWidget):
    def __init__(self, run_log_path: str, event_log) -> None:
        super().__init__()
        self.run_log_path = run_log_path
        self.event_log = event_log
        self._tab = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10); root.setSpacing(8)
        tabs = QHBoxLayout()
        self._group = QButtonGroup(self); self._group.setExclusive(True)
        for i, name in enumerate(("운전 기록", "알람/이벤트", "하중 트렌드")):
            b = QPushButton(name); b.setObjectName("tab"); b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self._set_tab(idx))
            self._group.addButton(b, i)
            tabs.addWidget(b)
        self._group.button(0).setChecked(True)
        tabs.addStretch(1)
        root.addLayout(tabs)

        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card)
        self._body = QLabel("")
        self._body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._body.setStyleSheet("font-size:15px; color:#28323f; line-height:170%;")
        cl.addWidget(self._body, 1)
        root.addWidget(card, 1)

    def _set_tab(self, idx: int) -> None:
        self._tab = idx
        self.update_view()

    def update_view(self) -> None:
        if self._tab == 0:
            self._body.setText(self._run_log_text())
        elif self._tab == 1:
            self._body.setText(self._event_text())
        else:
            self._body.setText("하중 실시간 트렌드는 C5 에서 제공됩니다.")

    def _run_log_text(self) -> str:
        if not os.path.exists(self.run_log_path):
            return "운전 기록 없음."
        try:
            with open(self.run_log_path, encoding="utf-8") as f:
                rows = f.read().strip().splitlines()
        except OSError:
            return "운전 기록을 읽을 수 없음."
        header, *data = rows
        lines = ["시각                  카운트   최대하중   알람"]
        for row in data[-20:][::-1]:
            parts = row.split(",")
            while len(parts) < 4:
                parts.append("")
            ts, cnt, load, alarms = parts[:4]
            lines.append(f"{ts:<20}  {cnt:>5}   {load:>8}   {alarms}")
        return "\n".join(lines) if data else "운전 기록 없음."

    def _event_text(self) -> str:
        items = self.event_log.recent(30)
        if not items:
            return "이벤트 없음."
        lines = ["시각       이벤트                        상세"]
        for ts, code, detail in items:
            lines.append(f"{ts}   {code:<28} {detail}")
        return "\n".join(lines)
