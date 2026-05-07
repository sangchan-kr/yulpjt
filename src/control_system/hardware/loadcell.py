import math
import random
import time


class LoadCell:
    def __init__(self, dt_pin: int, sck_pin: int, *, mock: bool = False) -> None:
        self.mock = mock
        if not mock:
            raise NotImplementedError("Real HX711 driver — install hardware first")
        self._t0 = time.monotonic()

    def read_grams(self) -> float:
        t = time.monotonic() - self._t0
        return 50.0 + 30.0 * math.sin(t * 0.5) + random.gauss(0.0, 0.3)
