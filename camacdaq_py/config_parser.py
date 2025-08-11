
import re
from dataclasses import dataclass
from typing import Dict

@dataclass
class ModuleEntry:
    name:str
    branch:int
    crate:int
    station:int
    comment:str|None=None

def parse_cit_cfg(text:str) -> Dict[str, ModuleEntry]:
    entries: Dict[str, ModuleEntry] = {}
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith(("*","#","!",";")):
            continue
        parts = re.split(r"\s+", line, maxsplit=4)
        if len(parts) < 4:
            continue
        name = parts[0]
        try:
            branch = int(parts[1]); crate  = int(parts[2]); station= int(parts[3])
        except ValueError:
            continue
        comment = parts[4] if len(parts) >= 5 else None
        entries[name.upper()] = ModuleEntry(name=name, branch=branch, crate=crate, station=station, comment=comment)
    return entries
