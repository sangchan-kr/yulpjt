# 반복 가압 측정기 — 하드웨어 없이 시뮬레이션(mock) 실행 (Windows 개발용)
#
#   HMI 창 + 제어함 시뮬레이터 창(외부 스위치/센서/로드셀) 이 함께 뜬다.
#   콘솔 창에 로그가 나오며, 콘솔을 닫으면 종료된다.
#
# 사용:  우클릭 → PowerShell 로 실행,  또는  터미널에서  ./run-sim.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:MOCK_HW  = "1"   # 1=모의 하드웨어(실 하드웨어 없이). 파이에서 실 I/O 는 0.
$env:DEBUG_IO = "1"   # 1=제어함 시뮬레이터 창 표시
$env:BOOT     = "0"   # 0=부팅화면 건너뜀(개발 편의). 부팅 흐름 보려면 1.
$env:KIOSK    = "0"   # 0=창 모드(개발). 파이 전체화면은 1.

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "가상환경(.venv)이 없습니다. 먼저 아래를 실행하세요:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\python -m pip install -e ."
    exit 1
}
Write-Host "시뮬레이션 실행 (MOCK_HW=1, 제어함 시뮬 표시). 종료하려면 이 창을 닫으세요." -ForegroundColor Cyan
& $py -m control_system
