#!/usr/bin/env python3
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camacdaq_py.camac_backend import CamacBackend

SLOTS = [2, 9, 10, 19, 20]        # your populated N’s
AS     = [0, 1, 2, 3]             # common A range
FUNCS  = [0, 2, 4]                # common read functions
WIDTHS = [3, 2, 1]                # try 24, 16, 8-bit in that order

def try_read(cam, n, a, f):
    ext = cam.cdreg(1,1,n,a)
    try:
        d, q = cam.cfsa(f, ext, None)
        return d, q, None
    except Exception as e:
        return None, None, e

def main():
    cam = CamacBackend(mode="visa", resource="GPIB0::16::INSTR")
    # speed up
    try: cam.impl.dev.timeout = 150
    except: pass
    cam.set_debug(0)

    for n in SLOTS:
        print(f"\n=== N={n} ===")
        # one-time control “init” on A=0 before reads (often needed)
        ext = cam.cdreg(1,1,n,0)
        try:
            _d,_q = cam.cfsa(24, ext, None)  # F=24 control
            time.sleep(0.05)
        except Exception:
            pass

        for w in WIDTHS:
            try:
                cam.impl._width_bytes = w
            except Exception:
                pass
            print(f"  -- width={8*w}-bit --")
            any_ok = False
            for f in FUNCS:
                for a in AS:
                    d, q, err = try_read(cam, n, a, f)
                    if err is None:
                        print(f"    N={n:02d} A={a:02d} F={f:02d}  Data={d:7d} (0x{d:06X})  Q={1 if q else 0}")
                        any_ok = True
                    else:
                        # comment this line out if too chatty:
                        # print(f"    N={n:02d} A={a:02d} F={f:02d}  ERR: {err}")
                        pass
            if not any_ok:
                print("    (no successful reads at this width)")
    print("\n# Done")
if __name__ == "__main__":
    main()
