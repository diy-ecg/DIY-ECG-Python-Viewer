"""
Serial transport and frame parser for the ECG Arduino binary protocol.

Frame layout (little-endian):
[uint8 count][count * uint16 sample][count * uint32 t_ms][uint16 crc16]
CRC is CRC-16/IBM (Modbus-style), init 0x0000, poly 0xA001, low byte first.
"""
from __future__ import annotations

import struct
import time
from typing import List, Optional, Tuple

import serial
from serial.tools import list_ports


CRC_POLY = 0xA001
MAX_SAMPLES = 255


def crc16_ibm(data: bytes) -> int:
    """Compute CRC-16/IBM over given bytes (poly 0xA001, init 0)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ CRC_POLY
            else:
                crc >>= 1
    return crc & 0xFFFF


class SerialPort:
    def __init__(self, baudrate: int = 115_200, timeout: float = 0.2) -> None:
        # Store serial settings; actual port is opened later.
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None

    def open_first(self) -> Optional[str]:
        """Try to open the first port that returns a valid frame."""
        ports = list(list_ports.comports())[::-1]  # reverse so later-listed ports are tried first
        if not ports:
            print("No serial ports found.")
            return None

        for port in ports:
            print(f"Trying {port.device} ...", end=" ", flush=True)
            try:
                # Open port and immediately probe with a frame request
                self.ser = serial.Serial(port.device, self.baudrate, timeout=self.timeout)
                if self._probe():
                    print("ok")
                    return port.device
            except Exception as exc:
                print(f"error ({exc})")
                self.ser = None
                continue
            print("not valid")
        return None

    def _probe(self) -> bool:
        """Send one request and validate a frame to confirm the device."""
        if self.ser is None:
            return False
        # Clear any stale bytes, then allow the Arduino to reboot after port open
        self.ser.reset_input_buffer()
        # Allow the board to reboot after port open (common on Arduino)
        time.sleep(1.5)
        try:
            for _ in range(3):
                samples, _ = self.request_frame()
                if samples:
                    return True
                time.sleep(0.05)
                self.ser.reset_input_buffer()
        except Exception:
            return False
        return False

    def request_frame(self) -> Tuple[List[int], List[int]]:
        """Request one frame and return (samples, timestamps).

        Layout: [count][samples...][timestamps...][crc16]
        Returns empty lists if anything looks invalid (no blocking exceptions).
        """
        if self.ser is None:
            raise RuntimeError("Serial port not open")

        # Send 'R' to request data
        self.ser.write(b"R")

        count_raw = self.ser.read(1)
        if len(count_raw) != 1:
            return [], []
        count = count_raw[0]
        if count == 0 or count > MAX_SAMPLES:
            return [], []

        payload_len = count * 6 + 2  # samples + timestamps + crc16
        payload = self.ser.read(payload_len)
        if len(payload) != payload_len:
            return [], []

        # CRC check over count + payload without last 2 CRC bytes
        crc_recv = payload[-2] | (payload[-1] << 8)
        crc_calc = crc16_ibm(bytes([count]) + payload[:-2])
        if crc_calc != crc_recv:
            # Drop frame quietly if CRC mismatches
            return [], []

        # Unpack
        sample_bytes = payload[: 2 * count]
        ts_bytes = payload[2 * count : -2]
        samples = list(struct.unpack("<" + "H" * count, sample_bytes))
        timestamps = list(struct.unpack("<" + "I" * count, ts_bytes))
        return samples, timestamps

    def close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            finally:
                self.ser = None


def open_serial(baudrate: int = 115_200, timeout: float = 0.2) -> SerialPort:
    sp = SerialPort(baudrate=baudrate, timeout=timeout)
    print("Scanning serial ports...")
    port = sp.open_first()
    if port is None:
        raise RuntimeError("No serial device with valid ECG frame found.")
    print(f"Connected to {port}")
    return sp
