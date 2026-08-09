"""매뉴얼 마크다운 → PDF 빌드 (PySide6 QTextDocument, 별도 설치 불필요).

사용: python docs/manual/build_pdf.py [입력.md] [출력.pdf]
기본: 반복가압측정기_조작설명서.md → 반복가압측정기_조작설명서.pdf
한글 폰트: Windows 'Malgun Gothic'(없으면 NanumGothic). A4, GitHub 표 지원.
"""
import os
import sys

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QFont, QFontDatabase, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QApplication

_HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "반복가압측정기_조작설명서.md")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(SRC)[0] + ".pdf"

# 표지/본문 가독성용 최소 CSS (QTextDocument 지원 범위).
_CSS = """
h1 { font-size: 20pt; color: #1b2735; }
h2 { font-size: 15pt; color: #1f5fa6; border-bottom: 1px solid #c9d4e0; }
h3 { font-size: 12pt; color: #28323f; }
table { border-collapse: collapse; }
th, td { border: 1px solid #b8c4d0; padding: 3px 7px; }
th { background: #eef2f7; }
code { background: #eef2f7; }
"""


def _pick_korean_font() -> str:
    # TTF 파일을 직접 로드해 글리프를 확실히 확보한다(offscreen 등에서 families() 만으론
    # 이름은 잡혀도 글리프가 안 실려 □ 로 나오는 문제 방지).
    for p in ("C:/Windows/Fonts/malgun.ttf",
              "C:/Windows/Fonts/malgunsl.ttf",
              "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
              "C:/Windows/Fonts/NanumGothic.ttf"):
        if os.path.exists(p):
            fid = QFontDatabase.addApplicationFont(p)
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                return fams[0]
    inst = set(QFontDatabase.families())
    for f in ("Malgun Gothic", "맑은 고딕", "NanumGothic", "Noto Sans CJK KR"):
        if f in inst:
            return f
    return "Sans Serif"


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 (QGuiApplication 컨텍스트 필요)
    with open(SRC, encoding="utf-8") as f:
        md = f.read()

    fam = _pick_korean_font()
    doc = QTextDocument()
    doc.setDefaultFont(QFont(fam, 10))
    doc.setDefaultStyleSheet(_CSS)
    doc.setMarkdown(md, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)

    writer = QPdfWriter(OUT)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setResolution(150)
    writer.setPageMargins(QMarginsF(16, 14, 16, 16), QPageLayout.Unit.Millimeter)
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print_(writer)

    print(f"[OK] font={fam}  pages={doc.pageCount()}  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
