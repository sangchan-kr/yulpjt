"""운전 조건 설정 페이지 (목업 v0.4 / handoff §10).

좌: 반복 가압 조건, 우: 하중 및 표시 조건 (2카드). 값 칸을 누르면 터치 키패드로
편집(대기 값 _pending 에만 저장). 편집만으로는 운전에 반영되지 않는다.

버튼:
  적용 — 편집값을 현재 운전에 반영(+ settings.json 영속). 이걸 눌러야 반영된다.
  저장 — 슬롯(1~3)을 골라 현재 편집값을 레시피로 저장.
  레시피 1/2/3 — 확인 후 그 레시피를 불러와 즉시 적용.
모두 대기(Idle) 상태에서만 동작.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
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
    def __init__(self, controller, settings_path: str, cfg, recipes=None) -> None:
        super().__init__()
        self.ctrl = controller
        self.settings_path = settings_path
        self.cfg = cfg
        self.recipes = recipes
        self._pending = dict(self._snapshot())
        self._value_labels: dict[str, QLabel] = {}
        self._bool_boxes: dict[str, QCheckBox] = {}
        self._recipe_btns: list[QPushButton] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("운전 조건 설정")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        if self.recipes is not None:
            title_row.addWidget(QLabel("레시피"))
            for i in range(self.recipes.N):
                b = QPushButton(f"레시피 {i + 1}")
                b.setMinimumHeight(40); b.setMinimumWidth(120)
                b.clicked.connect(lambda _=False, idx=i: self._load_recipe(idx))
                self._recipe_btns.append(b)
                title_row.addWidget(b)
        root.addLayout(title_row)

        # 본문 그리드: 왼쪽 카드는 세로 전체(버튼이 없는 하단 좌측까지) 차지, 오른쪽은
        # 위=카드 / 아래=버튼. 왼쪽 카드가 더 커져 박스/간격을 키울 수 있다.
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(self._group_card("반복 가압 조건", _LEFT, spread=True, box_h=40),
                       0, 0, 2, 1)                       # 2행 span → 전체 높이
        grid.addWidget(self._group_card("하중 및 표시 조건", _RIGHT), 0, 1)

        bottom = QHBoxLayout()
        self._note = QLabel("")
        self._note.setStyleSheet(f"color:{theme.YELLOW}; font-weight:700;")
        # 문구가 길어도 오른쪽 열을 넓혀 왼쪽 카드를 밀지 않도록 가로 정책을 Ignored 로.
        self._note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bottom.addWidget(self._note, 1)
        bottom.addStretch(0)
        self._b_default = QPushButton("기본값"); self._b_default.clicked.connect(self._restore_default)
        self._b_cancel = QPushButton("취소"); self._b_cancel.clicked.connect(self._cancel)
        self._b_apply = QPushButton("적용"); self._b_apply.setObjectName("primary")
        self._b_apply.clicked.connect(self._apply)
        self._b_save = QPushButton("저장"); self._b_save.setObjectName("navBtn"); self._b_save.setCheckable(False)
        self._b_save.clicked.connect(self._save_recipe)
        for b in (self._b_default, self._b_cancel, self._b_apply, self._b_save):
            b.setMinimumHeight(42); b.setMinimumWidth(84)
            bottom.addWidget(b)
        grid.addLayout(bottom, 1, 1)                     # 버튼은 오른쪽 하단에만

        grid.setRowStretch(0, 1)                         # 오른쪽 카드 행이 늘어남
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)
        self._refresh_labels()

    def _group_card(self, title: str, fields, *, spread: bool = False,
                    box_h: int | None = None) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card)
        # spread 카드는 마지막 박스가 카드 하단 테두리에 붙지 않도록 아래 마진을 더 준다.
        lay.setContentsMargins(14, 12, 14, 18 if spread else 12); lay.setSpacing(8)
        head = QLabel(title); head.setObjectName("cardTitle")
        lay.addWidget(head)
        grid = QGridLayout()
        grid.setVerticalSpacing(18 if spread else 10)
        grid.setHorizontalSpacing(10)
        for row, (attr, label, unit, kind, _m) in enumerate(fields):
            lbl = QLabel(label)
            grid.addWidget(lbl, row, 0)
            if kind == "bool":
                cb = QCheckBox("사용")
                cb.setStyleSheet(
                    "QCheckBox{font-size:14px; font-weight:700; color:#1b2735;}"
                    "QCheckBox::indicator{width:24px; height:24px;}"
                )
                cb.toggled.connect(lambda on, a=attr: self._set_bool(a, on))
                self._bool_boxes[attr] = cb
                grid.addWidget(cb, row, 1)
                continue
            box = QLabel("-")
            box.setStyleSheet(_INPUT_QSS)
            box.setMinimumWidth(150)
            box.setFixedHeight(box_h or 36)     # 박스 높이 고정 → 남는 세로공간은 항목 간격으로
            box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            box.mousePressEvent = lambda _e, a=attr, l=label, k=kind: self._edit(a, l, k)
            self._value_labels[attr] = box
            grid.addWidget(box, row, 1)
            u = QLabel(unit); u.setObjectName("mini")
            grid.addWidget(u, row, 2)
        grid.setColumnStretch(1, 1)
        if spread:
            # 그리드가 카드의 남는 세로공간을 차지하고, 각 행을 균등 분배해 간격을 넓힌다.
            for r in range(len(fields)):
                grid.setRowStretch(r, 1)
            lay.addLayout(grid, 1)
        else:
            lay.addLayout(grid)
            lay.addStretch(1)
        return card

    # ------------------------------------------------------------ 값 편집
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
        for attr, cb in self._bool_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(bool(self._pending[attr]))
            cb.blockSignals(False)

    def _set_bool(self, attr: str, on: bool) -> None:
        if not self._is_idle():
            cb = self._bool_boxes[attr]
            cb.blockSignals(True); cb.setChecked(bool(self._pending[attr])); cb.blockSignals(False)
            return
        self._pending[attr] = on

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
        self._note.setText("기본값 불러옴")

    def _cancel(self) -> None:
        self._pending = dict(self._snapshot())
        self._refresh_labels()
        self._note.setText("되돌림")

    # ------------------------------------------------------------ 적용 / 저장
    def _apply(self) -> None:
        """편집값을 현재 운전에 반영(+영속). 이 버튼을 눌러야 반영된다."""
        if not self._is_idle():
            return
        for attr, val in self._pending.items():
            setattr(self.ctrl.settings, attr, val)
        self.ctrl.settings.save(self.settings_path)
        self._note.setText("적용됨")

    def _save_recipe(self) -> None:
        """현재 편집값을 레시피 슬롯(1~3)에 저장."""
        if not self._is_idle() or self.recipes is None:
            return
        i = self._pick_slot()
        if i is None:
            return
        self.recipes.put(i, self._pending)
        self._refresh_recipe_btns()
        self._note.setText(f"레시피 {i + 1} 저장")

    def _load_recipe(self, i: int) -> None:
        """불러올 값을 미리보기로 보여주고, ‘예’를 누르면 불러와 즉시 적용."""
        if not self._is_idle() or self.recipes is None:
            return
        if not self.recipes.is_set(i):
            self._note.setText(f"레시피 {i + 1} 비어있음")
            return
        data = self.recipes.get(i)
        if not self._confirm_load(i, data):     # 미리보기 다이얼로그에서 ‘예’
            return
        for attr, *_ in _FIELDS:
            if attr in data:
                self._pending[attr] = data[attr]
        self._refresh_labels()
        self._apply()                           # 불러오기 → 즉시 적용
        self._note.setText(f"레시피 {i + 1} 적용")

    def _confirm_load(self, i: int, data: dict) -> bool:
        """레시피 값 미리보기 + 예/아니오. 예면 True."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"레시피 {i + 1} 불러오기")
        dlg.setStyleSheet(theme.QSS + "QDialog{background:#eef2f7;}")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(f"레시피 {i + 1} 값을 불러와 지금 운전 조건에 적용할까요?"))
        card = QFrame(); card.setObjectName("card")
        g = QGridLayout(card); g.setVerticalSpacing(6); g.setHorizontalSpacing(10)
        r = 0
        for attr, label, unit, _k, _m in _FIELDS:
            if attr not in data:
                continue
            g.addWidget(QLabel(label), r, 0)
            val = QLabel(self._fmt(attr, data[attr]))
            val.setStyleSheet("font-weight:900; color:#1b2735;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            g.addWidget(val, r, 1)
            g.addWidget(QLabel(unit), r, 2)
            r += 1
        g.setColumnStretch(1, 1)
        v.addWidget(card)
        row = QHBoxLayout(); row.addStretch(1)
        no = QPushButton("아니오"); no.setMinimumSize(110, 44); no.clicked.connect(dlg.reject)
        yes = QPushButton("예"); yes.setObjectName("primary"); yes.setMinimumSize(110, 44)
        yes.clicked.connect(dlg.accept)
        row.addWidget(no); row.addSpacing(10); row.addWidget(yes)
        v.addLayout(row)
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _pick_slot(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("레시피 저장 위치")
        dlg.setStyleSheet(theme.QSS + "QDialog{background:#eef2f7;}")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("저장할 레시피 번호를 선택하세요"))
        chosen = {"i": None}
        for i in range(self.recipes.N):
            state = "사용중" if self.recipes.is_set(i) else "빈 슬롯"
            b = QPushButton(f"레시피 {i + 1}   ({state})")
            b.setMinimumHeight(48)
            b.clicked.connect(lambda _=False, idx=i: (chosen.__setitem__("i", idx), dlg.accept()))
            v.addWidget(b)
        c = QPushButton("취소"); c.clicked.connect(dlg.reject)
        v.addWidget(c)
        dlg.exec()
        return chosen["i"]

    def _refresh_recipe_btns(self) -> None:
        if self.recipes is None:
            return
        for i, b in enumerate(self._recipe_btns):
            b.setText(f"레시피 {i + 1}" if self.recipes.is_set(i) else f"레시피 {i + 1} (빈)")

    def _is_idle(self) -> bool:
        return self.ctrl.state in _IDLE

    def update_view(self) -> None:
        idle = self._is_idle()
        for b in (self._b_default, self._b_cancel, self._b_apply, self._b_save, *self._recipe_btns):
            b.setEnabled(idle)
        if not idle:
            self._note.setText("대기 상태에서만 변경 가능")
        elif self._note.text().startswith("대기 상태"):
            self._note.setText("")
        self._refresh_recipe_btns()
