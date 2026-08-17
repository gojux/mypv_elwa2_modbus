"""Small shared helpers for the MyPV ELWA 2 Modbus integration."""

from __future__ import annotations

import struct


def decode_serial_number(registers: list[int]) -> str:
    """Decode the AC ELWA 2 serial number from its Modbus registers.

    Per my-PV's official documentation, the serial number is stored as 2
    ASCII characters per 16-bit register across registers 1018-1025 (see
    REG_SERIAL_NUMBER_BASE / REG_SERIAL_NUMBER_COUNT in const.py). Trailing
    null bytes/whitespace are stripped.
    """
    chars = "".join(
        struct.pack(">H", reg).decode("ascii", errors="replace") for reg in registers
    )
    return chars.replace("\x00", "").strip()
