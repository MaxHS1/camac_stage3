# camac_backend.py (only the top part changes)
from typing import Optional
from .camac_api import CamacMock
from .camac_lib import CamacLib, CamacLibError

# VISA detection
_HAS_PYVISA = False
_PYVISA_ERR = None
try:
    import pyvisa  # noqa: F401
    _HAS_PYVISA = True
except Exception as e:
    _PYVISA_ERR = e

_CAMAC_VISA_CLS = None
_CAMAC_VISA_ERR = None
if _HAS_PYVISA:
    try:
        from .camac_visa_3988 import CamacVisa3988 as _CamacVisaImpl
        _CAMAC_VISA_CLS = _CamacVisaImpl
    except Exception as e:
        _CAMAC_VISA_ERR = e

class CamacBackend:
    def __init__(self, mode: str = "auto", lib_path: Optional[str] = None, resource: Optional[str] = None):
        """
        mode: 'real' | 'mock' | 'auto' | 'visa'
        """
        self.mode = mode
        self.impl = None

        if mode == "mock":
            self.impl = CamacMock()

        elif mode == "visa":
            if not _HAS_PYVISA or _CAMAC_VISA_CLS is None:
                raise RuntimeError(f"VISA requested but unavailable. pyvisa={_HAS_PYVISA} err={_PYVISA_ERR} visa_impl_err={_CAMAC_VISA_ERR}")
            self.impl = _CAMAC_VISA_CLS(resource or "GPIB0::16::INSTR")

        elif mode in ("real", "auto"):
            try:
                self.impl = CamacLib(lib_path)
            except CamacLibError:
                if mode == "real":
                    raise
                self.impl = CamacMock()
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def cdset(self, a:int, b:int): return self.impl.cdset(a,b) if hasattr(self.impl, "cdset") else None
    def cdreg(self, branch:int, crate:int, station:int, address:int): return self.impl.cdreg(branch,crate,station,address)
    def set_debug(self, level:int=1): return self.impl.set_debug(level) if hasattr(self.impl, "set_debug") else None
    def cfsa(self, function:int, ext:int, data:int|None=None): return self.impl.cfsa(function, ext, data)