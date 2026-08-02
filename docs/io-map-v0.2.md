# 버튼 램프 / 부저 / I/O Map / Relay Map

- Project: Raspberry Pi Pneumatic Press Control System
- Revision: v0.2
- Date: 2026-08-02
- Scope: 프로그래밍 및 전장 설계 전달용
- 기준 구성:
  - ADAM-4055-C × 2EA
  - ADAM-4017+-F × 1EA
  - 타워램프 제거
  - 버튼 내장 램프 4점 개별 제어
  - 부저 추가: Autonics B2PB-B1D-R
  - 진공 유닛: SMC ZK2A10K5KWA-06-B, NPN output

---

## 1. 설계 방향 요약

기존 타워램프는 공간상의 이유로 제거한다. 상태 표시는 아래 항목으로 처리한다.

| 표시 수단 | 역할 |
|---|---|
| HMI GUI | 상세 상태, 에러 원인, 카운트, 설정값, Safety Reset |
| 버튼 내장 램프 | 현재 조작 가능 버튼, 운전 상태, 에러 상태 안내 |
| 부저 B2PB-B1D-R | Error / Safety Stop / Vacuum fail 등 청각 알람 |

버튼 램프는 아래 4개를 개별 제어한다.

| Lamp Signal | 대상 |
|---|---|
| `LAMP_AUTO_START` | Auto Start 버튼 램프 |
| `LAMP_AUTO_STOP` | Auto Stop 버튼 램프 |
| `LAMP_MANUAL_UP` | Manual Up 버튼 램프 |
| `LAMP_MANUAL_DOWN` | Manual Down 버튼 램프 |

부저는 아래 신호로 제어한다.

| Signal | 대상 |
|---|---|
| `BUZZER` | Autonics B2PB-B1D-R |

---

## 2. 버튼 램프 및 부저 동작 시나리오

### 2.1 표시 상태 정의

| 표시 | 의미 |
|---|---|
| OFF | 사용 불가 또는 해당 상태 아님 |
| ON | 사용 가능 또는 동작 활성 |
| Slow Blink | 다음 조작 대기, Reset 대기, Start 가능 |
| Fast Blink | Error 또는 비정상 상태 |

권장 점멸 주기:

| Blink Type | 주기 | 용도 |
|---|---:|---|
| Slow Blink | 1 Hz | Start 대기, Reset 대기, Paused |
| Fast Blink | 2~4 Hz | Error, Vacuum timeout, Safety Stop 강조 |

### 2.2 시스템 초기화

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| System Boot / Init | OFF | OFF | OFF | OFF | OFF | Raspberry Pi / ADAM 초기화 중 |

프로그램 시작 시 모든 DO를 OFF로 초기화한다.

### 2.3 Safety Stop

조건:

```text
SOL_ENABLE_OK = OFF
또는 Safety Stop latch = ON
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Safety Stop | OFF | Fast Blink | OFF | OFF | Intermittent ON | EMO / Area / 구동허가 이상 |
| Safety Reset 가능 | OFF | Slow Blink | OFF | OFF | OFF 또는 짧은 알림 | SOL_ENABLE_OK 복귀 후 HMI Reset 대기 |

복귀 순서:

```text
1. EMO 해제
2. Area Sensor 정상
3. SOL_ENABLE_OK = ON 확인
4. HMI Safety Reset 버튼 누름
5. Auto Idle 또는 Manual Idle 복귀
```

Safety Reset은 HMI GUI 버튼으로만 구현한다. 물리 Reset 버튼은 사용하지 않는다.

### 2.4 Auto Idle

조건:

```text
MODE_AUTO = ON
SOL_ENABLE_OK = ON
state = AUTO_IDLE
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Auto Idle | Slow Blink | OFF | OFF | OFF | OFF | Start 입력 대기 |

### 2.5 Auto Running

조건:

```text
MODE_AUTO = ON
state = AUTO_RUNNING 계열
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Auto Running | ON | ON | OFF | OFF | OFF | 자동 운전 중, Stop 가능 |

### 2.6 Auto Paused

조건:

```text
MODE_AUTO = ON
state = AUTO_PAUSED
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Auto Paused | Slow Blink | ON | OFF | OFF | OFF | Start 누르면 재개 |

