# Control System

Raspberry Pi 5 기반 산업용 제어/HMI.

## 하드웨어

- Raspberry Pi 5 (2GB)
- Waveshare 7" HDMI LCD (H), 1024×600, 정전식 터치 (USB)
- Advantech ADAM-4561 (USB ↔ RS-485) + ADAM-4055 (16ch DI) + ADAM-4068 (8ch 릴레이)
- HX711 + 로드셀

## 실행 

source .venv/bin/activate
python -m control_system
