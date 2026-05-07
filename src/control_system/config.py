from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class Config:
    mock_hardware: bool = environ.get("MOCK_HW", "1") == "1"

    adam_serial_port: str = "/dev/ttyUSB0"
    adam_baudrate: int = 9600
    adam_di_address: int = 1
    adam_do_address: int = 2

    hx711_dt_pin: int = 5
    hx711_sck_pin: int = 6
