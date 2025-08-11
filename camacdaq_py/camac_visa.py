
# camacdaq_py/camac_visa.py
"""
PyVISA backend for CAMAC over GPIB/VISA.

NOTE: You must fill in the device's command protocol in _naf_* methods.
Right now they return placeholder values so the app runs without crashing.
"""
from __future__ import annotations
from typing import Optional, Tuple
import pyvisa

def _pack_ext(branch:int, crate:int, station:int, address:int) -> int:
    return ((branch & 0xFF) << 24) | ((crate & 0xFF) << 16) | ((station & 0xFF) << 8) | (address & 0xFF)

def _unpack_ext(ext:int) -> Tuple[int,int,int,int]:
    return ((ext>>24)&0xFF, (ext>>16)&0xFF, (ext>>8)&0xFF, ext&0xFF)

class CamacVisa:
    def __init__(self, resource: str = "GPIB0::1::INSTR", timeout_ms: int = 2000, debug: int = 0):
        self.rm = pyvisa.ResourceManager()
        self.dev = self.rm.open_resource(resource)
        self.dev.timeout = timeout_ms
        self._debug = int(debug)

    def cdset(self, a:int, b:int):
        if self._debug:
            print(f"[VISA] cdset({a},{b})")

    def set_debug(self, level:int = 1):
        self._debug = int(level)

    def cdreg(self, branch:int, crate:int, station:int, address:int) -> int:
        if self._debug:
            print(f"[VISA] cdreg b={branch} c={crate} n={station} a={address}")
        return _pack_ext(branch, crate, station, address)

    def cfsa(self, function:int, ext:int, data: Optional[int] = None):
        b,c,n,a = _unpack_ext(ext)
        if 0 <= function <= 7:
            return self._naf_read(b,c,n,a,function)
        elif 16 <= function <= 23:
            q = self._naf_write(b,c,n,a,function, 0 if data is None else int(data))
            return (0 if data is None else int(data)), q
        else:
            q = self._naf_ctrl(b,c,n,a,function)
            return 0, q

    # --------- FILL THESE WITH YOUR DEVICE'S REAL COMMANDS ----------
    def _naf_read(self, b:int, c:int, n:int, a:int, f:int):
        # Example placeholder (replace with real IO):
        # self.dev.write(f"NAF:READ {b},{c},{n},{a},{f}")
        # resp = self.dev.read()
        # data, q = parse_resp(resp)
        if self._debug:
            print(f"[VISA] READ NAF b={b} c={c} n={n} a={a} f={f}")
        data = ((c & 0xFF) << 8) ^ ((n & 0xFF) << 4) ^ (a & 0xF) ^ (f << 12)
        q = True
        return data & 0xFFFFFF, q

    def _naf_write(self, b:int, c:int, n:int, a:int, f:int, data:int) -> bool:
        # Example placeholder (replace with real IO):
        # self.dev.write(f"NAF:WRITE {b},{c},{n},{a},{f},{data}")
        if self._debug:
            print(f"[VISA] WRITE NAF b={b} c={c} n={n} a={a} f={f} data={data}")
        return True

    def _naf_ctrl(self, b:int, c:int, n:int, a:int, f:int) -> bool:
        # Example placeholder (replace with real IO):
        # self.dev.write(f"NAF:CTRL {b},{c},{n},{a},{f}")
        if self._debug:
            print(f"[VISA] CTRL NAF b={b} c={c} n={n} a={a} f={f}")
        return True
