"""RS-485 시리얼 버스 — Advantech ADAM ASCII(DCON) 프로토콜 전송 계층.

※ 원래 Modbus RTU 래퍼였으나, 현장 ADAM-4055/4017+ 모듈이 ASCII 모드로 동작하고
   (프로토콜 전환은 Windows 유틸리티 전용) 파이에서 설정 가능한 ASCII 로 전환했다.
   파일명은 호환을 위해 유지. 3개 노드(4055 #1/#2, 4017+)가 한 버스를 공유하므로
   시리얼 포트는 여기서 한 번만 열고 각 모듈이 주소(unit_id)로 구분해 명령한다.

명령/응답 규약(DCON): 명령 문자열 + CR(0x0D) 전송 → 응답을 CR 까지 읽음.
  성공 응답은 '!' 또는 '>' 로 시작, 오류는 '?' 로 시작, 무응답은 타임아웃.

mock 모드에서는 포트를 열지 않는다(각 모듈이 합성 데이터 생성).
"""


class AdamSerialBus:
    def __init__(
        self,
        port: str,
        baudrate: int,
        *,
        parity: str = "N",
        stopbits: int = 1,
        bytesize: int = 8,
        timeout_ms: int = 400,
        retries: int = 2,
        mock: bool = False,
    ) -> None:
        self.mock = mock
        self.retries = retries
        self._port = port
        self._baudrate = baudrate
        self._parity = parity
        self._stopbits = stopbits
        self._bytesize = bytesize
        self._timeout = timeout_ms / 1000.0
        self._ser = None

    def connect(self) -> bool:
        if self.mock:
            return True
        import serial  # 실 하드웨어에서만 pyserial import (개발 노트북엔 없어도 됨)

        if self._ser is not None and self._ser.is_open:
            return True
        if "://" in self._port:
            # 원격 시리얼(예: socket://IP:PORT) — 파이 TCP↔시리얼 브리지 경유 테스트용.
            self._ser = serial.serial_for_url(self._port, timeout=self._timeout)
        else:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                parity=self._parity,
                stopbits=self._stopbits,
                timeout=self._timeout,
            )
        return bool(self._ser.is_open)

    def close(self) -> None:
        if not self.mock and self._ser is not None:
            self._ser.close()

    def _resolve_port(self) -> str:
        """USB 재열거로 ttyUSB 번호가 바뀌어도 CP210x by-id(고정 심링크)로 다시 찾는다.

        socket:// URL 이나 명시 경로가 살아있으면 그대로. 없으면 by-id → ttyUSB* 순.
        """
        if "://" in self._port:
            return self._port
        import glob
        import os
        if os.path.exists(self._port) and "by-id" in self._port:
            return self._port                       # 안정적 by-id 경로면 유지
        byid = sorted(glob.glob("/dev/serial/by-id/*CP210*")) \
            or sorted(glob.glob("/dev/serial/by-id/*ADAM*"))
        if byid:
            return byid[0]
        if os.path.exists(self._port):
            return self._port
        tty = sorted(glob.glob("/dev/ttyUSB*"))
        return tty[0] if tty else self._port

    def _reopen(self) -> None:
        """죽은 fd 를 닫고 포트를 재탐색해 다시 연다(USB 재열거 복구)."""
        try:
            if self._ser is not None:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self._port = self._resolve_port()
        self.connect()

    # --- ASCII 명령 전송 --------------------------------------------------
    def command(self, cmd: str, *, want_reply: bool = True) -> str:
        """ADAM ASCII 명령을 보내고 응답(CR 제거)을 돌려준다.

        시리얼 오류(USB 재열거 등)면 포트를 재오픈하고, want_reply 인데 응답이 없으면
        retries 만큼 재시도한다. 모두 실패하면 AdamCommError — 단 재오픈은 시도했으므로
        다음 스캔에서 자동 복구된다.
        """
        last = "no response"
        for _ in range(self.retries + 1):
            try:
                if self._ser is None or not self._ser.is_open:
                    self._reopen()
                self._ser.reset_input_buffer()
                self._ser.write((cmd + "\r").encode("ascii"))
                resp = self._read_until_cr()
                if not want_reply or resp:
                    return resp
                last = f"no response to {cmd!r}"
            except OSError as e:            # SerialException 포함(USB 끊김/재열거)
                last = str(e)
                try:
                    self._reopen()          # 죽은 포트 재오픈 시도 후 재시도
                except Exception as e2:
                    last = f"{e} / reopen 실패: {e2}"
                    self._ser = None        # 다음 시도에서 다시 연결 시도
        raise AdamCommError(f"command 실패 {cmd!r}: {last}")

    def _read_until_cr(self) -> str:
        buf = bytearray()
        while True:
            b = self._ser.read(1)
            if not b:                 # 타임아웃
                break
            if b == b"\r":
                break
            buf += b
        return buf.decode("ascii", errors="replace").strip()


# 하위 호환 별칭 (구 코드/테스트가 ModbusHub 를 참조할 수 있음)
ModbusHub = AdamSerialBus


class AdamCommError(RuntimeError):
    """ADAM 시리얼 통신 오류 (상위에서 ADAM_COMM_ERROR 알람으로 처리)."""


ModbusError = AdamCommError   # 하위 호환 별칭
