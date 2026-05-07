import random


class AdamDigitalInput:
    NUM_CHANNELS = 16

    def __init__(self, port: str, baudrate: int, address: int, *, mock: bool = False) -> None:
        self.mock = mock
        self._mock_state = [False] * self.NUM_CHANNELS
        if not mock:
            raise NotImplementedError("Real Modbus RTU driver — install hardware first")

    def read_all(self) -> list[bool]:
        self._mock_state = [v ^ (random.random() < 0.05) for v in self._mock_state]
        return list(self._mock_state)
