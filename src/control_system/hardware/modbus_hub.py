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

    # --- ASCII 명령 전송 --------------------------------------------------
    def command(self, cmd: str, *, want_reply: bool = True) -> str:
        """ADAM ASCII 명령을 보내고 응답(CR 제거)을 돌려준다.

        want_reply=True 인데 응답이 없으면 retries 만큼 재시도 후 AdamCommError.
        """
        if self._ser is None:
            raise AdamCommError("serial not connected")
        for _ in range(self.retries + 1):
            self._ser.reset_input_buffer()
            self._ser.write((cmd + "\r").encode("ascii"))
            resp = self._read_until_cr()
            if not want_reply or resp:
                return resp
        raise AdamCommError(f"no response to {cmd!r}")

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