### 2.7 Auto Complete

조건:

```text
MODE_AUTO = ON
state = AUTO_COMPLETE
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Auto Complete | ON | OFF | OFF | OFF | 짧은 알림 1회, 선택 | 완료 상태, 재시작 가능 |

완료 알림 부저는 선택 기능이다. 운영자가 불편하면 완료 시 부저는 사용하지 않고 HMI 메시지만 표시한다.

### 2.8 Manual Idle

조건:

```text
MODE_AUTO = OFF
SOL_ENABLE_OK = ON
state = MANUAL_IDLE
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Manual Idle | OFF | OFF | ON | ON | OFF | 수동 상승/하강 가능 |

### 2.9 Manual Up

조건:

```text
MODE_AUTO = OFF
MANUAL_UP_PB = ON
state = MANUAL_MOVE_UP
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Manual Up | OFF | OFF | Blink 또는 ON | OFF | OFF | 상승 동작 중 |

Manual Up 버튼을 떼면 `K_VALVE_UP`을 OFF하고 DS6340은 Closed Center 상태가 된다.

### 2.10 Manual Down

조건:

```text
MODE_AUTO = OFF
MANUAL_DOWN_PB = ON
state = MANUAL_MOVE_DOWN
```

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Manual Down | OFF | OFF | OFF | Blink 또는 ON | OFF | 하강 동작 중 |

Manual Down 버튼을 떼면 `K_VALVE_DOWN`을 OFF하고 DS6340은 Closed Center 상태가 된다.

### 2.11 일반 Error

예:

- Cylinder Up timeout
- Cylinder Down timeout
- Loadcell communication error
- Loadcell range error
- Vacuum timeout
- Modbus communication error
- Valve interlock error

| 상태 | Auto Start | Auto Stop | Manual Up | Manual Down | Buzzer | 설명 |
|---|---:|---:|---:|---:|---:|---|
| Error | OFF | Fast Blink | OFF | OFF | Intermittent ON | HMI에서 에러 확인 및 Reset 필요 |

Safety Stop과 일반 Error 모두 Auto Stop 램프를 대표 알람 램프로 사용한다. 상세 원인은 HMI에 표시한다.

---

## 3. I/O Map

## 3.1 ADAM-4055-C #1 — Main Press / Switch / Safety Enable

### Digital Input Map

| Module | Channel | Signal Name | 연결 대상 | 기능 / 설명 |
|---|---:|---|---|---|
| ADAM-4055-C #1 | DI-00 | `MODE_AUTO` | Auto/Manual 셀렉터 | Auto 모드 선택 상태. ON=Auto, OFF=Manual |
| ADAM-4055-C #1 | DI-01 | `AUTO_START_PB` | Auto Run/Start 버튼 접점 | 자동 운전 시작 / 재개 |
| ADAM-4055-C #1 | DI-02 | `AUTO_STOP_PB` | Auto Stop 버튼 접점 | 자동 운전 정지 / 일시정지 |
| ADAM-4055-C #1 | DI-03 | `MANUAL_UP_PB` | Manual Up 버튼 접점 | 수동 상승 명령 |
| ADAM-4055-C #1 | DI-04 | `MANUAL_DOWN_PB` | Manual Down 버튼 접점 | 수동 하강 명령 |
| ADAM-4055-C #1 | DI-05 | `CYL_UP_POS` | 실린더 상승 위치 센서 | 상승 위치 확인 |
| ADAM-4055-C #1 | DI-06 | `CYL_DOWN_POS` | 실린더 하강 위치 센서 | 하강 위치 확인 |
| ADAM-4055-C #1 | DI-07 | `SOL_ENABLE_OK` | SOL_ENABLE_24V 피드백 | EMO/Area 조건 통과, 구동 가능 상태 |

### Digital Output Map

| Module | Channel | Signal Name | 연결 대상 | 기능 / 설명 |
|---|---:|---|---|---|
| ADAM-4055-C #1 | DO-00 | `LAMP_AUTO_START` | Auto Start 버튼 램프 | 자동 시작 가능 / 자동 운전 활성 상태 표시 |
| ADAM-4055-C #1 | DO-01 | `LAMP_AUTO_STOP` | Auto Stop 버튼 램프 | 정지 가능 / Error / Safety Stop 표시 |
| ADAM-4055-C #1 | DO-02 | `LAMP_MANUAL_UP` | Manual Up 버튼 램프 | 수동 상승 가능 / 상승 동작 표시 |
| ADAM-4055-C #1 | DO-03 | `LAMP_MANUAL_DOWN` | Manual Down 버튼 램프 | 수동 하강 가능 / 하강 동작 표시 |
| ADAM-4055-C #1 | DO-04 | `K_VALVE_DOWN` | RY-02 릴레이 코일 - | DS6340 Down solenoid 구동 릴레이 |
| ADAM-4055-C #1 | DO-05 | `K_VALVE_UP` | RY-03 릴레이 코일 - | DS6340 Up solenoid 구동 릴레이 |
| ADAM-4055-C #1 | DO-06 | `BUZZER` | BZ-01 Autonics B2PB-B1D-R | 알람 부저. 24VDC 직접 구동 |
| ADAM-4055-C #1 | DO-07 | `SPARE_DO_07` | 예비 | 예비 출력 |

---

## 3.2 ADAM-4055-C #2 — Vacuum System / Expansion I/O

### Digital Input Map

| Module | Channel | Signal Name | 연결 대상 | 기능 / 설명 |
|---|---:|---|---|---|
| ADAM-4055-C #2 | DI-00 | `VACUUM_OK_NPN` | ZK2A10K5KWA-06-B 진공 스위치 출력 | 흡착 진공 도달 확인. NPN 출력 기준 배선 확인 필요 |
| ADAM-4055-C #2 | DI-01 | `VACUUM_RELEASE_OK` | 선택 입력 | 파기 완료 / 압력 복귀 확인. 미사용 시 예비 |
| ADAM-4055-C #2 | DI-02 | `AIR_PRESS_OK` | 공압 압력 스위치, 선택 | 공급 공압 정상 확인. 미사용 시 예비 |
| ADAM-4055-C #2 | DI-03 | `VACUUM_UNIT_ALARM` | 진공 유닛 알람, 선택 | 진공 유닛 이상 확인. 미사용 시 예비 |
| ADAM-4055-C #2 | DI-04 | `SPARE_DI_04` | 예비 | 예비 입력 |
| ADAM-4055-C #2 | DI-05 | `SPARE_DI_05` | 예비 | 예비 입력 |
| ADAM-4055-C #2 | DI-06 | `SPARE_DI_06` | 예비 | 예비 입력 |
| ADAM-4055-C #2 | DI-07 | `SPARE_DI_07` | 예비 | 예비 입력 |

### Digital Output Map

| Module | Channel | Signal Name | 연결 대상 | 기능 / 설명 |
|---|---:|---|---|---|
| ADAM-4055-C #2 | DO-00 | `K_VACUUM_ON` | RY-04 릴레이 코일 - | ZK2A Vacuum valve 구동 릴레이 |
| ADAM-4055-C #2 | DO-01 | `K_BLOW_OFF_ON` | RY-05 릴레이 코일 - | ZK2A Blow-off valve 구동 릴레이 |
| ADAM-4055-C #2 | DO-02 | `SPARE_DO_02` | 예비 | 예비 출력 |
| ADAM-4055-C #2 | DO-03 | `SPARE_DO_03` | 예비 | 예비 출력 |
| ADAM-4055-C #2 | DO-04 | `SPARE_DO_04` | 예비 | 예비 출력 |
| ADAM-4055-C #2 | DO-05 | `SPARE_DO_05` | 예비 | 예비 출력 |
| ADAM-4055-C #2 | DO-06 | `SPARE_DO_06` | 예비 | 예비 출력 |
| ADAM-4055-C #2 | DO-07 | `SPARE_DO_07` | 예비 | 예비 출력 |

---

## 3.3 ADAM-4017+-F — Analog Input

| Module | Channel | Signal Name | 연결 대상 | 입력 형식 | 기능 |
|---|---:|---|---|---|---|
| ADAM-4017+-F | AI-00 | `LOADCELL_4_20mA` | NCT-I420 로드셀 트랜스미터 | 4–20 mA | 프레스 하중 측정 |
| ADAM-4017+-F | AI-01 | `SPARE_AI_01` | 예비 | - | 예비 |
| ADAM-4017+-F | AI-02 | `SPARE_AI_02` | 예비 | - | 예비 |
| ADAM-4017+-F | AI-03 | `SPARE_AI_03` | 예비 | - | 예비 |
| ADAM-4017+-F | AI-04 | `SPARE_AI_04` | 예비 | - | 예비 |
| ADAM-4017+-F | AI-05 | `SPARE_AI_05` | 예비 | - | 예비 |
| ADAM-4017+-F | AI-06 | `SPARE_AI_06` | 예비 | - | 예비 |
| ADAM-4017+-F | AI-07 | `SPARE_AI_07` | 예비 | - | 예비 |

---

## 4. Relay Map

| Relay ID | Relay Name | Coil + | Coil - / Drive | Contact Output | 비고 |
|---|---|---|---|---|---|
| RY-01 | `K_AREA_OK` | +24V_CTRL 또는 Area Sensor 출력 조건 | 0V_CTRL | SOL_ENABLE_24V 생성 경로의 NO 접점 | Area Sensor 정상 시 ON. EMO NC와 직렬로 SOL_ENABLE_24V 허가 |
| RY-02 | `K_VALVE_DOWN` | SOL_ENABLE_24V | ADAM-4055-C #1 DO-04 | DS6340 Down solenoid 전원 공급 | 프레스 하강. RY-03과 동시 ON 금지 |
| RY-03 | `K_VALVE_UP` | SOL_ENABLE_24V | ADAM-4055-C #1 DO-05 | DS6340 Up solenoid 전원 공급 | 프레스 상승. RY-02와 동시 ON 금지 |
| RY-04 | `K_VACUUM_ON` | SOL_ENABLE_24V 권장 | ADAM-4055-C #2 DO-00 | ZK2A Vacuum valve 전원 공급 | 흡착 진공 발생. RY-05와 동시 ON 금지 권장 |
| RY-05 | `K_BLOW_OFF_ON` | SOL_ENABLE_24V 권장 | ADAM-4055-C #2 DO-01 | ZK2A Blow-off valve 전원 공급 | 파기 Blow-off. ON 시간은 50–300 ms 범위에서 튜닝 |

---

## 5. Non-relay Output / Direct Drive Map

버튼 램프와 부저는 릴레이를 통하지 않고 ADAM-4055-C DO로 직접 sink 구동하는 기준이다.

| Device ID | Signal Name | Power + | Drive - | 비고 |
|---|---|---|---|---|
| LP-01 | `LAMP_AUTO_START` | +24V_CTRL | ADAM-4055-C #1 DO-00 | Auto Start 버튼 내장 램프 |
| LP-02 | `LAMP_AUTO_STOP` | +24V_CTRL | ADAM-4055-C #1 DO-01 | Auto Stop 버튼 내장 램프 |
| LP-03 | `LAMP_MANUAL_UP` | +24V_CTRL | ADAM-4055-C #1 DO-02 | Manual Up 버튼 내장 램프 |
| LP-04 | `LAMP_MANUAL_DOWN` | +24V_CTRL | ADAM-4055-C #1 DO-03 | Manual Down 버튼 내장 램프 |
| BZ-01 | `BUZZER` | +24V_CTRL | ADAM-4055-C #1 DO-06 | Autonics B2PB-B1D-R. 24VDC 직접 구동 |

---

## 6. 주요 인터락 규칙

### 6.1 프레스 밸브 인터락

DS6340 Closed Center 밸브는 Down / Up 양쪽 솔레노이드가 동시에 켜지면 안 된다.

| K_VALVE_DOWN | K_VALVE_UP | 상태 |
|---:|---:|---|
| OFF | OFF | Closed Center, 정지/위치 유지 시도 |
| ON | OFF | Down |
| OFF | ON | Up |
| ON | ON | 금지 상태. 즉시 양쪽 OFF + Error |

프로그램 규칙:

```python
if k_valve_down and k_valve_up:
    k_valve_down = False
    k_valve_up = False
    state = "ERROR"
    error_code = "VALVE_INTERLOCK"
