
import os, sys, ctypes
from ctypes import c_int, POINTER, byref

class CamacLibError(RuntimeError):
    pass

class CamacLib:
    def __init__(self, lib_path: str | None = None):
        lib_path = lib_path or os.getenv("CAMAC_LIB")
        if lib_path:
            candidates = [lib_path]
        else:
            if sys.platform.startswith("win"):
                candidates = ["libcamac_gpib.dll", "camac_gpib.dll", "camac.dll"]
            elif sys.platform == "darwin":
                candidates = ["libcamac_gpib.dylib", "libcamac.dylib"]
            else:
                candidates = ["libcamac_gpib.so", "libcamac.so"]

        last_err = None
        self.lib = None
        for cand in candidates:
            try:
                self.lib = ctypes.CDLL(cand)
                break
            except OSError as e:
                last_err = e

        if self.lib is None:
            raise CamacLibError(f"Could not load CAMAC shared library. Tried {candidates}. "
                                f"Set CAMAC_LIB=/path/to/libcamac_gpib.<so|dylib|dll>. Last error: {last_err}")

        self.lib.cdset.argtypes = [c_int, c_int]
        self.lib.cdset.restype = None

        self.lib.cdreg.argtypes = [POINTER(c_int), c_int, c_int, c_int, c_int]
        self.lib.cfsa.argtypes = [c_int, c_int, POINTER(c_int), POINTER(c_int)]
        self.lib.cfsa.restype = c_int

        self._has_debug = hasattr(self.lib, "setCamacDebug")
        if self._has_debug:
            self.lib.setCamacDebug.argtypes = [c_int]
            self.lib.setCamacDebug.restype  = None

    def cdset(self, id1:int, id2:int):
        self.lib.cdset(c_int(id1), c_int(id2))

    def cdreg(self, branch:int, crate:int, station:int, address:int) -> int:
        ext = c_int(0)
        self.lib.cdreg(byref(ext), c_int(branch), c_int(crate), c_int(station), c_int(address))
        return ext.value

    def set_debug(self, level:int=1):
        if self._has_debug:
            self.lib.setCamacDebug(c_int(level))

    def cfsa(self, function:int, ext:int, data:int|None=None):
        data_c = c_int(0 if data is None else int(data))
        q = c_int(0)
        ret = self.lib.cfsa(c_int(function), c_int(ext), byref(data_c), byref(q))
        if ret != 0:
            raise CamacLibError(f"cfsa failed with code {ret}")
        return data_c.value, bool(q.value)
