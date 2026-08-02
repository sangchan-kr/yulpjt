"""운전 조건 설정 페이지 (목업 v0.4 / handoff §10).

좌: 반복 가압 조건, 우: 하중 및 표시 조건 (2카드). 값 칸을 누르면 터치 키패드로
편집(대기 값에 저장). 불리언(데이터 저장)은 누르면 사용/미사용 토글.
저장은 Idle 상태에서만 허용. 취소=되돌리기, 기본값=Config 기본값.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...config import RuntimeSettings
from ...core.states import State
from .. import theme
from ..keypad import edit_number

_IDLE = {State.AUTO_IDLE, State.MANUAL_IDLE, State.AUTO_COMPLETE}

# (attr, 라벨, 단위, kind, 표시배수)  kind: "int" | "float" | "bool"
_LEFT = [
    ("target_count", "목표 반복 횟수", "회", "int", 1),
    ("down_dwell_ms", "하강 유지시간", "초", "float", 0.001),
    ("up_dwell_ms", "상승 유지시간", "초", "float", 0.001),
    ("down_timeout_ms", "하강 제한시간", "초", "float", 0.001),
    ("up_timeout_ms", "상승 제한시간", "초", "float", 0.001),
    ("down_load_detect", "하강 하중 도달 사용", "", "bool", 1),
    ("down_load_threshold_kgf", "하강 도달 하중", "kgf", "float", 1),
]
_RIGHT = [
    ("load_limit_kgf", "하중 상한", "kgf", "float", 1),
    ("vacuum_confirm_timeout_ms", "진공 확인 제한시간", "초", "float", 0.001),
    ("data_save", "하중 데이터 저장", "", "bool", 1),
    ("trend_window_s", "그래프 표시 구간", "초", "int", 1),
    ("brightness", "화면 밝기", "%", "int", 1),
]
_FIELDS = _LEFT + _RIGHT

_INPUT_QSS = ("background:#ffffff; border:1px solid #cfd8e2; border-radius:8px;"
              "padding:7px 12px; font-weight:900; color:#1b2735;")


class SettingsPage(QWidget):
    def __init__(self, controller, settings_path: str, cfg) -> None:
        super().__init__()
        self.ctrl = controller
        self.settings_path = settings_path
        self.cfg = cfg
        self._pending = dict(self._snapshot())
        self._value_labels: dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)
        title = QLabel("운전 조건 설정")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._group_card("반복 가압 조건", _LEFT), 1)
        body.addWidget(self._group_card("하중 및 표시 조건", _RIGHT), 1)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        self._note = QLabel("")
        self._note.setStyleSheet(f"color:{theme.YELLOW}; font-weight:700;")
        bottom.addWidget(self._note)
        bottom.addStretch(1)
        self._b_default = QPushButton("기본값"); self._b_default.clicked.connect(self._restore_default)
        self._b_cancel = QPushButton("취소"); self._b_cancel.clicked.connect(self._cancel)
        self._b_save = QPushButton("저장"); self._b_save.setObjectName("navBtn"); self._b_save.setCheckable(False)
        self._b_save.clicked.connect(self._save)
        for b in (self._b_default, self._b_cancel, self._b_save):
            b.setMinimumHeight(42); b.setMinimumWidth(84)
            bottom.addWidget(b)
        root.addLayout(bottom)
        self._refresh_labels()

    def _group_card(self, title: str, fields) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QLabel(title); head.setObjectName("cardTitle")
        lay.addWidget(head)
        grid = QGridLayout(); grid.setVerticalSpacing(10); grid.setHorizontalSpacing(10)
        for row, (attr, label, unit, kind, _m) in enumerate(fields):
            lbl = QLabel(label)
            grid.addWidget(lbl, row, 0)
            box = QLabel("-")
            box.setStyleSheet(_INPUT_QSS)
            box.setMinimumWidth(150)
            box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            box.mousePressEvent = lambda _e, a=attr, l=label, k=kind: self._edit(a, l, k)
            self._value_labels[attr] = box
            grid.addWidget(box, row, 1)
            u = QLabel(unit); u.setObjectName("mini")
            grid.addWidget(u, row, 2)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        return card

    def _snapshot(self) -> dict:
        s = self.ctrl.settings
        return {a: getattr(s, a) for a, *_ in _FIELDS}

    def _mult(self, attr):
        return next(m for a, _l, _u, _k, m in _FIELDS if a == attr)

    def _kind(self, attr):
        return next(k for a, _l, _u, k, _m in _FIELDS if a == attr)

    def _fmt(self, attr: str, val) -> str:
        kind = self._kind(attr)
        if kind == "bool":
            return "사용" if val else "미사용"
        mult = self._mult(attr)
        v = val * mult
        return f"{v:.2f}" if kind == "float" else f"{int(v)}"

    def _refresh_labels(self) -> None:
        for attr, box in self._value_labels.items():
            box.setText(self._fmt(attr, self._pending[attr]))

    def _edit(self, attr: str, label: str, kind: str) -> None:
        if not self._is_idle():
            return
        if kind == "bool":
            self._pending[attr] = not self._pending[attr]
            self._refresh_labels()
            return
        mult = self._mult(attr)
        is_float = kind == "float"
        cur = self._pending[attr] * mult
        cur = round(cur, 2) if is_float else int(cur)
        new = edit_number(self, label, cur, is_float)
        if new is None:
            return
        stored = new / mult
        self._pending[attr] = float(stored) if (is_float and mult == 1) else int(round(stored))
        self._refresh_labels()

    def _restore_default(self) -> None:
        if not self._is_idle():
            return
        d = RuntimeSettings.from_config(self.cfg)
        self._pending = {a: getattr(d, a) for a, *_ in _FIELDS}
        self._refresh_labels()

    def _cancel(self) -> None:
        self._pending = dict(self._snapshot())
        self._refresh_labels()

    def _save(self) -> None:
        if not self._is_idle():
            return
        for attr, val in self._pending.items():
            setattr(self.ctrl.settings, attr, val)
        self.ctrl.settings.save(self.settings_path)
        self._note.setText("저장되었습니다.")

    def _is_idle(self) -> bool:
        return self.ctrl.state in _IDLE

    def update_view(self) -> None:
        idle = self._is_idle()
        for b in (self._b_default, self._b_cancel, self._b_save):
            b.setEnabled(idle)
        if not idle:
            self._note.setText("설정은 대기 상태에서만 변경할 수 있습니다.")
        elif self._note.text().startswith("설정은"):
            self._note.setText("")
