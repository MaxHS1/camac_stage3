#!/usr/bin/env python3
import time, sys, pathlib
sys.path.insert(0, r"C:\DAQ\camac_stage3")
from camacdaq_py.camac_backend import CamacBackend

# Your updated slots
SLOTS = [2, 9, 15, 19]
AS     = range(0, 8)         # broaden if needed
FUNCS  = (0, 2, 4)           # common read functions

cam = CamacBackend(mode="visa", resource="GPIB0::16::INSTR")
try: cam.impl.dev.timeout = 150
except: pass

for n in SLOTS:
    print(f"\n=== N={n} ===")
    # harmless clear/control once on A=0 (ignore errors)
    ext0 = cam.cdreg(1,1,n,0)
    try: cam.cfsa(24, ext0, None)
    except: pass

    for w in (3, 2, 1):  # 24-, 16-, 8-bit
        try: cam.impl._width_bytes = w
        except: pass
        print(f"  -- width={8*w}-bit --")
        hits = 0
        for a in AS:
            ext = cam.cdreg(1,1,n,a)
            for f in FUNCS:
                try:
                    d1,q1 = cam.cfsa(f, ext, None)
                    time.sleep(0.05)
                    d2,q2 = cam.cfsa(f, ext, None)
                    if (d1 or d2) or (d2 != d1):
                        print(f"   N={n:02d} A={a:02d} F={f:02d} d1={d1:7d} d2={d2:7d} Δ={d2-d1:+} Q=({int(bool(q1))},{int(bool(q2))})")
                        hits += 1
                except Exception:
                    pass
        if not hits:
            print("     (no changing/non-zero reads)")

print("\n# Done")
