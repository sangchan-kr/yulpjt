"""운전 조건 설정 페이지 (목업 v0.3 / handoff §10).

- 값 칸을 누르면 터치 키패드로 편집(대기 값에 저장).
- 저장은 Idle 상태에서만 허용. 저장 시 컨트롤러 설정에 적용 + 디스크 영속.
- 취소=되돌리기, 기본값 복원=Config 기본값.
"""

from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...config import RuntimeSettings
from ...core.states import State
from .. import theme
from ..keypad import edit_number

_IDLE = {State.AUTO_IDLE, State.MANUAL_IDLE, State.AUTO_COMPLETE}

# (attr, 라벨, 단위, is_float, 표시배수) — ms 는 초로 표시
_FIELDS = [
    ("target_count", "목표 반복 횟수", "회", False, 1),
    ("down_dwell_ms", "Down Dwell Time", "sec", True, 0.001),
    ("up_dwell_ms", "Up Dwell Time", "sec", True, 0.001),
    ("down_timeout_ms", "실린더 하강 Timeout", "sec", True, 0.001),
    ("up_timeout_ms", "실린더 상승 Timeout", "sec", True, 0.001),
    ("load_limit_kgf", "하중 상한", "kgf", True, 1),
    ("vacuum_confirm_timeout_ms", "Vacuum Confirm Timeout", "sec", True, 0.001),
]


class SettingsPage(QWidget):
    def __init__(self, controller, settings_path: str, cfg) -> None:
        super().__init__()
        self.ctrl = controller
        self.settings_path = settings_path
        self.cfg = cfg
        self._pending = dict(self._snapshot())
        self._value_labels: dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        title = QLabel("운전 조건 설정")
        title.setStyleSheet("font-size:20px; font-weight:900;")
        root.addWidget(title)

        card = QFrame(); card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 12, 14, 12)
        for i, (attr, label, unit, is_float, _) in enumerate(_FIELDS):
            grid.addWidget(QLabel(label), i, 0)
            box = QLabel("-")
            box.setStyleSheet("font-weight:900; background:#0e1726; border:1px solid #3a4b63;"
                              "border-radius:7px; padding:6px 12px;")
            box.mousePressEvent = lambda _e, a=attr, l=label, f=is_float: self._edit(a, l, f)
            self._value_labels[attr] = box
            grid.addWidget(box, i, 1)
            grid.addWidget(QLabel(unit), i, 2)
        root.addWidget(card)

        self._note = QLabel("")
        self._note.setStyleSheet(f"color:{theme.YELLOW};")
        root.addWidget(self._note)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._b_default = QPushButton("기본값 복원"); self._b_default.clicked.connect(self._restore_default)
        self._b_cancel = QPushButton("취소"); self._b_cancel.clicked.connect(self._cancel)
        self._b_save = QPushButton("저장"); self._b_save.clicked.connect(self._save)
        for b in (self._b_default, self._b_cancel, self._b_save):
            b.setMinimumHeight(44)
            actions.addWidget(b)
        root.addLayout(actions)
        root.addStretch(1)
        self._refresh_labels()

    def _snapshot(self) -> dict:
        s = self.ctrl.settings
        return {a: getattr(s, a) for a, *_ in _FIELDS}

    def _fmt(self, attr: str, val) -> str:
        for a, _l, _u, is_float, mult in _FIELDS:
            if a == attr:
                v = val * mult
                return f"{v:.2f}" if is_float else f"{int(v)}"
        return str(val)

    def _refresh_labels(self) -> None:
        for attr, box in self._value_labels.items():
            box.setText(self._fmt(attr, self._pending[attr]))

    def _edit(self, attr: str, label: str, is_float: bool) -> None:
        if not self._is_idle():
            return
        mult = next(m for a, _l, _u, _f, m in _FIELDS if a == attr)
        cur = self._pending[attr] * mult
        cur = round(cur, 2) if is_float else int(cur)
        new = edit_number(self, label, cur, is_float)
        if new is None:
            return
        stored = new / mult
        # ms 필드(mult=0.001)와 정수 필드는 정수로, 그 외 float 필드는 float 으로.
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
            self._note.setText("설정은 Idle 상태에서만 변경할 수 있습니다.")
        elif self._note.text().startswith("설정은"):
            self._note.setText("")