```

### 6.2 진공 / 파기 인터락

`K_VACUUM_ON`과 `K_BLOW_OFF_ON`은 동시에 ON하지 않는다.

| K_VACUUM_ON | K_BLOW_OFF_ON | 상태 |
|---:|---:|---|
| OFF | OFF | 진공 미사용 |
| ON | OFF | 흡착 |
| OFF | ON | 파기 |
| ON | ON | 금지 상태. 즉시 양쪽 OFF + Error |

파기 시퀀스 권장:

```text
1. K_VACUUM_ON = OFF
2. 50 ms delay
3. K_BLOW_OFF_ON = ON
4. 50~300 ms 유지
5. K_BLOW_OFF_ON = OFF
```

### 6.3 Safety Stop 인터락

조건:

```text
SOL_ENABLE_OK = OFF
```

즉시 처리:

```text
K_VALVE_DOWN = OFF
K_VALVE_UP = OFF
K_VACUUM_ON = OFF
K_BLOW_OFF_ON = OFF
BUZZER = Intermittent ON
state = SAFETY_STOP
alarm_latched = True
```

`SOL_ENABLE_OK`가 다시 ON으로 복귀해도 HMI Safety Reset 전까지 자동 재시작하지 않는다.

---

## 7. ZK2A NPN 출력 주의사항

최종 선정 진공 유닛은 다음이다.

```text
SMC ZK2A10K5KWA-06-B
```

이 모델의 진공 스위치는 NPN output 기준이다.  
따라서 `VACUUM_OK_NPN` 입력은 ADAM-4055-C #2 DI 결선 방식을 확인해야 한다.

권장 처리 방법:

| 방식 | 설명 |
|---|---|
| ADAM DI를 NPN 출력에 맞게 배선 | 전장 도면에서 DI COM 및 입력 기준 전위 확인 필요 |
| 인터페이스 릴레이 또는 포토커플러 사용 | ADAM 입력을 접점 입력처럼 분리 가능 |
| 프로그램에서 신호 논리 반전 여부 확인 | NPN 출력 특성상 ON/OFF 논리 확인 필요 |

---

## 8. 부저 사용 기준

부저 대상:

```text
Autonics B2PB-B1D-R
```

용도:

| 상태 | 부저 동작 |
|---|---|
| System Boot | OFF |
| Auto Running | OFF |
| Auto Complete | 짧은 알림 1회, 선택 |
| Auto Paused | OFF |
| Manual Mode | OFF |
| Error | Intermittent ON |
| Safety Stop | Intermittent ON |
| Vacuum Timeout | Intermittent ON |
| Modbus Communication Error | Intermittent ON |

부저는 운영 환경에 따라 HMI에서 사용 여부를 설정할 수 있게 하는 것이 좋다.

권장 HMI 설정:

| 설정 항목 | 기본값 |
|---|---|
| `buzzer_enabled` | True |
| `buzzer_on_error` | True |
| `buzzer_on_complete` | False |
| `buzzer_mute_button` | True |

---

## 9. 전장 설계 전달 메모

1. 타워램프는 사용하지 않는다.
2. 버튼 램프 4개는 각각 독립 DO로 직접 제어한다.
3. 부저 B2PB-B1D-R은 #1 DO-06으로 직접 제어한다.
4. 프레스 밸브 릴레이와 진공 밸브 릴레이는 `SOL_ENABLE_24V`를 코일 + 전원으로 사용하는 것을 권장한다.
5. `SOL_ENABLE_24V`는 EMO NC 접점과 `K_AREA_OK` 접점을 통과한 전원이다.
6. `SOL_ENABLE_OK`는 실제 `SOL_ENABLE_24V` 상태를 ADAM-4055-C #1 DI-07로 피드백한다.
7. ZK2A10K5KWA-06-B의 `VACUUM_OK_NPN`은 NPN 출력이므로 입력 결선 방식과 신호 논리를 별도 확인한다.
8. Safety Reset은 물리 버튼이 아니라 HMI GUI 버튼으로만 처리한다.
