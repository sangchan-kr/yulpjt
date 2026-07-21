"""C4 에서 채울 보조 페이지 자리표시자 (조건설정/시스템상태/로그/도움말)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import theme


class PlaceholderPage(QWidget):
    def __init__(self, title: str, note: str = "C4 에서 구현 예정") -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setStyleSheet("font-size:26px; font-weight:900;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = QLabel(note)
        s.setStyleSheet(f"color:{theme.MUTED};")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(s)

    def update_view(self) -> None:  # 공통 인터페이스 (아직 표시할 것 없음)
        pass
