# camac_visa_3988.py - VISA backend for KineticSystems 3988 (binary N-A-F protocol)
from __future__ import annotations
from typing import Optional, Tuple

class CamacVisa3988:
    """
    Binary protocol (per KS-3988):
      - Write exactly 3 bytes: N, A, F (all 0-31).
      - For READ (F in 0..7): follow with read of 3/2/1 bytes (Hi -> Mid -> Low).
      - For WRITE (F in 16..23): write 3 data bytes (Hi -> Mid -> Low) after N,A,F.
      - For CONTROL (others, e.g., 24, 26): just the 3-byte NAF (no data).
    We do NOT use termination chars. EOI (END) on writes must be enabled by VISA.
    """

    def __init__(self,
                 resource: str,
                 lib_path: Optional[str] = None,
                 timeout_ms: int = 5000,
                 width_bytes: int = 3) -> None:
        try:
            import pyvisa
        except Exception as e:
            raise ImportError("pyvisa is required for VISA mode") from e

        rm = pyvisa.ResourceManager(lib_path) if lib_path else pyvisa.ResourceManager()
        self.dev = rm.open_resource(resource)

        # Binary transfers: no terminations
        self.dev.write_termination = None
        self.dev.read_termination = None
        self.dev.send_end = True            # assert EOI on write
        self.dev.timeout = int(timeout_ms)

        self._debug = 0
        self._width = int(width_bytes) if width_bytes in (1, 2, 3) else 3

    # ----- API expected by camac_backend -----
    def set_debug(self, level: int) -> None:
        self._debug = int(level)

    def cdreg(self, branch: int, crate: int, station: int, address: int) -> int:
        # match the legacy ext packing (B,C,N,A)
        return ((branch & 0xFF) << 24) | ((crate & 0xFF) << 16) | ((station & 0xFF) << 8) | (address & 0xFF)

    def cfsa(self, function: int, ext: int, data: Optional[int] = None) -> Tuple[int, bool]:
        b = (ext >> 24) & 0xFF
        c = (ext >> 16) & 0xFF
        n = (ext >> 8) & 0xFF
        a = ext & 0xFF

        # the crate controller handles B/C; 3988 expects only N, A, F here.
        F = function & 0x1F
        self._write_naf(n, a, F)

        if 0 <= F <= 7:  # READ
            width = self._width
            raw = self._read_bytes(width)
            val = self._be_bytes_to_int(raw)
            return val, True  # if the 3988 returned bytes, we treat Q=True

        elif 16 <= F <= 23:  # WRITE
            val = int(0 if data is None else data) & 0xFFFFFF
            payload = self._int_to_be_bytes(val, 3)  # always send 3; 3988 ignores upper bytes per width
            self._write_raw(payload)
            return val, True

        else:  # CONTROL
            # no data follows; if write() returns without error, consider Q=True
            return 0, True

    # ----- helpers -----
    def _write_naf(self, n: int, a: int, f: int) -> None:
        if not (0 <= n <= 31 and 0 <= a <= 31 and 0 <= f <= 31):
            raise ValueError(f"Invalid NAF: N={n},A={a},F={f}")
        payload = bytes((n & 0x1F, a & 0x1F, f & 0x1F))
        self._write_raw(payload)

    def _write_raw(self, payload: bytes) -> None:
        if self._debug:
            print(f"[GPIB WRITE] {payload.hex(' ')}")
        # write_raw -> bytes; ensure it's 'bytes' not str
        self.dev.write_raw(payload)

    def _read_bytes(self, count: int) -> bytes:
        if count <= 0:
            return b""
        # read a fixed number of bytes (no terminations)
        data = self.dev.read_bytes(count)
        if self._debug:
            print(f"[GPIB READ]  {data.hex(' ')}")
        if len(data) != count:
            # VISA should block until count or timeout; treat short read as error-like but return what we have
            pass
        return data

    @staticmethod
    def _int_to_be_bytes(val: int, width: int) -> bytes:
        # width in {1,2,3}
        if width == 1:
            return bytes((val & 0xFF,))
        elif width == 2:
            return bytes(((val >> 8) & 0xFF, val & 0xFF))
        else:
            return bytes(((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF))

    @staticmethod
    def _be_bytes_to_int(buf: bytes) -> int:
        v = 0
        for b in buf:
            v = (v << 8) | (b & 0xFF)
        return v & 0xFFFFFF