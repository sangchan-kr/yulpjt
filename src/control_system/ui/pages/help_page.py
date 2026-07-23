"""도움말 페이지 (목업 v0.3 §도움말 — 빠른 사용법)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from .. import theme

_STEPS = [
    ("Main Power 를 켭니다.", "부팅 및 ADAM 통신 초기점검 완료를 기다립니다."),
    ("제품을 흡착 위치에 놓습니다.", "필요하면 메인 화면에서 VACUUM ON 을 누르고 VACUUM_OK 를 확인합니다."),
    ("AUTO 모드를 선택합니다.", "제어반의 AUTO/MANUAL 셀렉터를 AUTO 위치로 돌립니다."),
    ("운전 조건을 확인합니다.", "반복 횟수, Down/Up Dwell, 하중 상한을 조건설정에서 확인합니다."),
    ("Auto Run/Start 버튼을 누릅니다.", "자동 가압 사이클이 시작되며 진공 상태는 자동으로 변경되지 않습니다."),
    ("운전 완료 후 진공을 해제합니다.", "제품을 꺼낼 준비가 되면 메인 화면에서 VACUUM OFF 를 누릅니다."),
]

_NOTES = [
    "진공은 자동 사이클과 완전히 독립입니다. 자동 시작/완료/정지가 진공을 바꾸지 않습니다.",
    "Safety Stop 시 모든 액추에이터와 진공이 강제 OFF 되며, 복구 후 진공은 다시 눌러야 합니다.",
    "진공 경고(VACUUM_NOT_REACHED 등)는 자동운전을 멈추지 않는 참고 표시입니다.",
]


class HelpPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        title = QLabel("빠른 사용법"); title.setObjectName("pageTitle")
        root.addWidget(title)

        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card)
        for i, (head, desc) in enumerate(_STEPS, 1):
            row = QHBoxLayout()
            num = QLabel(str(i))
            num.setFixedSize(28, 28)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet("background:#2f6fed; color:#ffffff; border-radius:14px; font-weight:900;")
            txt = QLabel(f"<b>{head}</b><br><span style='color:{theme.MUTED}'>{desc}</span>")
            txt.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(txt, 1)
            cl.addLayout(row)
        root.addWidget(card)

        note = QLabel("• " + "\n• ".join(_NOTES))
        note.setStyleSheet(f"color:{theme.YELLOW};")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch(1)

    def update_view(self) -> None:
        pass
