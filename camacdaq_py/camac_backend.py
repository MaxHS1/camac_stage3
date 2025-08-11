
from typing import Optional
from .camac_api import CamacMock
from .camac_lib import CamacLib, CamacLibError

class CamacBackend:
    def __init__(self, mode: str = "auto", lib_path: Optional[str] = None):
        self.mode = mode
        self.impl = None
        if mode == "mock":
            self.impl = CamacMock()
        elif mode in ("real","auto"):
            try:
                self.impl = CamacLib(lib_path)
            except CamacLibError:
                if mode == "real":
                    raise
                self.impl = CamacMock()

    def cdset(self, a:int, b:int): return self.impl.cdset(a,b)
    def cdreg(self, branch:int, crate:int, station:int, address:int): return self.impl.cdreg(branch,crate,station,address)
    def set_debug(self, level:int=1): return self.impl.set_debug(level)
    def cfsa(self, function:int, ext:int, data:int|None=None): return self.impl.cfsa(function, ext, data)
