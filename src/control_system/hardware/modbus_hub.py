"""단일 RS-485 버스(pymodbus 시리얼 클라이언트) 래퍼.

3개 노드(ADAM-4055-C #1/#2, ADAM-4017+-F)가 하나의 버스를 공유하므로
클라이언트는 여기서 한 번만 만들고 각 모듈이 unit_id 로 구분해 사용한다.

mock 모드에서는 아무 것도 열지 않는다 — 각 하드웨어 모듈이 자체적으로
합성 데이터를 만든다. 실 Modbus 경로는 하드웨어 입고 후(Phase D) 검증한다.
"""


class ModbusHub:
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
        self._client = None
        if mock:
            return
        # 실 하드웨어에서만 pymodbus 를 import (개발 노트북에는 없어도 됨).
        from pymodbus.client import ModbusSerialClient

        self._client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            parity=parity,
            stopbits=stopbits,
            bytesize=bytesize,
            timeout=timeout_ms / 1000.0,
        )

    def connect(self) -> bool:
        if self.mock:
            return True
        return bool(self._client.connect())

    def close(self) -> None:
        if not self.mock and self._client is not None:
            self._client.close()

    # --- 저수준 Modbus 액세스 (실 모드) -----------------------------------
    # 주의: ADAM-4055-C / ADAM-4017+ 의 실제 레지스터 주소는 Advantech 매뉴얼로
    # 확인해야 한다. 여기서는 표준 함수만 노출하고 주소는 각 모듈이 넘긴다.
    def read_discrete_inputs(self, unit: int, address: int, count: int) -> list[bool]:
        rr = self._client.read_discrete_inputs(address, count=count, device_id=unit)
        if rr.isError():
            raise ModbusError(f"read_discrete_inputs unit={unit} addr={address}: {rr}")
        return list(rr.bits[:count])

    def read_coils(self, unit: int, address: int, count: int) -> list[bool]:
        rr = self._client.read_coils(address, count=count, device_id=unit)
        if rr.isError():
            raise ModbusError(f"read_coils unit={unit} addr={address}: {rr}")
        return list(rr.bits[:count])

    def write_coils(self, unit: int, address: int, values: list[bool]) -> None:
        rr = self._client.write_coils(address, list(values), device_id=unit)
        if rr.isError():
            raise ModbusError(f"write_coils unit={unit} addr={address}: {rr}")

    def read_input_registers(self, unit: int, address: int, count: int) -> list[int]:
        rr = self._client.read_input_registers(address, count=count, device_id=unit)
        if rr.isError():
            raise ModbusError(f"read_input_registers unit={unit} addr={address}: {rr}")
        return list(rr.registers[:count])


class ModbusError(RuntimeError):
    """Modbus 통신 오류 (상위에서 ADAM_COMM_ERROR 알람으로 처리)."""
