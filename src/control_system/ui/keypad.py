"""터치용 숫자 키패드 다이얼로그 (조건설정 편집)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QLabel, QPushButton, QVBoxLayout,
)

from . import theme


class KeypadDialog(QDialog):
    def __init__(self, title: str, value, is_float: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(theme.QSS + "QDialog{background:#0f1828;}")
        self._is_float = is_float
        self._buf = str(value)
        self.result_value = None

        root = QVBoxLayout(self)
        self._label = QLabel(title)
        self._label.setObjectName("cardTitle")
        root.addWidget(self._label)
        self._disp = QLabel(self._buf)
        self._disp.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._disp.setStyleSheet("font-size:28px; font-weight:900; background:#0e1726;"
                                 "border:1px solid #3a4b63; border-radius:8px; padding:8px 12px;")
        root.addWidget(self._disp)

        grid = QGridLayout()
        keys = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0", ".", "←"]
        for i, k in enumerate(keys):
            b = QPushButton(k)
            b.setMinimumSize(70, 56)
            if k == "." and not is_float:
                b.setEnabled(False)
            b.clicked.connect(lambda _=False, key=k: self._press(key))
            grid.addWidget(b, i // 3, i % 3)
        root.addLayout(grid)

        actions = QGridLayout()
        b_clear = QPushButton("Clear"); b_clear.clicked.connect(self._clear)
        b_cancel = QPushButton("취소"); b_cancel.clicked.connect(self.reject)
        b_ok = QPushButton("확인"); b_ok.clicked.connect(self._accept)
        for b in (b_clear, b_cancel, b_ok):
            b.setMinimumHeight(48)
        actions.addWidget(b_clear, 0, 0)
        actions.addWidget(b_cancel, 0, 1)
        actions.addWidget(b_ok, 0, 2)
        root.addLayout(actions)

    def _press(self, key: str) -> None:
        if key == "←":
            self._buf = self._buf[:-1]
        elif key == "." and "." in self._buf:
            return
        else:
            self._buf += key
        self._disp.setText(self._buf or "0")

    def _clear(self) -> None:
        self._buf = ""
        self._disp.setText("0")

    def _accept(self) -> None:
        try:
            self.result_value = float(self._buf) if self._is_float else int(float(self._buf))
        except ValueError:
            self.result_value = None
        self.accept()


def edit_number(parent, title: str, value, is_float: bool):
    """키패드를 띄워 새 값을 받는다. 취소/오류면 None."""
    dlg = KeypadDialog(title, value, is_float, parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.result_value
    return None
