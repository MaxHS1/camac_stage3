
from typing import Optional
from .camac_api import CamacMock
from .camac_lib import CamacLib, CamacLibError

try:
    from .camac_visa import CamacVisa
    _HAS_VISA = True
except Exception:
    CamacVisa = None  # type: ignore
    _HAS_VISA = False

class CamacBackend:
    def __init__(self, mode: str = "auto", lib_path: Optional[str] = None, resource: Optional[str] = None):
        """
        mode: 'real' | 'mock' | 'auto' | 'visa'
        - real: load native C library via ctypes
        - visa: use PyVISA (NI-VISA/NI-488.2)
        - auto: try real, fallback to mock
        - mock: always mock
        """
        self.mode = mode
        self.impl = None

        if mode == "mock":
            self.impl = CamacMock()

        elif mode == "visa":
            if not _HAS_VISA:
                raise RuntimeError("PyVISA backend requested but pyvisa is not installed.")
            self.impl = CamacVisa(resource or "GPIB0::1::INSTR")

        elif mode in ("real", "auto"):
            try:
                self.impl = CamacLib(lib_path)
            except CamacLibError:
                if mode == "real":
                    raise
                self.impl = CamacMock()
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def cdset(self, a:int, b:int): return self.impl.cdset(a,b)
    def cdreg(self, branch:int, crate:int, station:int, address:int): return self.impl.cdreg(branch,crate,station,address)
    def set_debug(self, level:int=1): return self.impl.set_debug(level)
    def cfsa(self, function:int, ext:int, data:int|None=None): return self.impl.cfsa(function, ext, data)
