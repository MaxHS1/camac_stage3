#!/usr/bin/env python3
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camacdaq_py.camac_backend import CamacBackend

def try_one(cam, n, a, f):
    ext = cam.cdreg(1,1,n,a)
    try:
        d,q = cam.cfsa(f, ext, None)
        print(f"N={n:02d} A={a:02d} F={f:02d}  Data={d:7d} (0x{d:06X})  Q={1 if q else 0}")
    except Exception as e:
        print(f"N={n:02d} A={a:02d} F={f:02d}  ERROR: {e}")

def main():
    cam = CamacBackend(mode="visa", resource="GPIB0::16::INSTR")
    # speed up timeouts for probing
    try: cam.impl.dev.timeout = 100
    except: pass

    # *** Force 16-bit width for this probe ***
    try:
        cam.impl._width_bytes = 2
        print("# Using 16-bit transfers for this probe")
    except Exception as e:
        print("# Could not set width_bytes=2:", e)

    # Try A=0..3, F in {0,2,4} on N=3
    for f in (0,2,4):
        for a in range(0,4):
            try_one(cam, 3, a, f)

if __name__ == "__main__":
    main()
