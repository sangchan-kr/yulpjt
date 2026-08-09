"""HTML 매뉴얼 → PDF (Chrome/Edge headless print-to-pdf).

사용: python docs/manual/build_html_pdf.py [출력.pdf]
기본 입력: docs/manual/manual.html  ·  기본 출력: docs/manual/manual.pdf
@page CSS 로 A4·여백을 지정하며, 스크린샷/콜아웃/표가 그대로 인쇄된다.
"""
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(_HERE, "manual.html")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "반복가압측정기_매뉴얼.pdf")

_CANDS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    shutil.which("google-chrome"), shutil.which("chromium"),
    shutil.which("chrome"), shutil.which("msedge"),
]


def main() -> int:
    browser = next((c for c in _CANDS if c and os.path.exists(c)), None)
    if not browser:
        print("[ERR] Chrome/Edge 를 찾지 못했습니다. 브라우저에서 manual.html 을 열고 "
              "Ctrl+P → PDF 로 저장하세요.")
        return 1
    before = os.path.getmtime(OUT) if os.path.exists(OUT) else 0
    url = "file:///" + HTML.replace("\\", "/").replace(" ", "%20")
    cmd = [browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={OUT}", url]
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    after = os.path.getmtime(OUT) if os.path.exists(OUT) else 0
    if after <= before:
        print("[경고] 출력 PDF가 갱신되지 않았습니다. 해당 PDF를 뷰어에서 열어 두면 "
              "덮어쓰기가 막힙니다. 뷰어를 닫고 다시 실행하세요.")
        return 2
    print(f"[OK] {os.path.basename(browser)} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
