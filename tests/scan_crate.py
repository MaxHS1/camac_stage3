#!/usr/bin/env python3
import argparse, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camacdaq_py.camac_backend import CamacBackend

# speed up scanning: short VISA timeout
try:
    cam.impl.dev.timeout = 100  # ms
except Exception:
    pass

def main():
    p = argparse.ArgumentParser(description="Scan CAMAC crate for responsive N-A-F (read functions)")
    p.add_argument("--mode", choices=["visa","real","mock","auto"], default="visa")
    p.add_argument("--resource", help="VISA resource, e.g. GPIB0::16::INSTR")
    p.add_argument("--lib", help="Path to native DLL/.so if using --mode real")
    p.add_argument("--branch", "-b", type=int, default=1)
    p.add_argument("--crate",  "-c", type=int, default=1)
    p.add_argument("--n-start", type=int, default=1)
    p.add_argument("--n-end",   type=int, default=23)
    p.add_argument("--a-start", type=int, default=0)
    p.add_argument("--a-end",   type=int, default=15)
    p.add_argument("--func", "-f", type=int, default=0, help="Read function 0..7 (default 0)")
    p.add_argument("--delay", type=float, default=0.0, help="Seconds between ops")
    args = p.parse_args()

    cam = CamacBackend(mode=args.mode, lib_path=args.lib, resource=args.resource)
    cam.set_debug(0)

    found = 0
    print(f"# Scanning N={args.n_start}..{args.n_end}, A={args.a_start}..{args.a_end}, F={args.func}, B={args.branch}, C={args.crate}")
    for n in range(args.n_start, args.n_end+1):
        for a in range(args.a_start, args.a_end+1):
            ext = cam.cdreg(args.branch, args.crate, n, a)
            try:
                data, q = cam.cfsa(args.func, ext, None)
            except Exception as e:
                print(f"ERR N={n:02d} A={a:02d}: {e}")
                continue
            if q:
                print(f"OK  N={n:02d} A={a:02d} F={args.func:02d}  Data={data:7d} (0x{data:06X})  Q=1")
                found += 1
            time.sleep(args.delay)
    print(f"# Done. Found {found} responsive addresses.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
