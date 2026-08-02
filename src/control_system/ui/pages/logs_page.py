"""로그 페이지 (목업 v0.3 / handoff §12).

탭: 운전 기록(사이클 CSV) · 알람 · 이벤트(메모리 이벤트 로그) · 하중 트렌드(C5).
알람과 이벤트를 분리해, 상태전환 등 이벤트에 묻히지 않고 알람만 확인할 수 있게 한다.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

# 이벤트 코드 분류: 알람 탭(문제/경고) vs 이벤트 탭(상태전환·조작).
_ALARM_CODES = {"ALARM", "VACUUM_WARN"}
_EVENT_CODES = {"STATE", "VACUUM_COMMAND"}
_CODE_KO = {"ALARM": "알람", "VACUUM_WARN": "진공경고",
            "STATE": "상태전환", "VACUUM_COMMAND": "진공명령"}


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
        for i, name in enumerate(("운전 기록", "알람", "이벤트", "하중 트렌드")):
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
            self._body.setText(self._event_text(_ALARM_CODES, "알람 없음."))
        elif self._tab == 2:
            self._body.setText(self._event_text(_EVENT_CODES, "이벤트 없음."))
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

    def _event_text(self, codes, empty: str) -> str:
        items = self.event_log.recent(60, codes=codes)
        if not items:
            return empty
        lines = ["시각       종류        상세"]
        for ts, code, detail in items:
            lines.append(f"{ts}   {_CODE_KO.get(code, code):<8} {detail}")
        return "\n".join(lines)
