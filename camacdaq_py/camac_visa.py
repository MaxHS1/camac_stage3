# camac_visa.py — Kinetic Systems 3988 (GPIB) single-transfer N-A-F over VISA (binary)
from __future__ import annotations
from typing import Optional, Tuple

try:
    from pyvisa import ResourceManager
except Exception as e:
    raise ImportError("pyvisa is required for VISA mode") from e

class CamacVisa:
    """
    Minimal VISA backend for KS-3988 crate controller using BINARY N-A-F:
      - Send exactly 3 bytes for a command: [N, A, F]
      - For data reads/writes, exchange 1/2/3 bytes depending on module width
      - Termination by EOI only (no string terminations)
      - Optional 1-byte status may follow if SBE is enabled; we treat Q=True *only* if a status byte arrives and bit0 is set
    """

    def __init__(self, resource: str, lib_path: Optional[str] = None, timeout_ms: int = 2000, width_bytes: int = 3):
        rm = ResourceManager(lib_path) if lib_path else ResourceManager()
        self.dev = rm.open_resource(resource)
        # raw binary; no terminations
        try:
            self.dev.write_termination = None
            self.dev.read_termination = None
        except Exception:
            pass
        self.dev.timeout = int(timeout_ms)
        self._debug = 0
        self._width_bytes = int(width_bytes)  # 3=24-bit (default), 2=16-bit, 1=8-bit

    # ----- required by backend -----
    def set_debug(self, level: int) -> None:
        self._debug = int(level)

    def cdreg(self, branch: int, crate: int, station: int, address: int) -> int:
        return ((branch & 0xFF) << 24) | ((crate & 0xFF) << 16) | ((station & 0xFF) << 8) | (address & 0xFF)

    def cfsa(self, function: int, ext: int, data: Optional[int] = None) -> Tuple[int, bool]:
        b = (ext >> 24) & 0xFF
        c = (ext >> 16) & 0xFF
        n = (ext >> 8) & 0xFF
        a = ext & 0xFF
        if 0 <= function <= 7:                # READ
            return self._naf_read(b, c, n, a, function)
        elif 16 <= function <= 23:            # WRITE
            d = int(0 if data is None else data)
            q = self._naf_write(b, c, n, a, function, d)
            return d, q
        else:                                 # CONTROL
            q = self._naf_ctrl(b, c, n, a, function)
            return 0, q

    # ----- low-level helpers -----
    def _send_naf(self, n: int, a: int, f: int) -> None:
        payload = bytes([(n & 0xFF), (a & 0xFF), (f & 0xFF)])
        if self._debug:
            print("[WRITE RAW NAF]", list(payload))
        self.dev.write_raw(payload)

    def _read_data(self) -> int:
        nbytes = self._width_bytes
        raw = self.dev.read_bytes(nbytes)
        if self._debug:
            print(f"[READ RAW DATA{8*nbytes}]", list(raw))
        if nbytes == 3:
            return ((raw[0] << 16) | (raw[1] << 8) | raw[2]) & 0xFFFFFF
        if nbytes == 2:
            return ((raw[0] << 8) | raw[1]) & 0xFFFF
        return raw[0] & 0xFF

    def _write_data(self, data: int) -> None:
        nbytes = self._width_bytes
        if nbytes == 3:
            d = data & 0xFFFFFF
            payload = bytes([(d >> 16) & 0xFF, (d >> 8) & 0xFF, d & 0xFF])
        elif nbytes == 2:
            d = data & 0xFFFF
            payload = bytes([(d >> 8) & 0xFF, d & 0xFF])
        else:
            d = data & 0xFF
            payload = bytes([d])
        if self._debug:
            print(f"[WRITE RAW DATA{8*nbytes}]", list(payload))
        self.dev.write_raw(payload)

    def _read_status_byte_if_enabled(self) -> Optional[int]:
        try:
            orig = self.dev.timeout
        except Exception:
            orig = None
        try:
            if orig is not None:
                self.dev.timeout = 5
            sb = self.dev.read_bytes(1)
            if self._debug:
                print("[READ STATUS BYTE]", list(sb))
            return sb[0]
        except Exception:
            return None
        finally:
            if orig is not None:
                self.dev.timeout = orig

    # ----- N-A-F primitives -----
    def _naf_read(self, b: int, c: int, n: int, a: int, f: int) -> Tuple[int, bool]:
        self._send_naf(n, a, f)
        data = self._read_data()
        sb = self._read_status_byte_if_enabled()
        q = bool(sb & 0x01) if sb is not None else False
        return data, q

    def _naf_write(self, b: int, c: int, n: int, a: int, f: int, data: int) -> bool:
        self._send_naf(n, a, f)
        self._write_data(data)
        sb = self._read_status_byte_if_enabled()
        q = bool(sb & 0x01) if sb is not None else False
        return q

    def _naf_ctrl(self, b: int, c: int, n: int, a: int, f: int) -> bool:
        self._send_naf(n, a, f)
        sb = self._read_status_byte_if_enabled()
        q = bool(sb & 0x01) if sb is not None else False
        return q