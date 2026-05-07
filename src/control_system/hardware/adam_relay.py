class AdamRelay:
    NUM_CHANNELS = 8

    def __init__(self, port: str, baudrate: int, address: int, *, mock: bool = False) -> None:
        self.mock = mock
        self._state = [False] * self.NUM_CHANNELS
        if not mock:
            raise NotImplementedError("Real Modbus RTU driver — install hardware first")

    def read_all(self) -> list[bool]:
        return list(self._state)

    def set_channel(self, channel: int, on: bool) -> None:
        self._state[channel] = on
