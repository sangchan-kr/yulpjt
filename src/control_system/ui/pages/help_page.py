"""도움말 페이지 (목업 v0.3 §도움말 — 빠른 사용법 + 하드웨어 조정)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
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

# 공압 하드웨어 수동 조정 (밸브 스피드 컨트롤러 · 압력 레귤레이터)
_HW_ADJUST = [
    ("속도 조절 — 스피드 컨트롤러(스피드콘)",
     "실린더 밸브의 배기 스피드 컨트롤러로 이동 속도를 조절합니다. "
     "<b>위쪽 = 상승 속도</b>, <b>아래쪽 = 하강 속도</b>. "
     "조이면 느려지고 풀면 빨라집니다. 조절 후 잠금 너트로 고정하세요."),
    ("최대 압력 — 레귤레이터(우측)",
     "우측 레귤레이터로 가압 <b>최대 압력</b>을 설정합니다. "
     "대략 <b>1 MPa 당 약 100 kgf</b> 로 환산해 목표 하중에 맞춰 미세 조절합니다. "
     "(예: 300 kgf 목표 → 약 3 MPa). 하중 상한(조건설정)보다 낮게 두는 것이 안전합니다."),
]

_NOTES = [
    "진공은 자동 사이클과 완전히 독립입니다. 자동 시작/완료/정지가 진공을 바꾸지 않습니다.",
    "Safety Stop 시 모든 액추에이터와 진공이 강제 OFF 되며, 복구 후 진공은 다시 눌러야 합니다.",
    "진공 경고(VACUUM_NOT_REACHED 등)는 자동운전을 멈추지 않는 참고 표시입니다.",
]


def _steps_card() -> QFrame:
    card = QFrame(); card.setObjectName("card")
    cl = QVBoxLayout(card)
    head = QLabel("빠른 사용법"); head.setObjectName("cardTitle")
    cl.addWidget(head)
    for i, (h, desc) in enumerate(_STEPS, 1):
        row = QHBoxLayout()
        num = QLabel(str(i))
        num.setFixedSize(28, 28)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet("background:#2f6fed; color:#ffffff; border-radius:14px; font-weight:900;")
        txt = QLabel(f"<b>{h}</b><br><span style='color:{theme.MUTED}'>{desc}</span>")
        txt.setTextFormat(Qt.TextFormat.RichText); txt.setWordWrap(True)
        row.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(txt, 1)
        cl.addLayout(row)
    return card


def _hw_card() -> QFrame:
    card = QFrame(); card.setObjectName("card")
    cl = QVBoxLayout(card)
    head = QLabel("하드웨어 조정 (공압)"); head.setObjectName("cardTitle")
    cl.addWidget(head)
    for h, desc in _HW_ADJUST:
        txt = QLabel(f"<b>{h}</b><br><span style='color:{theme.MUTED}'>{desc}</span>")
        txt.setTextFormat(Qt.TextFormat.RichText); txt.setWordWrap(True)
        txt.setStyleSheet("margin-bottom:6px;")
        cl.addWidget(txt)
    return card


class HelpPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        title = QLabel("도움말 / 매뉴얼"); title.setObjectName("pageTitle")
        root.addWidget(title)

        # 작은 화면(1024x600)이라 내용이 넘칠 수 있어 스크롤 영역에 담는다.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 6, 0)
        il.setSpacing(10)
        il.addWidget(_steps_card())
        il.addWidget(_hw_card())
        note = QLabel("• " + "\n• ".join(_NOTES))
        note.setStyleSheet(f"color:{theme.YELLOW};")
        note.setWordWrap(True)
        il.addWidget(note)
        il.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

    def update_view(self) -> None:
        pass
