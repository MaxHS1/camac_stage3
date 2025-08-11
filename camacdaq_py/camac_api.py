
from dataclasses import dataclass

READ_FUNCS = set(range(0, 8))
WRITE_FUNCS = set(range(16, 24))
CTRL_FUNCS  = set(range(8, 16)) | set(range(24, 32))

def pack_ext(branch:int, crate:int, station:int, address:int) -> int:
    return ((branch & 0xFF) << 24) | ((crate & 0xFF) << 16) | ((station & 0xFF) << 8) | (address & 0xFF)

def unpack_ext(ext:int):
    return ((ext>>24)&0xFF, (ext>>16)&0xFF, (ext>>8)&0xFF, ext&0xFF)

@dataclass
class CamacState:
    branch:int = 1
    debug:int = 0

class CamacMock:
    def __init__(self):
        self.state = CamacState()

    def cdset(self, id1:int, id2:int):
        if self.state.debug:
            print(f"[DEBUG] cdset({id1}, {id2})")

    def cdreg(self, branch:int, crate:int, station:int, address:int) -> int:
        if self.state.debug:
            print(f"[DEBUG] cdreg b={branch} c={crate} n={station} a={address}")
        return pack_ext(branch, crate, station, address)

    def set_debug(self, level:int=1):
        self.state.debug = int(level)

    def set_branch(self, branch:int):
        self.state.branch = int(branch)

    def get_branch(self) -> int:
        return self.state.branch

    def cfsa(self, function:int, ext:int, data:int|None=None):
        b,c,n,a = unpack_ext(ext)
        if function in READ_FUNCS:
            val = ((ext & 0xFFFFFF) ^ (function<<12)) & 0xFFFFFF
            return val, True
        elif function in WRITE_FUNCS:
            return (data if data is not None else 0), True
        elif function in CTRL_FUNCS:
            return 0, True
        else:
            return 0, False
