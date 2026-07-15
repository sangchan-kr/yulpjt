# Control System (v1.12)

Raspberry Pi 5 기반 **공압 가압 + 진공 흡착 제어 HMI**.
Pi 5 가 HMI, 제어 상태머신, Modbus RTU 통신, 데이터 로깅을 담당한다.

설계 기준: `yul_control_system_overview_v1.12.md`
상세 계획/진행 현황: [docs/refactor-plan-v1.12.md](docs/refactor-plan-v1.12.md),
[docs/dev-status.md](docs/dev-status.md)

## 하드웨어 (v1.12)

- Raspberry Pi 5 (2GB) + Waveshare 7" HDMI LCD (H), 1024×600 터치
- ADAM-4561-CE (USB ↔ RS-485), 단일 Modbus RTU 버스
- ADAM-4055-C ×2 (각 8 DI + 8 DO) — Node 1(프레스/스위치/타워), Node 2(진공 이젝터)
- ADAM-4017+-F (8ch 아날로그 입력) — Node 3, 로드셀 4-20 mA
- 로드셀 CSB-1T → NCT-I420 트랜스미터 → 4-20 mA (HX711 미사용)
- DS6340 5/3 밸브, SMC ZK2A 진공 이젝터, PTE-DRV 시그널 타워

> v1.12 는 Pi GPIO 를 쓰지 않는다(모든 I/O 가 RS-485/아날로그). 의존성은
> 순수 파이썬(PySide6·pymodbus·pyserial)이라 Windows 개발과 Pi 배포가 동일하다.

## 개발 환경 (노트북, mock)

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:MOCK_HW="1"
.\.venv\Scripts\python.exe -m control_system   # 창 모드, 하단 입력 시뮬레이터, Esc 종료
```

## 실행 (Pi, 실 하드웨어) — Phase D 이후

```sh
source .venv/bin/activate
MOCK_HW=0 python -m control_system            # 키오스크(풀스크린)
```

## 테스트

```powershell
.\.venv\Scripts\python.exe tests\test_hardware_smoke.py   # 하드웨어 계층 6
.\.venv\Scripts\python.exe tests\test_controller.py       # 상태머신 15
```

## 설정

`src/control_system/config.py` — 시리얼/노드/시퀀스 파라미터. 주요 값은 환경변수로도
덮어쓸 수 있다(`MOCK_HW`, `SERIAL_PORT`, `FULL_SCALE_KGF`, `LOAD_LIMIT_KGF`).
로드셀/앰프 게인 세팅 도움말: `python -m control_system.config`.
