
#!/usr/bin/env python3
import os, sys, argparse, readline, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camacdaq_py.camac_backend import CamacBackend

def main():
    ap = argparse.ArgumentParser(description="ctalk (Python) with real/mock/visa backend")
    ap.add_argument("--mode", choices=["auto","real","mock","visa"], default="auto")
    ap.add_argument("--lib", help="Path to CAMAC shared library (.so/.dylib/.dll)")
    ap.add_argument("--resource", help="VISA resource string (e.g., GPIB0::1::INSTR)")
    args = ap.parse_args()

    cam = CamacBackend(mode=args.mode, lib_path=args.lib, resource=args.resource)
    cam.cdset(0,0)

    print("\n*****************************")
    print("* Interactive talk to CAMAC *")
    print("*****************************")
    print("Commands:")
    print("  C crate station address function [data]")
    print("  B [branch]  - get/set branch (local)")
    print("  D [level]   - set debug level")
    print("  Q / E       - quit/exit")

    branch = 1

    while True:
        try:
            line = input("CAMAC> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        toks = [t for t in line.replace(',',' ').split() if t]
        cmd = toks[0].upper()
        if cmd in {"Q","QUIT","E","EXIT"}:
            break
        elif cmd in {"B","BRANCH"}:
            if len(toks) == 1:
                print(f"\tBranch: {branch}")
            else:
                try:
                    branch = int(toks[1], 0)
                    print(f"\tBranch: {branch}")
                except ValueError:
                    print("!! Branch must be integer")
        elif cmd in {"D","DEBUG"}:
            level = int(toks[1], 0) if len(toks)>1 else 1
            cam.set_debug(level)
            print(f"\tDebug: {level}")
        elif cmd in {"C","CAMAC"}:
            if len(toks) < 5:
                print("Usage: C crate station address function [data]")
                continue
            try:
                crate   = int(toks[1], 0)
                station = int(toks[2], 0)
                address = int(toks[3], 0)
                function= int(toks[4], 0)
                data = int(toks[5], 0) if len(toks) > 5 else None
            except ValueError:
                print("!! All numeric fields must be integers (0x.. ok)")
                continue
            ext = cam.cdreg(branch, crate, station, address)
            d,q = cam.cfsa(function, ext, data)
            if 0 <= function <= 7:
                print(f"\tData: {d:6d} (Dec), {d:5X} (Hex), Q: {'True' if q else 'False'}")
            elif 16 <= function <= 23:
                print(f"\tData written, Q: {'True' if q else 'False'}")
            else:
                print(f"\tQ: {'True' if q else 'False'}")
        else:
            print("Unknown command. Try: C, B, D, Q/E")

if __name__ == "__main__":
    main()
