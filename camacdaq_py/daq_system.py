
from dataclasses import dataclass
from typing import Dict
from .config_parser import ModuleEntry, parse_cit_cfg

@dataclass
class Module:
    entry: ModuleEntry

class DAQSystem:
    def __init__(self, cam):
        self.cam = cam
        self.modules: Dict[str, Module] = {}

    def load_cfg_text(self, text:str):
        parsed = parse_cit_cfg(text)
        self.modules = {name: Module(entry=me) for name, me in parsed.items()}
        return list(self.modules.keys())

    def list_modules(self):
        return [(m.entry.name, m.entry.branch, m.entry.crate, m.entry.station, m.entry.comment) for m in self.modules.values()]

    def _ext_for(self, name:str, address:int) -> int:
        m = self.modules.get(name.upper())
        if not m:
            raise KeyError(f"Unknown module name: {name}")
        me = m.entry
        return self.cam.cdreg(me.branch, me.crate, me.station, address)

    def camac_read(self, name:str, address:int, function:int=0):
        ext = self._ext_for(name, address)
        data, q = self.cam.cfsa(function, ext, None)
        return data, q

    def camac_write(self, name:str, address:int, function:int, data:int):
        ext = self._ext_for(name, address)
        _, q = self.cam.cfsa(function, ext, data)
        return q
